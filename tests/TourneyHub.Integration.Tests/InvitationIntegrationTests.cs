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
using TourneyHub.Application.Identity;
using TourneyHub.Application.Tenancy;
using TourneyHub.Domain.Identity;
using TourneyHub.Domain.Organizations;
using TourneyHub.Infrastructure.Persistence;
using Xunit;

namespace TourneyHub.Integration.Tests;

public sealed class InvitationIntegrationTests : IAsyncLifetime
{
    private const string DevSigningKey = "dev-test-key-at-least-32-bytes-long!!";

    private readonly PostgreSqlContainer _postgres = new PostgreSqlBuilder()
        .WithDatabase("tourneyhub_inv_test")
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

    private static string GenerateToken(Guid userId, string? email = null)
    {
        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(DevSigningKey));
        var credentials = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);

        var claims = new List<Claim>
        {
            new(JwtRegisteredClaimNames.Sub, userId.ToString()),
            new(JwtRegisteredClaimNames.Email, email ?? $"{userId}@test.com"),
            new(JwtRegisteredClaimNames.Jti, Guid.NewGuid().ToString()),
            new("state", "Active"),
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

    private static HttpRequestMessage CreateAuthRequest(
        HttpMethod method, string url, Guid userId, string? email = null, object? body = null,
        Guid? orgId = null)
    {
        var request = new HttpRequestMessage(method, url);
        request.Headers.Authorization =
            new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", GenerateToken(userId, email));

        if (orgId.HasValue)
        {
            request.Headers.Add("X-Organization-Id", orgId.Value.ToString());
        }

        if (body is not null)
        {
            request.Content = JsonContent(body);
        }

        return request;
    }

    private async Task<(Organization Org, Guid OwnerId)> SeedOrganizationWithOwner(
        string name, string slug, string email = "owner@test.com", Guid? ownerId = null)
    {
        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();

        var org = new Organization(name, slug);
        db.Organizations.Add(org);

        var uid = ownerId ?? Guid.NewGuid();
        db.Memberships.Add(new Membership(uid, org.Id, MembershipRole.OrgOwner));

        await db.SaveChangesAsync();

        return (org, uid);
    }

    private async Task<Invitation> SeedInvitation(Guid organizationId, string email,
        InvitedRole role = InvitedRole.Player, InvitationScopeType scopeType = InvitationScopeType.League,
        Guid? scopeId = null)
    {
        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
        var tenant = scope.ServiceProvider.GetRequiredService<ITenantContext>();
        ((Infrastructure.Tenancy.HttpTenantContext)tenant).SetTenant(organizationId);

        var invitation = new Invitation(
            organizationId, email, scopeType,
            scopeId ?? Guid.NewGuid(), role, Guid.NewGuid());
        db.Invitations.Add(invitation);
        await db.SaveChangesAsync();

        return invitation;
    }

    [Fact]
    public async Task Create_invitation_returns_201_with_correct_data()
    {
        var (org, ownerId) = await SeedOrganizationWithOwner("Invite Org", "invite-org");
        var email = "player@example.com";

        var response = await _factory.CreateClient().SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/leagues/{Guid.NewGuid()}/invitations", ownerId,
                email: email, orgId: org.Id,
                body: new { email, role = "player" }));

        Assert.Equal(System.Net.HttpStatusCode.Created, response.StatusCode);

        var body = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(email, body.GetProperty("email").GetString());
        Assert.Equal("pending", body.GetProperty("state").GetString());
        Assert.Equal("player", body.GetProperty("role").GetString());
        Assert.Equal("league", body.GetProperty("scopeType").GetString());
    }

    [Fact]
    public async Task Create_invitation_with_organizer_role()
    {
        var (org, ownerId) = await SeedOrganizationWithOwner("Invite Org 2", "invite-org-2");
        var email = "organizer@example.com";

        var response = await _factory.CreateClient().SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/leagues/{Guid.NewGuid()}/invitations", ownerId,
                email: email, orgId: org.Id,
                body: new { email, role = "organizer" }));

        Assert.Equal(System.Net.HttpStatusCode.Created, response.StatusCode);

        var body = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("organizer", body.GetProperty("role").GetString());
    }

    [Fact]
    public async Task Get_invitation_publicly_returns_status()
    {
        var (org, _) = await SeedOrganizationWithOwner("Public Invite", "public-invite");
        var invitation = await SeedInvitation(org.Id, "public@example.com");

        var response = await _factory.CreateClient().GetAsync(
            $"/api/v1/invitations/{invitation.Id}");

        Assert.Equal(System.Net.HttpStatusCode.OK, response.StatusCode);

        var body = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(invitation.Id, body.GetProperty("id").GetGuid());
        Assert.Equal("public@example.com", body.GetProperty("email").GetString());
        Assert.Equal("pending", body.GetProperty("state").GetString());
    }

    [Fact]
    public async Task Get_invitation_returns_404_for_unknown_id()
    {
        var response = await _factory.CreateClient().GetAsync(
            $"/api/v1/invitations/{Guid.NewGuid()}");

        Assert.Equal(System.Net.HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task Accept_invitation_creates_membership_with_correct_role()
    {
        var (org, _) = await SeedOrganizationWithOwner("Accept Org", "accept-org");
        var userId = Guid.NewGuid();
        var email = "accepted@example.com";
        var invitation = await SeedInvitation(org.Id, email, InvitedRole.Player);

        var response = await _factory.CreateClient().SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/invitations/{invitation.Id}/accept",
                userId, email: email));

        Assert.Equal(System.Net.HttpStatusCode.OK, response.StatusCode);

        var body = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("accepted", body.GetProperty("state").GetString());

        using var verifyScope = _factory.Services.CreateScope();
        var verifyDb = verifyScope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
        var membership = await verifyDb.Memberships
            .FirstOrDefaultAsync(m => m.OrganizationId == org.Id && m.UserId == userId);
        Assert.NotNull(membership);
        Assert.Equal(MembershipRole.Player, membership!.Role);
    }

    [Fact]
    public async Task Accept_invitation_grants_organizer_role()
    {
        var (org, _) = await SeedOrganizationWithOwner("Org Role", "org-role-accept");
        var userId = Guid.NewGuid();
        var email = "orgrole@example.com";
        var invitation = await SeedInvitation(org.Id, email, InvitedRole.Organizer);

        var response = await _factory.CreateClient().SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/invitations/{invitation.Id}/accept",
                userId, email: email));

        Assert.Equal(System.Net.HttpStatusCode.OK, response.StatusCode);

        using var verifyScope = _factory.Services.CreateScope();
        var verifyDb = verifyScope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
        var membership = await verifyDb.Memberships
            .FirstOrDefaultAsync(m => m.OrganizationId == org.Id && m.UserId == userId);
        Assert.NotNull(membership);
        Assert.Equal(MembershipRole.Organizer, membership!.Role);
    }

    [Fact]
    public async Task Accept_invitation_twice_fails()
    {
        var (org, _) = await SeedOrganizationWithOwner("Double Accept", "double-accept");
        var userId = Guid.NewGuid();
        var email = "double@example.com";
        var invitation = await SeedInvitation(org.Id, email);

        await _factory.CreateClient().SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/invitations/{invitation.Id}/accept",
                userId, email: email));

        var response2 = await _factory.CreateClient().SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/invitations/{invitation.Id}/accept",
                userId, email: email));

        Assert.Equal(System.Net.HttpStatusCode.Conflict, response2.StatusCode);
    }

    [Fact]
    public async Task Accept_invitation_with_wrong_email_fails()
    {
        var (org, _) = await SeedOrganizationWithOwner("Wrong Email", "wrong-email");
        var userId = Guid.NewGuid();
        var invitation = await SeedInvitation(org.Id, "correct@example.com");

        var response = await _factory.CreateClient().SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/invitations/{invitation.Id}/accept",
                userId, email: "wrong@example.com"));

        Assert.Equal(System.Net.HttpStatusCode.Forbidden, response.StatusCode);
    }

    [Fact]
    public async Task Decline_invitation_transitions_state()
    {
        var (org, _) = await SeedOrganizationWithOwner("Decline Org", "decline-org");
        var userId = Guid.NewGuid();
        var email = "decliner@example.com";
        var invitation = await SeedInvitation(org.Id, email);

        var response = await _factory.CreateClient().SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/invitations/{invitation.Id}/decline",
                userId, email: email));

        Assert.Equal(System.Net.HttpStatusCode.NoContent, response.StatusCode);

        using var verifyScope = _factory.Services.CreateScope();
        var verifyDb = verifyScope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
        var updated = await verifyDb.Invitations.FindAsync(invitation.Id);
        Assert.Equal(InvitationState.Declined, updated!.State);
    }

    [Fact]
    public async Task Accept_expired_invitation_fails()
    {
        var (org, _) = await SeedOrganizationWithOwner("Expired Org", "expired-org-accept");
        var userId = Guid.NewGuid();
        var email = "expired@example.com";

        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
        var tenant = scope.ServiceProvider.GetRequiredService<ITenantContext>();
        ((Infrastructure.Tenancy.HttpTenantContext)tenant).SetTenant(org.Id);

        var invitation = new Invitation(
            org.Id, email, InvitationScopeType.League,
            Guid.NewGuid(), InvitedRole.Player, Guid.NewGuid());
        typeof(Invitation).GetProperty(nameof(Invitation.ExpiresAt))!
            .SetValue(invitation, DateTime.UtcNow.AddDays(-1));
        db.Invitations.Add(invitation);
        await db.SaveChangesAsync();

        var response = await _factory.CreateClient().SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/invitations/{invitation.Id}/accept",
                userId, email: email));

        Assert.Equal(System.Net.HttpStatusCode.Gone, response.StatusCode);
    }

    [Fact]
    public async Task Accept_revoked_invitation_fails()
    {
        var (org, _) = await SeedOrganizationWithOwner("Revoked Org", "revoked-org-accept");
        var userId = Guid.NewGuid();
        var email = "revoked@example.com";

        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
        var tenant = scope.ServiceProvider.GetRequiredService<ITenantContext>();
        ((Infrastructure.Tenancy.HttpTenantContext)tenant).SetTenant(org.Id);

        var invitation = new Invitation(
            org.Id, email, InvitationScopeType.League,
            Guid.NewGuid(), InvitedRole.Player, Guid.NewGuid());
        invitation.Revoke();
        db.Invitations.Add(invitation);
        await db.SaveChangesAsync();

        var response = await _factory.CreateClient().SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/invitations/{invitation.Id}/accept",
                userId, email: email));

        Assert.Equal(System.Net.HttpStatusCode.Forbidden, response.StatusCode);
    }

    [Fact]
    public async Task GetPendingForEmail_returns_pending_invitations()
    {
        var (org, _) = await SeedOrganizationWithOwner("Pending Org", "pending-org");

        var email = "pending@example.com";
        await SeedInvitation(org.Id, email, InvitedRole.Player);

        var invitationAccepted = await SeedInvitation(org.Id, email, InvitedRole.Player);
        using (var scope = _factory.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
            var tenant = scope.ServiceProvider.GetRequiredService<ITenantContext>();
            ((Infrastructure.Tenancy.HttpTenantContext)tenant).SetTenant(org.Id);
            var inv = await db.Invitations.FindAsync(invitationAccepted.Id);
            inv!.Accept();
            await db.SaveChangesAsync();
        }

        await SeedInvitation(org.Id, "other@example.com", InvitedRole.Player);

        using var verifyScope = _factory.Services.CreateScope();
        var service = verifyScope.ServiceProvider.GetRequiredService<IInvitationService>();
        var pending = await service.GetPendingForEmailAsync(email, CancellationToken.None);

        Assert.Single(pending);
    }

    [Fact]
    public async Task Invitation_is_scoped_to_organization()
    {
        var org1 = new Organization("Org A", "org-a-scoped");
        var org2 = new Organization("Org B", "org-b-scoped");

        using (var scope = _factory.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
            db.Organizations.AddRange(org1, org2);
            await db.SaveChangesAsync();
        }

        var invitation = await SeedInvitation(org1.Id, "scoped@example.com");

        using var verifyScope = _factory.Services.CreateScope();
        var verifyDb = verifyScope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
        var inv = await verifyDb.Invitations.FirstAsync();

        Assert.Equal(org1.Id, inv.OrganizationId);
        Assert.NotEqual(org2.Id, inv.OrganizationId);
    }
}
