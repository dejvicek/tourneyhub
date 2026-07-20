using System.IdentityModel.Tokens.Jwt;
using System.Net.Http;
using System.Net.Http.Json;
using System.Security.Claims;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.IdentityModel.Tokens;
using Testcontainers.PostgreSql;
using TourneyHub.Domain.Organizations;
using TourneyHub.Infrastructure.Persistence;
using Xunit;

namespace TourneyHub.Integration.Tests;

public sealed class OrganizationMembershipIntegrationTests : IAsyncLifetime
{
    private const string DevSigningKey = "dev-test-key-at-least-32-bytes-long!!";

    private readonly PostgreSqlContainer _postgres = new PostgreSqlBuilder()
        .WithDatabase("tourneyhub_org_test")
        .WithUsername("tourneyhub")
        .WithPassword("tourneyhub")
        .Build();

    private WebApplicationFactory<Program> _factory = null!;

    public async Task InitializeAsync()
    {
        await _postgres.StartAsync();

        _factory = new WebApplicationFactory<Program>()
            .WithWebHostBuilder(builder =>
            {
                builder.UseSetting("ConnectionStrings:Postgres", _postgres.GetConnectionString());
            });

        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
        await db.Database.MigrateAsync();
    }

    public async Task DisposeAsync()
    {
        if (_factory is not null) await _factory.DisposeAsync();
        await _postgres.DisposeAsync();
    }

    private static string GenerateToken(Guid userId)
    {
        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(DevSigningKey));
        var credentials = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);

        var claims = new[]
        {
            new Claim(JwtRegisteredClaimNames.Sub, userId.ToString()),
            new Claim(JwtRegisteredClaimNames.Email, $"{userId}@test.com"),
            new Claim(JwtRegisteredClaimNames.Jti, Guid.NewGuid().ToString()),
            new Claim("state", "Active"),
        };

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

    private static HttpRequestMessage CreateAuthRequest(HttpMethod method, string url, Guid userId, object? body = null)
    {
        var request = new HttpRequestMessage(method, url);
        request.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", GenerateToken(userId));

        if (body is not null)
        {
            request.Content = JsonContent(body);
        }

        return request;
    }

    [Fact]
    public async Task Create_organization_returns_201_and_stores_membership()
    {
        var userId = Guid.NewGuid();

        var response = await _factory.CreateClient().SendAsync(
            CreateAuthRequest(HttpMethod.Post, "/api/v1/organizations", userId,
                new { name = "My Org", slug = "my-org" }));

        response.EnsureSuccessStatusCode();
        Assert.Equal(System.Net.HttpStatusCode.Created, response.StatusCode);

        var org = await response.Content.ReadFromJsonAsync<JsonElement>();
        var orgId = org!.GetProperty("id").GetGuid();
        Assert.Equal("my-org", org.GetProperty("slug").GetString());

        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
        var membership = await db.Memberships
            .FirstOrDefaultAsync(m => m.OrganizationId == orgId && m.UserId == userId);
        Assert.NotNull(membership);
        Assert.Equal(MembershipRole.OrgOwner, membership.Role);
    }

    [Fact]
    public async Task Non_member_gets_403_for_org_scoped_read()
    {
        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();

        var org = new Organization("Private Org", "private-org");
        db.Organizations.Add(org);
        var memberUser = Guid.NewGuid();
        db.Memberships.Add(new Membership(memberUser, org.Id, MembershipRole.OrgOwner));
        await db.SaveChangesAsync();

        var nonMemberId = Guid.NewGuid();

        var response = await _factory.CreateClient().SendAsync(
            CreateAuthRequest(HttpMethod.Get, $"/api/v1/organizations/{org.Id}", nonMemberId));

        Assert.Equal(System.Net.HttpStatusCode.Forbidden, response.StatusCode);
    }

    [Fact]
    public async Task List_organizations_returns_only_user_organizations()
    {
        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();

        var userX = Guid.NewGuid();
        var userY = Guid.NewGuid();

        var org1 = new Organization("Org One", "org-one");
        var org2 = new Organization("Org Two", "org-two");
        db.Organizations.AddRange(org1, org2);
        db.Memberships.Add(new Membership(userX, org1.Id, MembershipRole.OrgOwner));
        db.Memberships.Add(new Membership(userY, org2.Id, MembershipRole.OrgOwner));
        await db.SaveChangesAsync();

        var response = await _factory.CreateClient().SendAsync(
            CreateAuthRequest(HttpMethod.Get, "/api/v1/organizations", userX));

        response.EnsureSuccessStatusCode();
        var orgs = await response.Content.ReadFromJsonAsync<JsonElement[]>();
        Assert.Single(orgs!);
        Assert.Equal(org1.Id, orgs![0].GetProperty("id").GetGuid());
    }

    [Fact]
    public async Task Ownership_transfer_succeeds_when_recipient_is_member()
    {
        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();

        var ownerId = Guid.NewGuid();
        var memberId = Guid.NewGuid();

        var org = new Organization("Transfer Org", "transfer-org");
        db.Organizations.Add(org);
        db.Memberships.Add(new Membership(ownerId, org.Id, MembershipRole.OrgOwner));
        db.Memberships.Add(new Membership(memberId, org.Id, MembershipRole.Player));
        await db.SaveChangesAsync();

        var response = await _factory.CreateClient().SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/organizations/{org.Id}/transfer-ownership", ownerId,
                new { newOwnerUserId = memberId }));

        var responseBody = await response.Content.ReadAsStringAsync();
        Assert.Equal(System.Net.HttpStatusCode.NoContent, response.StatusCode);

        // Use a fresh scope to verify persistence
        using var verifyScope = _factory.Services.CreateScope();
        var verifyDb = verifyScope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();

        var updatedOwner = await verifyDb.Memberships
            .FirstOrDefaultAsync(m => m.OrganizationId == org.Id && m.UserId == ownerId);
        Assert.NotNull(updatedOwner);
        Assert.Equal(MembershipRole.Organizer, updatedOwner!.Role);

        var updatedMember = await verifyDb.Memberships
            .FirstOrDefaultAsync(m => m.OrganizationId == org.Id && m.UserId == memberId);
        Assert.NotNull(updatedMember);
        Assert.Equal(MembershipRole.OrgOwner, updatedMember!.Role);
    }

    [Fact]
    public async Task Transfer_ownership_rejected_when_recipient_not_member()
    {
        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();

        var ownerId = Guid.NewGuid();
        var outsiderId = Guid.NewGuid();

        var org = new Organization("Sole Org", "sole-org");
        db.Organizations.Add(org);
        db.Memberships.Add(new Membership(ownerId, org.Id, MembershipRole.OrgOwner));
        await db.SaveChangesAsync();

        var response = await _factory.CreateClient().SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/organizations/{org.Id}/transfer-ownership", ownerId,
                new { newOwnerUserId = outsiderId }));

        Assert.Equal(System.Net.HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task Organization_creation_auto_generates_slug_from_name()
    {
        var userId = Guid.NewGuid();

        var response = await _factory.CreateClient().SendAsync(
            CreateAuthRequest(HttpMethod.Post, "/api/v1/organizations", userId,
                new { name = "My Awesome Organization" }));

        response.EnsureSuccessStatusCode();
        var org = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("my-awesome-organization", org!.GetProperty("slug").GetString());
    }
}