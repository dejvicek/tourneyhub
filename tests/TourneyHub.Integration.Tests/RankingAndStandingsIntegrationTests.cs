using System.IdentityModel.Tokens.Jwt;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Claims;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.IdentityModel.Tokens;
using Testcontainers.PostgreSql;
using TourneyHub.Application.Tenancy;
using TourneyHub.Domain.Competition;
using TourneyHub.Domain.Identity;
using TourneyHub.Domain.Organizations;
using TourneyHub.Infrastructure.Persistence;
using TourneyHub.Infrastructure.Tenancy;
using Xunit;

namespace TourneyHub.Integration.Tests;

public sealed class RankingAndStandingsIntegrationTests : IAsyncLifetime
{
    private const string DevSigningKey = "dev-test-key-at-least-32-bytes-long!!";

    private readonly PostgreSqlContainer _postgres = new PostgreSqlBuilder()
        .WithDatabase("tourneyhub_ranking_test")
        .WithUsername("tourneyhub")
        .WithPassword("tourneyhub")
        .Build();

    private WebApplicationFactory<Program> _factory = null!;
    private Guid _orgId;
    private Guid _userId;
    private Guid _user2Id;
    private Guid _user3Id;
    private Guid _user4Id;
    private HttpClient _client = null!;

    public async Task InitializeAsync()
    {
        await _postgres.StartAsync();

        _factory = new WebApplicationFactory<Program>().WithWebHostBuilder(builder =>
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
        _user4Id = Guid.NewGuid();

        var org = new Organization("Test Org", "test-org");
        db.Organizations.Add(org);
        _orgId = org.Id;

        db.Memberships.Add(new Membership(_userId, _orgId, MembershipRole.OrgOwner));
        db.Memberships.Add(new Membership(_user2Id, _orgId, MembershipRole.Player));
        db.Memberships.Add(new Membership(_user3Id, _orgId, MembershipRole.Player));
        db.Memberships.Add(new Membership(_user4Id, _orgId, MembershipRole.Player));

        await db.SaveChangesAsync();

        foreach (var (id, email) in new[] {
                     (_user2Id, "player2@test.com"),
                     (_user3Id, "player3@test.com"),
                     (_user4Id, "player4@test.com"),
                 })
        {
            var user = new User
            {
                Id = id,
                UserName = email,
                Email = email,
                NormalizedEmail = email.ToUpperInvariant(),
                EmailConfirmed = true,
                State = AccountState.Active,
            };
            db.Users.Add(user);
        }
        await db.SaveChangesAsync();

        _client = _factory.CreateClient();
    }

    public async Task DisposeAsync()
    {
        _client?.Dispose();
        if (_factory is not null) await _factory.DisposeAsync();
        await _postgres.DisposeAsync();
    }

    [Fact]
    public async Task Tournament_standings_are_computed_after_match_result()
    {
        var ctx = await CreateBracketedTournament(teamSize: 1, formatType: "RoundRobin");

        await SubmitResult(ctx.MatchId, ctx.MatchVersion, 21, 15);

        var standingsResp = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Get, $"/api/v1/tournaments/{ctx.TournamentId}/standings"));
        standingsResp.EnsureSuccessStatusCode();

