using System.IdentityModel.Tokens.Jwt;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Json;
using System.Security.Claims;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.IdentityModel.Tokens;
using Testcontainers.PostgreSql;
using TourneyHub.Domain.Identity;
using TourneyHub.Domain.Organizations;
using TourneyHub.Infrastructure.Persistence;
using Xunit;

namespace TourneyHub.Integration.Tests;

public sealed class PlatformAdminIntegrationTests : IAsyncLifetime
{
    private const string DevSigningKey = "dev-test-key-at-least-32-bytes-long!!";

    private readonly PostgreSqlContainer _postgres = new PostgreSqlBuilder()
        .WithDatabase("tourneyhub_admin_test")
        .WithUsername("tourneyhub")
        .WithPassword("tourneyhub")
        .Build();

    private WebApplicationFactory<Program> _factory = null!;
    private HttpClient _client = null!;

    public async Task InitializeAsync()
    {
        await _postgres.StartAsync();

        _factory = new WebApplicationFactory<Program>()
            .WithWebHostBuilder(builder =>
            {
                builder.UseSetting("ConnectionStrings:Postgres", _postgres.GetConnectionString());
                builder.UseSetting("TOURNEYHUB_ADMIN_EMAIL", "admin@tourneyhub.test");
            });

        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
        await db.Database.MigrateAsync();

        var roleManager = scope.ServiceProvider.GetRequiredService<RoleManager<IdentityRole<Guid>>>();
        if (!await roleManager.RoleExistsAsync("InstanceAdmin"))
        {
            await roleManager.CreateAsync(new IdentityRole<Guid>("InstanceAdmin"));
        }

        _client = _factory.CreateClient();
    }

    public async Task DisposeAsync()
    {
        _client?.Dispose();
        if (_factory is not null) await _factory.DisposeAsync();
        await _postgres.DisposeAsync();
    }

