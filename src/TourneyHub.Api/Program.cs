using Microsoft.EntityFrameworkCore;
using TourneyHub.Api.Middleware;
using TourneyHub.Application.Tenancy;
using TourneyHub.Domain.Competition;
using TourneyHub.Infrastructure.Persistence;
using TourneyHub.Infrastructure.Tenancy;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// Tenancy: resolve the active organization server-side from the authenticated principal.
// HttpTenantContext is scoped: a fresh instance per request, populated by middleware.
builder.Services.AddHttpContextAccessor();
builder.Services.AddScoped<HttpTenantContext>();
builder.Services.AddScoped<ITenantContext>(sp => sp.GetRequiredService<HttpTenantContext>());

// EF Core + PostgreSQL (NFR-004, TENANCY guardrails §5.1).
builder.Services.AddDbContext<TourneyHubDbContext>(options =>
    options.UseNpgsql(builder.Configuration.GetConnectionString("Postgres")));

// Health checks — /live is a liveness ping; /ready checks DB + Redis (AGENTS.md §8).
builder.Services.AddHealthChecks()
    .AddNpgSql(
        connectionString: builder.Configuration.GetConnectionString("Postgres")!,
        name: "postgres",
        tags: ["ready"])
    .AddRedis(
        redisConnectionString: builder.Configuration.GetConnectionString("Redis")!,
        name: "redis",
        tags: ["ready"]);

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

// Tenant resolution: MUST run after authentication (when wired).
app.UseMiddleware<TenantResolutionMiddleware>();

// Minimal tenant-scoped endpoints for integration-test scaffolding.
// Full controller implementation comes with the Leagues slice (Step 10).
// Auth gate added in Step 05; tenant isolation is enforced via the DbContext query filter
// and the TenantResolutionMiddleware (populated from X-Organization-Id header for now).
var leagues = app.MapGroup("/api/v1/leagues");

leagues.MapGet("/", async (TourneyHubDbContext db, CancellationToken ct) =>
{
    var items = await db.Leagues.ToListAsync(ct);
    return Results.Ok(items.Select(l => new { l.Id, l.OrganizationId, l.Name }));
});

leagues.MapGet("/{leagueId:guid}", async (Guid leagueId, TourneyHubDbContext db, CancellationToken ct) =>
{
    var league = await db.Leagues.FirstOrDefaultAsync(l => l.Id == leagueId, ct);
    return league is null ? Results.NotFound() : Results.Ok(new { league.Id, league.OrganizationId, league.Name });
});

leagues.MapPost("/", async (CreateLeagueRequest request, TourneyHubDbContext db, CancellationToken ct) =>
{
    var league = new League(request.Name);
    db.Leagues.Add(league);
    await db.SaveChangesAsync(ct);
    return Results.Created($"/api/v1/leagues/{league.Id}", new { league.Id, league.OrganizationId, league.Name });
});

app.MapGet("/api/v1/ping", () => Results.Ok(new { service = "TourneyHub", version = "v1" }));

app.Run();

// Exposed for WebApplicationFactory-based integration tests (Testcontainers).
public partial class Program { }

internal sealed record CreateLeagueRequest(string Name);