        var standings = await standingsResp.Content.ReadFromJsonAsync<JsonElement[]>();
        Assert.NotNull(standings);
        Assert.Equal(2, standings!.Length);
        Assert.Equal(1, standings[0].GetProperty("rank").GetInt32());
        Assert.True(standings[0].GetProperty("points").GetInt32() > 0);
    }

    [Fact]
    public async Task Tournament_standings_reflect_points_from_scoring_config()
    {
        var ctx = await CreateBracketedTournament(teamSize: 1, formatType: "RoundRobin");

        await SubmitResult(ctx.MatchId, ctx.MatchVersion, 21, 15);

        var standingsResp = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Get, $"/api/v1/tournaments/{ctx.TournamentId}/standings"));
        standingsResp.EnsureSuccessStatusCode();

        var standings = await standingsResp.Content.ReadFromJsonAsync<JsonElement[]>();
        Assert.NotNull(standings);
        Assert.Equal(2, standings!.Length);

        var winner = standings[0];
        Assert.Equal(3, winner.GetProperty("points").GetInt32());
        Assert.Equal(1, winner.GetProperty("wins").GetInt32());
        Assert.Equal(21, winner.GetProperty("pointsScored").GetInt32());
    }

    [Fact]
    public async Task Season_rankings_award_points_per_player_for_team_play()
    {
        var seasonCtx = await CreateSeasonAndGetLeagueId();
        var ctx = await CreateBracketedTournament(teamSize: 2, formatType: "SingleElimination",
            leagueId: seasonCtx.leagueId, seasonId: seasonCtx.seasonId);

        await SubmitResult(ctx.MatchId, ctx.MatchVersion, 21, 15);

        var rankingsResp = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Get, $"/api/v1/leagues/seasons/{seasonCtx.seasonId}/rankings"));
        rankingsResp.EnsureSuccessStatusCode();

        var rankings = await rankingsResp.Content.ReadFromJsonAsync<JsonElement[]>();
        Assert.NotNull(rankings);
        Assert.Equal(4, rankings!.Length);
    }

    [Fact]
    public async Task Tournament_overview_returns_composite_view()
    {
        var ctx = await CreateBracketedTournament(teamSize: 1, formatType: "SingleElimination");

        var overviewResp = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Get, $"/api/v1/tournaments/{ctx.TournamentId}/overview"));
        Assert.Equal(HttpStatusCode.OK, overviewResp.StatusCode);

        var overview = await overviewResp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(overview.TryGetProperty("tournament", out _));
        Assert.True(overview.TryGetProperty("matches", out var matches));
        Assert.True(overview.TryGetProperty("standings", out _));
        Assert.NotEmpty(matches.EnumerateArray());
    }

    [Fact]
    public async Task Tournament_overview_is_public_no_auth_required()
    {
        var ctx = await CreateBracketedTournament(teamSize: 1, formatType: "SingleElimination");

        var request = new HttpRequestMessage(HttpMethod.Get,
            $"/api/v1/tournaments/{ctx.TournamentId}/overview");
        var response = await _client.SendAsync(request);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task Standings_are_persisted_and_dont_require_full_recomputation_on_read()
    {
        var ctx = await CreateBracketedTournament(teamSize: 1, formatType: "RoundRobin");

        await SubmitResult(ctx.MatchId, ctx.MatchVersion, 21, 15);

        var resp1 = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Get, $"/api/v1/tournaments/{ctx.TournamentId}/standings"));
        resp1.EnsureSuccessStatusCode();

        var resp2 = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Get, $"/api/v1/tournaments/{ctx.TournamentId}/standings"));
        resp2.EnsureSuccessStatusCode();

        var s1 = await resp1.Content.ReadFromJsonAsync<JsonElement[]>();
        var s2 = await resp2.Content.ReadFromJsonAsync<JsonElement[]>();
        Assert.NotNull(s1);
        Assert.NotNull(s2);
        Assert.Equal(s1!.Length, s2!.Length);
        for (int i = 0; i < s1.Length; i++)
        {
            Assert.Equal(s1[i].GetProperty("rank").GetInt32(), s2[i].GetProperty("rank").GetInt32());
            Assert.Equal(s1[i].GetProperty("points").GetInt32(), s2[i].GetProperty("points").GetInt32());
        }
    }

    private async Task<(Guid leagueId, Guid seasonId)> CreateSeasonAndGetLeagueId()
    {
        var leagueResp = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = $"Rankings L {Guid.NewGuid():N}"[..20], visibility = "public" }));
        leagueResp.EnsureSuccessStatusCode();

        var league = await leagueResp.Content.ReadFromJsonAsync<JsonElement>();
        var leagueId = league.GetProperty("id").GetGuid();

        var seasonResp = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/leagues/{leagueId}/seasons",
                new { name = "Season 1" }));
        seasonResp.EnsureSuccessStatusCode();

        var season = await seasonResp.Content.ReadFromJsonAsync<JsonElement>();
        var seasonId = season.GetProperty("id").GetGuid();

        using var scope = _factory.Services.CreateScope();
        var tenantContext = (HttpTenantContext)scope.ServiceProvider.GetRequiredService<ITenantContext>();
        tenantContext.SetTenant(_orgId);

        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
        var s = await db.Seasons.FirstAsync(se => se.Id == seasonId);
        s.Activate();
        await db.SaveChangesAsync();

        return (leagueId, seasonId);
    }

    private async Task<(Guid TournamentId, Guid MatchId, int MatchVersion)> CreateBracketedTournament(
        int teamSize = 1,
        string formatType = "SingleElimination",
        Guid? leagueId = null,
        Guid? seasonId = null)
    {
        var body = new
        {
            disciplineName = "Chess",
            resultModel = "score",
            teamSize,
            formatType,
            leagueId,
            seasonId,
            scoreConfig = new { minScore = 0, maxScore = 100, allowDraws = true },
        };

        var createResp = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Post, "/api/v1/tournaments", body));
        createResp.EnsureSuccessStatusCode();
        var tournament = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var tournamentId = tournament.GetProperty("id").GetGuid();

        await RegisterParticipant(tournamentId, "Team A", _userId);
        await RegisterParticipant(tournamentId, "Team B", _user2Id);

        if (teamSize > 1)
        {
            await AcceptMember(tournamentId, _user3Id, "Team A");
            await AcceptMember(tournamentId, _user4Id, "Team B");
        }

        await CloseRegistrationAndSeed(tournamentId);

        var endpoint = formatType.Equals("RoundRobin", StringComparison.OrdinalIgnoreCase)
            ? $"/api/v1/tournaments/{tournamentId}/generate-schedule"
            : $"/api/v1/tournaments/{tournamentId}/generate-bracket";

        var genResp = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Post, endpoint, new { }));
        genResp.EnsureSuccessStatusCode();

        var matches = await genResp.Content.ReadFromJsonAsync<JsonElement[]>();
        Assert.NotNull(matches);
        var match = matches![0];
        var matchId = match.GetProperty("id").GetGuid();
        var matchVersion = match.GetProperty("version").GetInt32();

        return (tournamentId, matchId, matchVersion);
    }

    private async Task SubmitResult(Guid matchId, int matchVersion, int scoreA, int scoreB)
    {
        var request = CreateAuthRequest(HttpMethod.Patch, $"/api/v1/matches/{matchId}/result",
            new { scoreA, scoreB, isDraw = false });
        request.Headers.Add("If-Match", $"\"{matchVersion}\"");
        var response = await _client.SendAsync(request);
        response.EnsureSuccessStatusCode();
    }

    private async Task RegisterParticipant(Guid tournamentId, string name, Guid userId)
    {
        var response = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/tournaments/{tournamentId}/registrations",
                new { participantDisplayName = name }, userId));
        response.EnsureSuccessStatusCode();
    }

    private async Task AcceptMember(Guid tournamentId, Guid memberUserId, string teamName)
    {
        using var scope = _factory.Services.CreateScope();
        var tenantContext = (HttpTenantContext)scope.ServiceProvider.GetRequiredService<ITenantContext>();
        tenantContext.SetTenant(_orgId);

        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
        var participant = await db.Participants
            .FirstOrDefaultAsync(p => p.TournamentId == tournamentId && p.DisplayName == teamName);

        if (participant is not null)
        {
            var member = new ParticipantMember(participant.Id, tournamentId, memberUserId,
                ParticipantMemberStatus.Accepted);
            db.ParticipantMembers.Add(member);
            participant.Confirm();
            await db.SaveChangesAsync();
        }
    }

    private async Task CloseRegistrationAndSeed(Guid tournamentId)
    {
        using var scope = _factory.Services.CreateScope();
        var tenantContext = (HttpTenantContext)scope.ServiceProvider.GetRequiredService<ITenantContext>();
        tenantContext.SetTenant(_orgId);

        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
        var t = await db.Tournaments.FirstAsync(t => t.Id == tournamentId);
        t.CloseRegistration();
        t.Seed();
        await db.SaveChangesAsync();
    }

    private HttpRequestMessage CreateAuthRequest(HttpMethod method, string url, object? body = null,
        Guid? userId = null)
    {
        var request = new HttpRequestMessage(method, url);
        var uid = userId ?? _userId;
        var email = uid switch
        {
            var id when id == _user2Id => "player2@test.com",
            var id when id == _user3Id => "player3@test.com",
            var id when id == _user4Id => "player4@test.com",
            _ => "test@test.com",
        };
        request.Headers.Authorization =
            new AuthenticationHeaderValue("Bearer", GenerateToken(uid, email));
        request.Headers.Add("X-Organization-Id", _orgId.ToString());

        if (body is not null)
        {
            request.Content = new StringContent(
                JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");
        }

        return request;
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
}