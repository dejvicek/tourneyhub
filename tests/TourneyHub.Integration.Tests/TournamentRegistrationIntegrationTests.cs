using System.IdentityModel.Tokens.Jwt;
using System.Net.Http.Json;
using System.Net;
using System.Security.Claims;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.IdentityModel.Tokens;
using Testcontainers.PostgreSql;
using TourneyHub.Domain.Competition;
using TourneyHub.Domain.Identity;
using TourneyHub.Domain.Organizations;
using TourneyHub.Infrastructure.Persistence;
using Xunit;

namespace TourneyHub.Integration.Tests;

public sealed class TournamentRegistrationIntegrationTests : IAsyncLifetime
{
    private const string DevSigningKey = "dev-test-key-at-least-32-bytes-long!!";

    private readonly PostgreSqlContainer _postgres = new PostgreSqlBuilder()
        .WithDatabase("tourneyhub_tournament_test")
        .WithUsername("tourneyhub")
        .WithPassword("tourneyhub")
        .Build();

    private WebApplicationFactory<Program> _factory = null!;
    private Guid _orgId;
    private Guid _userId;
    private Guid _user2Id;
    private Guid _user3Id;
    private HttpClient _client = null!;

    private static readonly string[] Player2EmailArray = ["player2@test.com"];

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

        _orgId = Guid.NewGuid();
        _userId = Guid.NewGuid();
        _user2Id = Guid.NewGuid();
        _user3Id = Guid.NewGuid();

        var org = new Organization("Test Org", "test-org");
        db.Organizations.Add(org);
        _orgId = org.Id;

        db.Memberships.Add(new Membership(_userId, _orgId, MembershipRole.OrgOwner));
        db.Memberships.Add(new Membership(_user2Id, _orgId, MembershipRole.Player));
        db.Memberships.Add(new Membership(_user3Id, _orgId, MembershipRole.Player));

        await db.SaveChangesAsync();

        var user2 = new User
        {
            Id = _user2Id,
            UserName = "player2@test.com",
            Email = "player2@test.com",
            NormalizedEmail = "PLAYER2@TEST.COM",
            EmailConfirmed = true,
            State = AccountState.Active,
        };

        var user3 = new User
        {
            Id = _user3Id,
            UserName = "player3@test.com",
            Email = "player3@test.com",
            NormalizedEmail = "PLAYER3@TEST.COM",
            EmailConfirmed = true,
            State = AccountState.Active,
        };

        db.Users.AddRange(user2, user3);
        await db.SaveChangesAsync();