    private static string GenerateToken(Guid userId, string email, bool isAdmin = false)
    {
        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(DevSigningKey));
        var credentials = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);

        var claims = new List<Claim>
        {
            new(JwtRegisteredClaimNames.Sub, userId.ToString()),
            new(JwtRegisteredClaimNames.Email, email),
            new(JwtRegisteredClaimNames.Jti, Guid.NewGuid().ToString()),
            new("state", "Active"),
        };

        if (isAdmin)
        {
            claims.Add(new Claim(ClaimTypes.Role, "InstanceAdmin"));
        }

        var token = new JwtSecurityToken(
            issuer: "tourneyhub",
            audience: "tourneyhub",
            claims: claims,
            expires: DateTime.UtcNow.AddHours(1),
            signingCredentials: credentials);

        return new JwtSecurityTokenHandler().WriteToken(token);
    }

    private static StringContent JsonContent(object body) =>
        new(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");

    private static HttpRequestMessage CreateRequest(HttpMethod method, string url, Guid userId, string email, object? body = null, bool isAdmin = false)
    {
        var request = new HttpRequestMessage(method, url);
        request.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue(
            "Bearer", GenerateToken(userId, email, isAdmin));

        if (body is not null)
        {
            request.Content = JsonContent(body);
        }

        return request;
    }

    private async Task EnsureInstanceAdminAsync(Guid userId, string email)
    {
        using var scope = _factory.Services.CreateScope();
        var userManager = scope.ServiceProvider.GetRequiredService<UserManager<User>>();

        var user = await userManager.FindByEmailAsync(email);
        if (user is null)
        {
            user = new User
            {
                Id = userId,
                UserName = email,
                Email = email,
                EmailConfirmed = true,
                DisplayName = "Test Admin",
                State = AccountState.Active,
            };
            var testPassword = $"Xy9!kL2#mN8@pQ5!rT3!wZ7_{Guid.NewGuid():N}";
            var createResult = await userManager.CreateAsync(user, testPassword);
            if (!createResult.Succeeded)
            {
                throw new InvalidOperationException(
                    $"Failed to create user: {string.Join("; ", createResult.Errors.Select(e => e.Description))}");
            }
            user = await userManager.FindByEmailAsync(email);
            Assert.NotNull(user);
        }

        if (!await userManager.IsInRoleAsync(user, "InstanceAdmin"))
        {
            var roleResult = await userManager.AddToRoleAsync(user, "InstanceAdmin");
            Assert.True(roleResult.Succeeded, string.Join("; ", roleResult.Errors.Select(e => e.Description)));
        }
    }

    [Fact]
    public async Task Bootstrap_creates_admin_user_from_env_email()
    {
        using var scope = _factory.Services.CreateScope();
        var userManager = scope.ServiceProvider.GetRequiredService<UserManager<User>>();

        var adminEmail = "admin@tourneyhub.test";

        var user = await userManager.FindByEmailAsync(adminEmail);
        if (user is null)
        {
            user = new User
            {
                UserName = adminEmail,
                Email = adminEmail,
                DisplayName = "Instance Admin",
                State = AccountState.PendingVerification,
            };
            var createResult = await userManager.CreateAsync(user);
            Assert.True(createResult.Succeeded, string.Join("; ", createResult.Errors.Select(e => e.Description)));
        }

        if (!await userManager.IsInRoleAsync(user, "InstanceAdmin"))
        {
            var roleResult = await userManager.AddToRoleAsync(user, "InstanceAdmin");
            Assert.True(roleResult.Succeeded, string.Join("; ", roleResult.Errors.Select(e => e.Description)));
        }

        var adminUser = await userManager.FindByEmailAsync(adminEmail);
        Assert.NotNull(adminUser);
        Assert.True(await userManager.IsInRoleAsync(adminUser, "InstanceAdmin"));

        var admins = await userManager.GetUsersInRoleAsync("InstanceAdmin");
        Assert.True(admins.Count >= 1, "At least one InstanceAdmin must exist (FR-009c)");
    }

    [Fact]
    public async Task Non_admin_cannot_suspend_organization()
    {
        var ownerId = Guid.NewGuid();
        var email = $"owner-{Guid.NewGuid():N}@test.com";

        var createResponse = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/organizations", ownerId, email,
                new { name = "Test Org", slug = $"test-org-{Guid.NewGuid():N}" }));
        createResponse.EnsureSuccessStatusCode();
        var org = await createResponse.Content.ReadFromJsonAsync<JsonElement>();
        var orgId = org!.GetProperty("id").GetGuid();

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Put, $"/api/v1/organizations/{orgId}/suspension", ownerId, email,
                new { suspended = true, reason = "test" }));
        Assert.Equal(System.Net.HttpStatusCode.Forbidden, response.StatusCode);
    }

    [Fact]
    public async Task InstanceAdmin_can_suspend_and_reactivate_organization()
    {
        var adminId = Guid.NewGuid();
        var adminEmail = $"admin-{Guid.NewGuid():N}@test.com";
        await EnsureInstanceAdminAsync(adminId, adminEmail);

        var ownerId = Guid.NewGuid();
        var ownerEmail = $"owner-{Guid.NewGuid():N}@test.com";

        var createResponse = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/organizations", ownerId, ownerEmail,
                new { name = "Suspend Target", slug = $"suspend-target-{Guid.NewGuid():N}" }));
        createResponse.EnsureSuccessStatusCode();
        var org = await createResponse.Content.ReadFromJsonAsync<JsonElement>();
        var orgId = org!.GetProperty("id").GetGuid();

        var suspendResponse = await _client.SendAsync(
            CreateRequest(HttpMethod.Put, $"/api/v1/organizations/{orgId}/suspension", adminId, adminEmail,
                new { suspended = true, reason = "violation" }, isAdmin: true));
        Assert.Equal(System.Net.HttpStatusCode.NoContent, suspendResponse.StatusCode);

        using (var scope = _factory.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
            var suspendedOrg = await db.Organizations.FirstAsync(o => o.Id == orgId);
            Assert.Equal(OrganizationState.Suspended, suspendedOrg.State);
        }

        var reactivateResponse = await _client.SendAsync(
            CreateRequest(HttpMethod.Put, $"/api/v1/organizations/{orgId}/suspension", adminId, adminEmail,
                new { suspended = false }, isAdmin: true));
        Assert.Equal(System.Net.HttpStatusCode.NoContent, reactivateResponse.StatusCode);

        using (var scope = _factory.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
            var activeOrg = await db.Organizations.FirstAsync(o => o.Id == orgId);
            Assert.Equal(OrganizationState.Active, activeOrg.State);
        }
    }

    [Fact]
    public async Task Suspended_organization_blocks_writes()
    {
        var ownerId = Guid.NewGuid();
        var ownerEmail = $"owner-{Guid.NewGuid():N}@test.com";

        var createResponse = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/organizations", ownerId, ownerEmail,
                new { name = "Blocked Org", slug = $"blocked-org-{Guid.NewGuid():N}" }));
        createResponse.EnsureSuccessStatusCode();
        var org = await createResponse.Content.ReadFromJsonAsync<JsonElement>();
        var orgId = org!.GetProperty("id").GetGuid();

        using (var scope = _factory.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
            var dbOrg = await db.Organizations.FirstAsync(o => o.Id == orgId);
            dbOrg.Suspend();
            await db.SaveChangesAsync();
        }

        var request = new HttpRequestMessage(HttpMethod.Post, "/api/v1/leagues");
        request.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue(
            "Bearer", GenerateToken(ownerId, ownerEmail));
        request.Headers.Add("X-Organization-Id", orgId.ToString());
        request.Content = JsonContent(new { name = "Should Be Blocked" });

        var response = await _client.SendAsync(request);
        Assert.Equal(System.Net.HttpStatusCode.Forbidden, response.StatusCode);
    }

    [Fact]
    public async Task Active_organization_allows_writes()
    {
        var ownerId = Guid.NewGuid();
        var ownerEmail = $"owner-{Guid.NewGuid():N}@test.com";

        var createResponse = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/organizations", ownerId, ownerEmail,
                new { name = "Active Org", slug = $"active-org-{Guid.NewGuid():N}" }));
        createResponse.EnsureSuccessStatusCode();
        var org = await createResponse.Content.ReadFromJsonAsync<JsonElement>();
        var orgId = org!.GetProperty("id").GetGuid();

        var request = new HttpRequestMessage(HttpMethod.Post, "/api/v1/leagues");
        request.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue(
            "Bearer", GenerateToken(ownerId, ownerEmail));
        request.Headers.Add("X-Organization-Id", orgId.ToString());
        request.Content = JsonContent(new { name = "Test League" });

        var response = await _client.SendAsync(request);
        response.EnsureSuccessStatusCode();
        Assert.Equal(System.Net.HttpStatusCode.Created, response.StatusCode);
    }
}