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
using TourneyHub.Domain.Organizations;
using TourneyHub.Infrastructure.Persistence;
using Xunit;

namespace TourneyHub.Integration.Tests;

public sealed class LeagueSeasonIntegrationTests : IAsyncLifetime
{
    private const string DevSigningKey = "dev-test-key-at-least-32-bytes-long!!";

    private readonly PostgreSqlContainer _postgres = new PostgreSqlBuilder()
        .WithDatabase("tourneyhub_league_test")
        .WithUsername("tourneyhub")
        .WithPassword("tourneyhub")
        .Build();

    private WebApplicationFactory<Program> _factory = null!;
    private Guid _orgId;
    private Guid _userId;
    private HttpClient _client = null!;

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

        var org = new Organization("Test Org", "test-org");
        db.Organizations.Add(org);
        _orgId = org.Id;

        db.Memberships.Add(new Membership(_userId, _orgId, MembershipRole.OrgOwner));
        await db.SaveChangesAsync();

        _client = _factory.CreateClient();
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

    private HttpRequestMessage CreateRequest(HttpMethod method, string url, object? body = null)
    {
        var request = new HttpRequestMessage(method, url);
        request.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", GenerateToken(_userId));
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

    private static StringContent JsonContent(object body) =>
        new(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");

    [Fact]
    public async Task Create_league_returns_201()
    {
        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "My League", visibility = "public" }));

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);

        var league = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("My League", league.GetProperty("name").GetString());
        Assert.Equal("public", league.GetProperty("visibility").GetString());
        Assert.Equal("active", league.GetProperty("state").GetString());
        Assert.NotEmpty(league.GetProperty("slug").GetString()!);
    }

    [Fact]
    public async Task Create_league_auto_generates_slug()
    {
        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "My Awesome League", visibility = "public" }));

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);

        var league = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("my-awesome-league", league.GetProperty("slug").GetString());
    }

    [Fact]
    public async Task Create_league_with_custom_slug()
    {
        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "Custom Slug League", visibility = "public", slug = "custom-slug" }));

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);

        var league = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("custom-slug", league.GetProperty("slug").GetString());
    }

    [Fact]
    public async Task Create_league_with_duplicate_slug_rejected()
    {
        await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "First League", visibility = "public", slug = "same-slug" }));

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "Second League", visibility = "public", slug = "same-slug" }));

        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
    }

    [Fact]
    public async Task List_leagues_returns_org_leagues()
    {
        await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "League One", visibility = "public" }));

        await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "League Two", visibility = "private" }));

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Get, "/api/v1/leagues"));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var leagues = await response.Content.ReadFromJsonAsync<JsonElement[]>();
        Assert.NotNull(leagues);
        Assert.Equal(2, leagues!.Length);
    }

    [Fact]
    public async Task Get_league_by_id_returns_with_etag()
    {
        var createResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "Get Me", visibility = "public" }));

        var created = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var leagueId = created.GetProperty("id").GetGuid();

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Get, $"/api/v1/leagues/{leagueId}"));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.True(response.Headers.ETag is not null);
    }

    [Fact]
    public async Task Get_non_existent_league_returns_404()
    {
        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Get, $"/api/v1/leagues/{Guid.NewGuid()}"));

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task Update_league_modifies_fields()
    {
        var createResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "Original", visibility = "public" }));

        var created = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var leagueId = created.GetProperty("id").GetGuid();

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Put, $"/api/v1/leagues/{leagueId}",
                new { name = "Updated", visibility = "private", description = "New desc" }));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var updated = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Updated", updated.GetProperty("name").GetString());
        Assert.Equal("private", updated.GetProperty("visibility").GetString());
        Assert.Equal("New desc", updated.GetProperty("description").GetString());
    }

    [Fact]
    public async Task Archive_and_unarchive_league()
    {
        var createResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "Archivable", visibility = "public" }));

        var created = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var leagueId = created.GetProperty("id").GetGuid();

        var archiveResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/leagues/{leagueId}/archive"));

        Assert.Equal(HttpStatusCode.OK, archiveResp.StatusCode);
        var archived = await archiveResp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("archived", archived.GetProperty("state").GetString());

        var unarchiveResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/leagues/{leagueId}/unarchive"));

        Assert.Equal(HttpStatusCode.OK, unarchiveResp.StatusCode);
        var unarchived = await unarchiveResp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("active", unarchived.GetProperty("state").GetString());
    }

    [Fact]
    public async Task Delete_league_returns_204()
    {
        var createResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "Deletable", visibility = "public" }));

        var created = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var leagueId = created.GetProperty("id").GetGuid();

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Delete, $"/api/v1/leagues/{leagueId}"));

        Assert.Equal(HttpStatusCode.NoContent, response.StatusCode);

        var getResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Get, $"/api/v1/leagues/{leagueId}"));
        Assert.Equal(HttpStatusCode.NotFound, getResp.StatusCode);
    }

    [Fact]
    public async Task Create_season_returns_201()
    {
        var createResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "Seasoned League", visibility = "public" }));

        var league = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var leagueId = league.GetProperty("id").GetGuid();

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/leagues/{leagueId}/seasons",
                new { name = "Season 1" }));

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);

        var season = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Season 1", season.GetProperty("name").GetString());
        Assert.Equal("upcoming", season.GetProperty("state").GetString());
    }

    [Fact]
    public async Task Activate_and_close_season()
    {
        var createResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "Active League", visibility = "public" }));

        var league = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var leagueId = league.GetProperty("id").GetGuid();

        var seasonResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/leagues/{leagueId}/seasons",
                new { name = "Season 1" }));

        var season = await seasonResp.Content.ReadFromJsonAsync<JsonElement>();
        var seasonId = season.GetProperty("id").GetGuid();

        var activateResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/leagues/seasons/{seasonId}/activate"));

        Assert.Equal(HttpStatusCode.OK, activateResp.StatusCode);
        var activated = await activateResp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("active", activated.GetProperty("state").GetString());

        var closeResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/leagues/seasons/{seasonId}/close"));

        Assert.Equal(HttpStatusCode.OK, closeResp.StatusCode);
        var closed = await closeResp.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("closed", closed.GetProperty("state").GetString());
    }

    [Fact]
    public async Task Only_one_active_season_per_league()
    {
        var createResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "Multi Season League", visibility = "public" }));

        var league = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var leagueId = league.GetProperty("id").GetGuid();

        var s1Resp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/leagues/{leagueId}/seasons",
                new { name = "Season 1" }));

        var s1 = await s1Resp.Content.ReadFromJsonAsync<JsonElement>();
        var s1Id = s1.GetProperty("id").GetGuid();

        await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/leagues/seasons/{s1Id}/activate"));

        var s2Resp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/leagues/{leagueId}/seasons",
                new { name = "Season 2" }));

        var s2 = await s2Resp.Content.ReadFromJsonAsync<JsonElement>();
        var s2Id = s2.GetProperty("id").GetGuid();

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/leagues/seasons/{s2Id}/activate"));

        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
    }

    [Fact]
    public async Task Cancel_season()
    {
        var createResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "Cancel League", visibility = "public" }));

        var league = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var leagueId = league.GetProperty("id").GetGuid();

        var seasonResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/leagues/{leagueId}/seasons",
                new { name = "To Cancel" }));

        var season = await seasonResp.Content.ReadFromJsonAsync<JsonElement>();
        var seasonId = season.GetProperty("id").GetGuid();

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/leagues/seasons/{seasonId}/cancel"));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var cancelled = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("cancelled", cancelled.GetProperty("state").GetString());
    }

    [Fact]
    public async Task Cannot_activate_season_in_archived_league()
    {
        var createResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "Will Archive", visibility = "public" }));

        var league = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var leagueId = league.GetProperty("id").GetGuid();

        var seasonResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/leagues/{leagueId}/seasons",
                new { name = "Season 1" }));

        var season = await seasonResp.Content.ReadFromJsonAsync<JsonElement>();
        var seasonId = season.GetProperty("id").GetGuid();

        await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/leagues/{leagueId}/archive"));

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/leagues/seasons/{seasonId}/activate"));

        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
    }

    [Fact]
    public async Task Public_league_accessible_via_slug()
    {
        var createResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "Public League", visibility = "public", slug = "public-league" }));

        createResp.EnsureSuccessStatusCode();

        var publicClient = _factory.CreateClient();
        var response = await publicClient.GetAsync("/api/v1/public/leagues/public-league");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var league = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Public League", league.GetProperty("name").GetString());
    }

    [Fact]
    public async Task Private_league_not_accessible_via_public_slug()
    {
        var createResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "Private League", visibility = "private", slug = "private-league" }));

        createResp.EnsureSuccessStatusCode();

        var publicClient = _factory.CreateClient();
        var response = await publicClient.GetAsync("/api/v1/public/leagues/private-league");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task Unlisted_league_not_in_public_discovery()
    {
        var createResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "Unlisted League", visibility = "unlisted", slug = "unlisted-league" }));

        createResp.EnsureSuccessStatusCode();

        var publicClient = _factory.CreateClient();
        var response = await publicClient.GetAsync("/api/v1/public/leagues/unlisted-league");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task List_seasons_returns_all_seasons_for_league()
    {
        var createResp = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues",
                new { name = "Seasoned", visibility = "public" }));

        var league = await createResp.Content.ReadFromJsonAsync<JsonElement>();
        var leagueId = league.GetProperty("id").GetGuid();

        await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/leagues/{leagueId}/seasons",
                new { name = "S1" }));

        await _client.SendAsync(
            CreateRequest(HttpMethod.Post, $"/api/v1/leagues/{leagueId}/seasons",
                new { name = "S2" }));

        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Get, $"/api/v1/leagues/{leagueId}/seasons"));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var seasons = await response.Content.ReadFromJsonAsync<JsonElement[]>();
        Assert.Equal(2, seasons!.Length);
    }
}