        _client = _factory.CreateClient();
    }

    public async Task DisposeAsync()
    {
        if (_factory is not null) await _factory.DisposeAsync();
        await _postgres.DisposeAsync();
    }

    private static string GenerateToken(Guid userId, string email = "test@test.com")
    {
        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(DevSigningKey));
        var credentials = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);

        var claims = new[]
        {
            new Claim(JwtRegisteredClaimNames.Sub, userId.ToString()),
            new Claim(JwtRegisteredClaimNames.Email, email),
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

    private HttpRequestMessage CreateRequest(HttpMethod method, string url, object? body = null, Guid? userId = null)
    {
        var request = new HttpRequestMessage(method, url);
        var uid = userId ?? _userId;
        var email = uid == _user2Id ? "player2@test.com" : uid == _user3Id ? "player3@test.com" : $"{uid}@test.com";
        request.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", GenerateToken(uid, email));
        request.Headers.Add("X-Organization-Id", _orgId.ToString());

        if (body is not null)
        {
            request.Content = new StringContent(
                JsonSerializer.Serialize(body),
                Encoding.UTF8,
                "application/json");
        }

        return request;
    }

    // ── Tournament Creation ──────────────────────────────────────────

    [Fact]
    public async Task Create_tournament_returns_201()
    {
        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/tournaments",
                new
                {
                    disciplineName = "Badminton",
                    resultModel = "winner",
                    teamSize = 1,
                    formatType = "SingleElimination",
                }));

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);

        var tournament = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Badminton", tournament.GetProperty("disciplineName").GetString());
        Assert.Equal("winner", tournament.GetProperty("resultModel").GetString());
        Assert.Equal(1, tournament.GetProperty("teamSize").GetInt32());
        Assert.Equal("singleelimination", tournament.GetProperty("formatType").GetString());
        Assert.Equal("registrationopen", tournament.GetProperty("state").GetString());
    }

    [Fact]
    public async Task Create_tournament_with_league_returns_201()
    {
        var leagueResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "My League", visibility = "public" }));

        var league = await leagueResp.Content.ReadFromJsonAsync<JsonElement>();
        var leagueId = league.GetProperty("id").GetGuid();

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/tournaments",
                new
                {
                    disciplineName = "Chess",
                    resultModel = "score",
                    teamSize = 1,
                    formatType = "RoundRobin",
                    leagueId = leagueId.ToString(),
                }));

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);

        var tournament = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(leagueId, tournament.GetProperty("leagueId").GetGuid());
    }

    [Fact]
    public async Task Create_tournament_with_invalid_league_returns_404()
    {
        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/tournaments",
                new
                {
                    disciplineName = "Chess",
                    resultModel = "winner",
                    teamSize = 1,
                    formatType = "SingleElimination",
                    leagueId = Guid.NewGuid().ToString(),
                }));

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task Create_tournament_team_size_validated()
    {
        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/tournaments",
                new
                {
                    disciplineName = "Badminton",
                    resultModel = "winner",
                    teamSize = 0,
                    formatType = "SingleElimination",
                }));

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    // ── Registration ─────────────────────────────────────────────────

    [Fact]
    public async Task Register_solo_participant_returns_201()
    {
        var tournamentResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/tournaments",
                new
                {
                    disciplineName = "Badminton",
                    resultModel = "winner",
                    teamSize = 1,
                    formatType = "SingleElimination",
                }));

        var tournament = await tournamentResp.Content.ReadFromJsonAsync<JsonElement>();
        var tournamentId = tournament.GetProperty("id").GetGuid();

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/tournaments/{tournamentId}/registrations",
                new { participantDisplayName = "Alex" }));

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);

        var participant = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(tournamentId, participant.GetProperty("tournamentId").GetGuid());
        Assert.Equal("Alex", participant.GetProperty("displayName").GetString());
        Assert.Equal("confirmed", participant.GetProperty("status").GetString());
    }

    [Fact]
    public async Task Register_team_participant_starts_incomplete()
    {
        var tournamentResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/tournaments",
                new
                {
                    disciplineName = "Foosball",
                    resultModel = "winner",
                    teamSize = 2,
                    formatType = "SingleElimination",
                }));

        var tournament = await tournamentResp.Content.ReadFromJsonAsync<JsonElement>();
        var tournamentId = tournament.GetProperty("id").GetGuid();

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/tournaments/{tournamentId}/registrations",
                new
                {
                    participantDisplayName = "Team Alpha",
                    rosterInviteEmails = Player2EmailArray,
                }));

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);

        var participant = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("incomplete", participant.GetProperty("status").GetString());
    }

    [Fact]
    public async Task Register_with_duplicate_player_rejected()
    {
        var tournamentResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/tournaments",
                new
                {
                    disciplineName = "Badminton",
                    resultModel = "winner",
                    teamSize = 1,
                    formatType = "SingleElimination",
                }));

        var tournament = await tournamentResp.Content.ReadFromJsonAsync<JsonElement>();
        var tournamentId = tournament.GetProperty("id").GetGuid();

        await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/tournaments/{tournamentId}/registrations",
                new { participantDisplayName = "Alex" }));

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/tournaments/{tournamentId}/registrations",
                new { participantDisplayName = "Alex2" }));

        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
    }

    [Fact]
    public async Task Cannot_invite_player_already_in_tournament()
    {
        var tournamentResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/tournaments",
                new
                {
                    disciplineName = "Foosball",
                    resultModel = "winner",
                    teamSize = 2,
                    formatType = "SingleElimination",
                }));

        var tournament = await tournamentResp.Content.ReadFromJsonAsync<JsonElement>();
        var tournamentId = tournament.GetProperty("id").GetGuid();

        await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/tournaments/{tournamentId}/registrations",
                new
                {
                    participantDisplayName = "Team Alpha",
                    rosterInviteEmails = Player2EmailArray,
                }));

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/tournaments/{tournamentId}/registrations",
                new
                {
                    participantDisplayName = "Team Beta",
                    rosterInviteEmails = Player2EmailArray,
                }));

        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
    }

    [Fact]
    public async Task Registration_fails_when_tournament_not_in_registration_open()
    {
        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/tournaments/{Guid.NewGuid()}/registrations",
                new { participantDisplayName = "Ghost" }));

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Fact]
    public async Task Registration_full_when_capacity_reached()
    {
        var tournamentResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/tournaments",
                new
                {
                    disciplineName = "Badminton",
                    resultModel = "winner",
                    teamSize = 1,
                    formatType = "SingleElimination",
                    maxParticipants = 1,
                }));

        var tournament = await tournamentResp.Content.ReadFromJsonAsync<JsonElement>();
        var tournamentId = tournament.GetProperty("id").GetGuid();

        await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/tournaments/{tournamentId}/registrations",
                new { participantDisplayName = "Player1" }));

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/tournaments/{tournamentId}/registrations",
                new { participantDisplayName = "Player2" },
                userId: _user2Id));

        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
    }

    // ── Roster Accept ────────────────────────────────────────────────

    [Fact]
    public async Task Accept_roster_invite_confirms_participant()
    {
        var tournamentResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/tournaments",
                new
                {
                    disciplineName = "Foosball",
                    resultModel = "winner",
                    teamSize = 2,
                    formatType = "SingleElimination",
                }));

        var tournament = await tournamentResp.Content.ReadFromJsonAsync<JsonElement>();
        var tournamentId = tournament.GetProperty("id").GetGuid();

        var regResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/tournaments/{tournamentId}/registrations",
                new
                {
                    participantDisplayName = "Team Alpha",
                    rosterInviteEmails = Player2EmailArray,
                }));

        var participant = await regResp.Content.ReadFromJsonAsync<JsonElement>();
        var participantId = participant.GetProperty("id").GetGuid();
        Assert.Equal("incomplete", participant.GetProperty("status").GetString());

        var acceptResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/participants/{participantId}/members/accept",
                userId: _user2Id));

        Assert.Equal(HttpStatusCode.OK, acceptResp.StatusCode);
    }

    [Fact]
    public async Task Accept_member_not_in_participant_returns_404()
    {
        var tournamentResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/tournaments",
                new
                {
                    disciplineName = "Foosball",
                    resultModel = "winner",
                    teamSize = 2,
                    formatType = "SingleElimination",
                }));

        var tournament = await tournamentResp.Content.ReadFromJsonAsync<JsonElement>();
        var tournamentId = tournament.GetProperty("id").GetGuid();

        var regResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/tournaments/{tournamentId}/registrations",
                new
                {
                    participantDisplayName = "Team Alpha",
                    rosterInviteEmails = Player2EmailArray,
                }));

        var participant = await regResp.Content.ReadFromJsonAsync<JsonElement>();
        var participantId = participant.GetProperty("id").GetGuid();

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/participants/{participantId}/members/accept",
                userId: _user3Id));

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task Get_tournament_returns_with_etag()
    {
        var createResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/tournaments",
                new
                {
                    disciplineName = "Chess",
                    resultModel = "winner",
                    teamSize = 1,
                    formatType = "RoundRobin",
                }));

        var created = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var tournamentId = created.GetProperty("id").GetGuid();

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Get, $"/api/v1/tournaments/{tournamentId}"));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.True(response.Headers.ETag is not null);
    }

    [Fact]
    public async Task List_tournaments_returns_org_tournaments()
    {
        await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/tournaments",
                new
                {
                    disciplineName = "Badminton",
                    resultModel = "winner",
                    teamSize = 1,
                    formatType = "SingleElimination",
                }));

        await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/tournaments",
                new
                {
                    disciplineName = "Chess",
                    resultModel = "score",
                    teamSize = 1,
                    formatType = "RoundRobin",
                }));

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Get, "/api/v1/tournaments"));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var tournaments = await response.Content.ReadFromJsonAsync<JsonElement[]>();
        Assert.NotNull(tournaments);
        Assert.Equal(2, tournaments!.Length);
    }

    [Fact]
    public async Task Get_non_existent_tournament_returns_404()
    {
        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Get, $"/api/v1/tournaments/{Guid.NewGuid()}"));

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }
}
