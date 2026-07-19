var builder = WebApplication.CreateBuilder(args);

builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// Health checks — /live is a liveness ping; /ready checks DB + Redis (AGENTS.md §8).
builder.Services.AddHealthChecks()
    .AddNpgSql(
        npgsqlDataSource: builder.Configuration.GetConnectionString("Postgres")!,
        name: "postgres",
        tags: ["ready"])
    .AddRedis(
        redisConnectionString: builder.Configuration.GetConnectionString("Redis")!,
        name: "redis",
        tags: ["ready"]);

// Composition root. Wire per slice (AGENTS.md §6):
//   - AddDbContext<TourneyHubDbContext>(o => o.UseNpgsql(cfg.GetConnectionString("Postgres")))
//   - Redis (cache + SignalR backplane), ASP.NET Core Identity, JWT auth, SignalR hubs.
//   - Tenant-scope resolver + authorization policies (NFR-004, NFR-024).

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

// Health/readiness endpoints (NFR-014).
// /health/live — liveness ping (always 200 if server is running).
app.MapGet("/health/live", () => Results.Ok(new { status = "live" }));

// /health/ready — readiness probe; checks DB + Redis.
// Returns 503 if any tagged dependency is unhealthy.
app.MapHealthChecks("/health/ready", new()
{
    Predicate = check => check.Tags.Contains("ready"),
    ResultStatusCodes =
    {
        [Microsoft.Extensions.Diagnostics.HealthChecks.HealthStatus.Healthy] = StatusCodes.Status200OK,
        [Microsoft.Extensions.Diagnostics.HealthChecks.HealthStatus.Degraded] = StatusCodes.Status200OK,
        [Microsoft.Extensions.Diagnostics.HealthChecks.HealthStatus.Unhealthy] = StatusCodes.Status503ServiceUnavailable,
    },
});

// Placeholder API root until controllers are generated from api/openapi.yaml.
app.MapGet("/api/v1/ping", () => Results.Ok(new { service = "TourneyHub", version = "v1" }));

app.Run();

// Exposed for WebApplicationFactory-based integration tests (Testcontainers).
public partial class Program { }
