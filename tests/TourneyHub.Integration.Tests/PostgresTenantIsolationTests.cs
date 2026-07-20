using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Testcontainers.PostgreSql;
using TourneyHub.Domain.Competition;
using TourneyHub.Domain.Organizations;
using TourneyHub.Infrastructure.Persistence;
using Xunit;

namespace TourneyHub.Integration.Tests;

/// <summary>
/// Postgres-backed end-to-end tenant-isolation tests hitting real HTTP endpoints
/// via <see cref="WebApplicationFactory{TEntryPoint}"/>. Two organizations are seeded;
/// each request carries an <c>X-Organization-Id</c> header to resolve the tenant.
/// Asserts no cross-org read/write through the API (NFR-004, NFR-024, FR-152).
/// </summary>
public sealed class PostgresTenantIsolationTests : IAsyncLifetime
{
    private readonly PostgreSqlContainer _postgres = new PostgreSqlBuilder()
        .WithDatabase("tourneyhub_test")
        .WithUsername("tourneyhub")
        .WithPassword("tourneyhub")
        .Build();

    private WebApplicationFactory<Program> _factory = null!;
    private HttpClient _client = null!;

    private Guid _orgA;
    private Guid _orgB;
    private Guid _leagueA;

    public async Task InitializeAsync()
    {
        await _postgres.StartAsync();

        _factory = new WebApplicationFactory<Program>()
            .WithWebHostBuilder(builder =>
            {
                builder.UseSetting("ConnectionStrings:Postgres", _postgres.GetConnectionString());
            });

        // Apply migrations.
        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
        await db.Database.MigrateAsync();

        // Seed two organizations.
        var orgA = new Organization("Org A", "org-a");
        var orgB = new Organization("Org B", "org-b");
        _orgA = orgA.Id;
        _orgB = orgB.Id;

        db.Organizations.AddRange(orgA, orgB);
        await db.SaveChangesAsync();

        _client = _factory.CreateClient();
    }

    public async Task DisposeAsync()
    {
        _client?.Dispose();
        if (_factory is not null)
        {
            await _factory.DisposeAsync();
        }

        await _postgres.DisposeAsync();
    }

    private static HttpRequestMessage CreateRequest(HttpMethod method, string url, Guid orgId, object? body = null)
    {
        var request = new HttpRequestMessage(method, url);
        request.Headers.Add("X-Organization-Id", orgId.ToString());

        if (body is not null)
        {
            var json = JsonSerializer.Serialize(body);
            request.Content = new StringContent(json, Encoding.UTF8, "application/json");
        }

        return request;
    }

    [Fact]
    public async Task Create_league_with_org_header_stamps_and_returns_correct_org()
    {
        var response = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues", _orgA, new { name = "League A" }));

        response.EnsureSuccessStatusCode();
        var content = await response.Content.ReadFromJsonAsync<JsonElement>();
        var orgId = content.GetProperty("organizationId").GetGuid();
        Assert.Equal(_orgA, orgId);
        _leagueA = content.GetProperty("id").GetGuid();
    }

    [Fact]
    public async Task Cross_org_read_via_api_returns_nothing()
    {
        // Create league in Org A first.
        var createResponse = await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues", _orgA, new { name = "League A" }));
        createResponse.EnsureSuccessStatusCode();
        var league = await createResponse.Content.ReadFromJsonAsync<JsonElement>();
        var leagueId = league.GetProperty("id").GetGuid();

        // Fetch as Org B — should return 404 (query filter hides it).
        var getResponse = await _client.SendAsync(
            CreateRequest(HttpMethod.Get, $"/api/v1/leagues/{leagueId}", _orgB));

        Assert.Equal(System.Net.HttpStatusCode.NotFound, getResponse.StatusCode);
    }

    [Fact]
    public async Task List_leagues_returns_only_calling_tenants_rows()
    {
        await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues", _orgA, new { name = "League A" }));
        await _client.SendAsync(
            CreateRequest(HttpMethod.Post, "/api/v1/leagues", _orgB, new { name = "League B" }));

        var listA = await _client.SendAsync(
            CreateRequest(HttpMethod.Get, "/api/v1/leagues", _orgA));
        var itemsA = await listA.Content.ReadFromJsonAsync<JsonElement[]>();
        Assert.All(itemsA!, item => Assert.Equal(_orgA, item.GetProperty("organizationId").GetGuid()));

        var listB = await _client.SendAsync(
            CreateRequest(HttpMethod.Get, "/api/v1/leagues", _orgB));
        var itemsB = await listB.Content.ReadFromJsonAsync<JsonElement[]>();
        Assert.All(itemsB!, item => Assert.Equal(_orgB, item.GetProperty("organizationId").GetGuid()));
    }

    [Fact]
    public async Task Write_without_org_header_fails_closed()
    {
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/v1/leagues")
        {
            Content = new StringContent(
                JsonSerializer.Serialize(new { name = "No Org" }),
                Encoding.UTF8,
                "application/json")
        };

        var response = await _client.SendAsync(request);

        Assert.Equal(System.Net.HttpStatusCode.InternalServerError, response.StatusCode);
    }
}
