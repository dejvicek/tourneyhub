using Microsoft.AspNetCore.RateLimiting;
using System.Threading.RateLimiting;
using Microsoft.EntityFrameworkCore;
using TourneyHub.Api.Middleware;
using TourneyHub.Application.Tenancy;
using TourneyHub.Domain.Competition;
using TourneyHub.Infrastructure.Persistence;
using TourneyHub.Infrastructure.Tenancy;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

builder.Services.AddHttpContextAccessor();
builder.Services.AddScoped<HttpTenantContext>();
builder.Services.AddScoped<ITenantContext>(sp => sp.GetRequiredService<HttpTenantContext>());

builder.Services.AddDbContext<TourneyHubDbContext>(options =>
    options.UseNpgsql(builder.Configuration.GetConnectionString("Postgres")));

builder.Services.AddHealthChecks()
    .AddNpgSql(
        connectionString: builder.Configuration.GetConnectionString("Postgres")!,
        name: "postgres",
        tags: ["ready"])
    .AddRedis(
        redisConnectionString: builder.Configuration.GetConnectionString("Redis")!,
        name: "redis",
        tags: ["ready"]);

builder.Services.AddRateLimiter(options =>
{
    options.RejectionStatusCode = 429;

    options.AddFixedWindowLimiter("default", config =>
    {
        config.PermitLimit = 300;
        config.Window = TimeSpan.FromMinutes(1);
        config.QueueProcessingOrder = QueueProcessingOrder.OldestFirst;
        config.QueueLimit = 10;
    });

    options.AddFixedWindowLimiter("auth", config =>
    {
        config.PermitLimit = 20;
        config.Window = TimeSpan.FromMinutes(1);
        config.QueueProcessingOrder = QueueProcessingOrder.OldestFirst;
        config.QueueLimit = 0;
    });

    options.AddFixedWindowLimiter("finance", config =>
    {
        config.PermitLimit = 10;
        config.Window = TimeSpan.FromMinutes(1);
        config.QueueProcessingOrder = QueueProcessingOrder.OldestFirst;
        config.QueueLimit = 0;
    });
});

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseMiddleware<CorrelationIdMiddleware>();
app.UseMiddleware<ProblemDetailsMiddleware>();
app.UseMiddleware<IdempotencyMiddleware>();
app.UseRateLimiter();
app.UseMiddleware<TenantResolutionMiddleware>();

var leagues = app.MapGroup("/api/v1/leagues");

leagues.MapGet("/", async (TourneyHubDbContext db, CancellationToken ct) =>
{
    var items = await db.Leagues.ToListAsync(ct);
    return Results.Ok(items.Select(l => new { l.Id, l.OrganizationId, l.Name }));
});

leagues.MapGet("/{leagueId:guid}", async (Guid leagueId, TourneyHubDbContext db, HttpContext httpContext, CancellationToken ct) =>
{
    var league = await db.Leagues.FirstOrDefaultAsync(l => l.Id == leagueId, ct);
    if (league is null)
    {
        return Results.NotFound();
    }

    httpContext.Response.Headers.ETag = $"\"{league.Version}\"";
    return Results.Ok(new { league.Id, league.OrganizationId, league.Name });
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

public partial class Program { }

internal sealed record CreateLeagueRequest(string Name);
