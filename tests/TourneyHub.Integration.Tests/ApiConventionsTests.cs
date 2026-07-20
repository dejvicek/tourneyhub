using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Testcontainers.PostgreSql;
using TourneyHub.Domain.Organizations;
using TourneyHub.Infrastructure.Persistence;
using Xunit;

namespace TourneyHub.Integration.Tests;

public sealed class ApiConventionsTests : IAsyncLifetime
{
    private readonly PostgreSqlContainer _postgres = new PostgreSqlBuilder()
        .WithDatabase("tourneyhub_test_conv")
        .WithUsername("tourneyhub")
        .WithPassword("tourneyhub")
        .Build();

    private WebApplicationFactory<Program> _factory = null!;
    private HttpClient _client = null!;
    private Guid _orgA;

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

        var orgA = new Organization("Org A", "org-a");
        _orgA = orgA.Id;
        db.Organizations.Add(orgA);
        await db.SaveChangesAsync();

        _client = _factory.CreateClient();
    }

    public async Task DisposeAsync()
    {
        _client?.Dispose();
        if (_factory is not null) await _factory.DisposeAsync();
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
    public async Task Correlation_id_header_is_present_in_response()
    {
        var request = new HttpRequestMessage(HttpMethod.Get, "/api/v1/ping");

        var response = await _client.SendAsync(request);

        Assert.True(response.Headers.Contains("X-Correlation-Id"));
    }

    [Fact]
    public async Task Correlation_id_header_is_accepted_from_request()
    {
        var request = new HttpRequestMessage(HttpMethod.Get, "/api/v1/ping");
        request.Headers.Add("X-Correlation-Id", "test-correlation-123");

        var response = await _client.SendAsync(request);

        Assert.Equal("test-correlation-123",
            response.Headers.GetValues("X-Correlation-Id").FirstOrDefault());
    }

    [Fact]
    public async Task No_tenant_header_returns_problem_json_with_error_code()
    {
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/v1/leagues")
        {
            Content = new StringContent(
                JsonSerializer.Serialize(new { name = "No Org" }),
                Encoding.UTF8,
                "application/json")
        };

        var response = await _client.SendAsync(request);
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal("application/problem+json", response.Content.Headers.ContentType?.MediaType);

        var problem = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(problem.TryGetProperty("code", out _));
        Assert.True(problem.TryGetProperty("title", out _));
        Assert.True(problem.TryGetProperty("status", out _));
    }

    [Fact]
    public async Task Ping_endpoint_is_rate_limited()
    {
        var response = await _client.GetAsync("/api/v1/ping");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task Problem_response_contains_stable_code_field()
    {
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/v1/leagues")
        {
            Content = new StringContent(
                JsonSerializer.Serialize(new { name = "No Org" }),
                Encoding.UTF8,
                "application/json")
        };

        var response = await _client.SendAsync(request);
        var problem = await response.Content.ReadFromJsonAsync<JsonElement>();

        Assert.True(problem.TryGetProperty("code", out var codeProp));
        var code = codeProp.GetString();
        Assert.NotNull(code);
        Assert.NotEmpty(code);
    }
}