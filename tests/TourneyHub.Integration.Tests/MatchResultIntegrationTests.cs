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

public sealed class MatchResultIntegrationTests : IAsyncLifetime
{
    private const string DevSigningKey = "dev-test-key-at-least-32-bytes-long!!";

    private readonly PostgreSqlContainer _postgres = new PostgreSqlBuilder()
        .WithDatabase("tourneyhub_matchresult_test")
        .WithUsername("tourneyhub")
        .WithPassword("tourneyhub")
        .Build();

    private WebApplicationFactory<Program> _factory = null!;
    private Guid _orgId;
    private Guid _userId;
    private Guid _user2Id;
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

        var org = new Organization("Test Org", "test-org");
        db.Organizations.Add(org);
        _orgId = org.Id;

        db.Memberships.Add(new Membership(_userId, _orgId, MembershipRole.OrgOwner));
        db.Memberships.Add(new Membership(_user2Id, _orgId, MembershipRole.Player));

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
        db.Users.Add(user2);
        await db.SaveChangesAsync();

        _client = _factory.CreateClient();
    }

    public async Task DisposeAsync()
    {
        _client?.Dispose();
        if (_factory is not null) await _factory.DisposeAsync();
        await _postgres.DisposeAsync();
    }

    // ── Result submission ────────────────────────────────────────

    [Fact]
    public async Task Submit_result_for_bracket_match_returns_200_and_advances_winner()
    {
        var ctx = await CreateBracketedTournament();

        var request = CreateAuthRequest(HttpMethod.Patch, $"/api/v1/matches/{ctx.MatchId}/result",
            new { scoreA = 21, scoreB = 15, isDraw = false });
        request.Headers.Add("If-Match", $"\"{ctx.MatchVersion}\"");

        var response = await _client.SendAsync(request);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var result = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Completed", result.GetProperty("state").GetString());
        Assert.True(result.TryGetProperty("winnerId", out var w) && w.ValueKind != JsonValueKind.Null);
    }

    [Fact]
    public async Task Submit_result_with_winner_model_requires_winner()
    {
        var ctx = await CreateBracketedTournament(resultModel: ResultModel.Winner);

        var response = await _client.SendAsync(
            CreateAuthRequestWithEtag(HttpMethod.Patch, $"/api/v1/matches/{ctx.MatchId}/result",
                new { isDraw = false }, ctx.MatchVersion));

        Assert.Equal(HttpStatusCode.UnprocessableEntity, response.StatusCode);
        var problem = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Contains("winner_mismatch", problem.GetProperty("code").GetString());
    }

    [Fact]
    public async Task Submit_draw_when_not_allowed_returns_422()
    {
        var ctx = await CreateBracketedTournament(
            scoreConfig: new { minScore = 0, maxScore = 100, allowDraws = false });

        var response = await _client.SendAsync(
            CreateAuthRequestWithEtag(HttpMethod.Patch, $"/api/v1/matches/{ctx.MatchId}/result",
                new { scoreA = 10, scoreB = 10, isDraw = true }, ctx.MatchVersion));

        Assert.Equal(HttpStatusCode.UnprocessableEntity, response.StatusCode);
        var problem = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Contains("draws_not_allowed", problem.GetProperty("code").GetString());
    }

    [Fact]
    public async Task Submit_result_with_winner_mismatch_returns_422()
    {
        var ctx = await CreateBracketedTournament();

        var response = await _client.SendAsync(
            CreateAuthRequestWithEtag(HttpMethod.Patch, $"/api/v1/matches/{ctx.MatchId}/result",
                new { scoreA = 15, scoreB = 21, winnerId = ctx.ParticipantAId, isDraw = false }, ctx.MatchVersion));

        Assert.Equal(HttpStatusCode.UnprocessableEntity, response.StatusCode);
        var problem = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Contains("winner_mismatch", problem.GetProperty("code").GetString());
    }

    [Fact]
    public async Task Submit_result_without_if_match_returns_428()
    {
        var ctx = await CreateBracketedTournament();

        var response = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Patch, $"/api/v1/matches/{ctx.MatchId}/result",
                new { scoreA = 21, scoreB = 15, isDraw = false }));

        Assert.Equal(428, (int)response.StatusCode);
    }

    [Fact]
    public async Task Submit_result_with_stale_etag_returns_409()
    {
        var ctx = await CreateBracketedTournament();

        var response = await _client.SendAsync(
            CreateAuthRequestWithEtag(HttpMethod.Patch, $"/api/v1/matches/{ctx.MatchId}/result",
                new { scoreA = 21, scoreB = 15, isDraw = false }, 999));

        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
        var problem = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Contains("concurrency_conflict", problem.GetProperty("code").GetString());
    }

    [Fact]
    public async Task Submit_result_edit_succeeds()
    {
        var ctx = await CreateBracketedTournament();

        var resp1 = await _client.SendAsync(
            CreateAuthRequestWithEtag(HttpMethod.Patch, $"/api/v1/matches/{ctx.MatchId}/result",
                new { scoreA = 21, scoreB = 15, isDraw = false }, ctx.MatchVersion));
        Assert.Equal(HttpStatusCode.OK, resp1.StatusCode);
        var m1 = await resp1.Content.ReadFromJsonAsync<JsonElement>();

        var newVersion = m1.GetProperty("version").GetInt32();

        var resp2 = await _client.SendAsync(
            CreateAuthRequestWithEtag(HttpMethod.Patch, $"/api/v1/matches/{ctx.MatchId}/result",
                new { scoreA = 18, scoreB = 21, isDraw = false }, newVersion));
        Assert.Equal(HttpStatusCode.OK, resp2.StatusCode);

        var final = await resp2.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Completed", final.GetProperty("state").GetString());
    }

    // ── Forfeit ──────────────────────────────────────────────────

    [Fact]
    public async Task Forfeit_match_returns_200_and_advances_opponent()
    {
        var ctx = await CreateBracketedTournament();

        var response = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/matches/{ctx.MatchId}/forfeit",
                new { forfeitedParticipantId = ctx.ParticipantAId }));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var result = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Completed", result.GetProperty("state").GetString());
        Assert.Equal(ctx.ParticipantBId.ToString(), result.GetProperty("winnerId").GetString());
    }

    [Fact]
    public async Task Forfeit_non_participant_returns_422()
    {
        var ctx = await CreateBracketedTournament();

        var response = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/matches/{ctx.MatchId}/forfeit",
                new { forfeitedParticipantId = Guid.NewGuid() }));

        Assert.Equal(HttpStatusCode.UnprocessableEntity, response.StatusCode);
    }

    // ── Withdrawal ───────────────────────────────────────────────

    [Fact]
    public async Task Withdraw_participant_cancels_remaining_matches()
    {
        var ctx = await CreateBracketedTournament();

        var response = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/participants/{ctx.ParticipantAId}/withdraw"));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task Withdraw_nonexistent_participant_returns_404()
    {
        var response = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/participants/{Guid.NewGuid()}/withdraw"));

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    // ── Tournament completion ────────────────────────────────────

    [Fact]
    public async Task Final_match_completion_completes_tournament()
    {
        var ctx = await CreateBracketedTournament();

        var request = CreateAuthRequest(HttpMethod.Patch, $"/api/v1/matches/{ctx.MatchId}/result",
            new { scoreA = 21, scoreB = 15, isDraw = false });
        request.Headers.Add("If-Match", $"\"{ctx.MatchVersion}\"");

        var response = await _client.SendAsync(request);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var tournamentResp = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Get, $"/api/v1/tournaments/{ctx.TournamentId}"));
        var tournament = await tournamentResp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("completed", tournament.GetProperty("state").GetString());
    }

    // ── Helpers ──────────────────────────────────────────────────

    private async Task<BracketedTournament> CreateBracketedTournament(
        ResultModel resultModel = ResultModel.Score,
        object? scoreConfig = null)
    {
        var isScoreModel = resultModel == ResultModel.Score;
        var createBody = new
        {
            disciplineName = "Chess",
            resultModel = isScoreModel ? "score" : "winner",
            teamSize = 1,
            formatType = "SingleElimination",
            scoreConfig = isScoreModel ? (scoreConfig ?? new { minScore = 0, maxScore = 100, allowDraws = true }) : null,
        };

        var createResp = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Post, "/api/v1/tournaments", createBody));
        createResp.EnsureSuccessStatusCode();
        var tournament = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var tournamentId = tournament.GetProperty("id").GetGuid();

        await RegisterParticipant(tournamentId, "Player 1", _userId);
        await RegisterParticipant(tournamentId, "Player 2", _user2Id);

        await CloseRegistrationAndSeed(tournamentId);

        var bracketResp = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/tournaments/{tournamentId}/generate-bracket",
                new { }));
        bracketResp.EnsureSuccessStatusCode();

        var matches = await bracketResp.Content.ReadFromJsonAsync<JsonElement[]>();
        var match = matches![0];
        var matchId = match.GetProperty("id").GetGuid();
        var matchVersion = match.GetProperty("version").GetInt32();
        var participantAId = match.TryGetProperty("participantA", out var pa) && pa.ValueKind != JsonValueKind.Null
            ? pa.GetGuid() : Guid.Empty;
        var participantBId = match.TryGetProperty("participantB", out var pb) && pb.ValueKind != JsonValueKind.Null
            ? pb.GetGuid() : Guid.Empty;

        return new BracketedTournament(tournamentId, matchId, matchVersion, participantAId, participantBId);
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

    private async Task RegisterParticipant(Guid tournamentId, string name, Guid userId)
    {
        var response = await _client.SendAsync(
            CreateAuthRequest(HttpMethod.Post, $"/api/v1/tournaments/{tournamentId}/registrations",
                new { participantDisplayName = name }, userId));
        response.EnsureSuccessStatusCode();
    }

    private HttpRequestMessage CreateAuthRequest(HttpMethod method, string url, object? body = null, Guid? userId = null)
    {
        var request = new HttpRequestMessage(method, url);
        var uid = userId ?? _userId;
        var email = uid == _user2Id ? "player2@test.com" : "test@test.com";
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", GenerateToken(uid, email));
        request.Headers.Add("X-Organization-Id", _orgId.ToString());

        if (body is not null)
        {
            request.Content = new StringContent(
                JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");
        }

        return request;
    }

    private HttpRequestMessage CreateAuthRequestWithEtag(HttpMethod method, string url, object? body, int etag)
    {
        var request = CreateAuthRequest(method, url, body);
        request.Headers.Add("If-Match", $"\"{etag}\"");
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

    private sealed record BracketedTournament(
        Guid TournamentId,
        Guid MatchId,
        int MatchVersion,
        Guid ParticipantAId,
        Guid ParticipantBId);
}