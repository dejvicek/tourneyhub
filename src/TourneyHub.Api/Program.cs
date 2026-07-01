var builder = WebApplication.CreateBuilder(args);

builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

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
app.MapGet("/health/live", () => Results.Ok(new { status = "live" }));
app.MapGet("/health/ready", () => Results.Ok(new { status = "ready" }));

// Placeholder API root until controllers are generated from api/openapi.yaml.
app.MapGet("/api/v1/ping", () => Results.Ok(new { service = "TourneyHub", version = "v1" }));

app.Run();

// Exposed for WebApplicationFactory-based integration tests (Testcontainers).
public partial class Program { }
