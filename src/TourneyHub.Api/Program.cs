using System.Net.Mime;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.RateLimiting;
using System.Threading.RateLimiting;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using TourneyHub.Api.Extensions;
using TourneyHub.Api.Middleware;
using TourneyHub.Application.Identity;
using TourneyHub.Application.Tenancy;
using TourneyHub.Domain.Competition;
using TourneyHub.Domain.Identity;
using TourneyHub.Application.Organizations;
using TourneyHub.Infrastructure.Identity;
using TourneyHub.Infrastructure.Organizations;
using TourneyHub.Infrastructure.Persistence;
using TourneyHub.Infrastructure.Tenancy;

var builder = WebApplication.CreateBuilder(args);

builder.Services.ConfigureHttpJsonOptions(options =>
{
    options.SerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.CamelCase;
});

builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

builder.Services.AddHttpContextAccessor();
builder.Services.AddScoped<HttpTenantContext>();
builder.Services.AddScoped<ITenantContext>(sp => sp.GetRequiredService<HttpTenantContext>());

builder.Services.AddDbContext<TourneyHubDbContext>(options =>
    options.UseNpgsql(builder.Configuration.GetConnectionString("Postgres")));

builder.Services.AddIdentity<User, IdentityRole<Guid>>(options =>
    {
        options.User.RequireUniqueEmail = true;
        options.SignIn.RequireConfirmedEmail = false;
        options.Password.RequiredLength = 12;
        options.Password.RequireDigit = false;
        options.Password.RequireLowercase = false;
        options.Password.RequireUppercase = false;
        options.Password.RequireNonAlphanumeric = false;
    })
    .AddEntityFrameworkStores<TourneyHubDbContext>()
    .AddDefaultTokenProviders();

builder.Services.AddScoped<IPasswordValidator<User>, BreachedPasswordValidator<User>>();

var jwtSection = builder.Configuration.GetSection(JwtOptions.Section);
builder.Services.Configure<JwtOptions>(jwtSection);

var jwtOptions = jwtSection.Get<JwtOptions>() ?? new JwtOptions();
var signingKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(
    string.IsNullOrEmpty(jwtOptions.SigningKey)
        ? "dev-test-key-at-least-32-bytes-long!!"
        : jwtOptions.SigningKey));

builder.Services.AddAuthentication(options =>
    {
        options.DefaultAuthenticateScheme = JwtBearerDefaults.AuthenticationScheme;
        options.DefaultChallengeScheme = JwtBearerDefaults.AuthenticationScheme;
    })
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true,
            ValidateAudience = true,
            ValidateLifetime = true,
            ValidateIssuerSigningKey = true,
            ValidIssuer = jwtOptions.Issuer,
            ValidAudience = jwtOptions.Audience,
            IssuerSigningKey = signingKey,
            ClockSkew = TimeSpan.Zero,
        };
    });

builder.Services.AddAuthorizationBuilder()
    .AddPolicy(InstanceAdminRequirement.PolicyName,
        policy => policy.Requirements.Add(new InstanceAdminRequirement()));

builder.Services.AddSingleton<IAuthorizationHandler, InstanceAdminHandler>();
builder.Services.AddHostedService<BootstrapService>();

builder.Services.AddSingleton<JwtTokenService>();
builder.Services.AddScoped<IIdentityService, IdentityService>();
builder.Services.AddScoped<IOrganizationService, OrganizationService>();
builder.Services.AddScoped<IInvitationService, InvitationService>();

builder.Services.AddHttpClient<BreachedPasswordValidator<User>>();

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
app.UseAuthentication();
app.UseAuthorization();
app.UseMiddleware<SuspensionGuardMiddleware>();
app.UseMiddleware<TenantResolutionMiddleware>();

app.MapAuthEndpoints();
app.MapOrganizationsEndpoints();
app.MapInvitationsEndpoints();
app.MapLeagueInvitationsEndpoints();

var leagues = app.MapGroup("/api/v1/leagues");

leagues.MapGet("/", async (TourneyHubDbContext db, CancellationToken ct) =>
{
    var items = await db.Leagues.ToListAsync(ct);
    return ProgramHelpers.JsonOk(items.Select(l => new LeagueResponse(l.Id, l.OrganizationId, l.Name)).ToList());
});

leagues.MapGet("/{leagueId:guid}", async (Guid leagueId, TourneyHubDbContext db, HttpContext httpContext, CancellationToken ct) =>
{
    var league = await db.Leagues.FirstOrDefaultAsync(l => l.Id == leagueId, ct);
    if (league is null)
    {
        return Results.NotFound();
    }

    httpContext.Response.Headers.ETag = $"\"{league.Version}\"";
return ProgramHelpers.JsonOk(new LeagueResponse(league.Id, league.OrganizationId, league.Name));
    });

    leagues.MapPost("/", async (CreateLeagueRequest request, TourneyHubDbContext db, CancellationToken ct) =>
    {
        var league = new League(request.Name);
        db.Leagues.Add(league);
    await db.SaveChangesAsync(ct);
    return ProgramHelpers.JsonCreated($"/api/v1/leagues/{league.Id}",
        new LeagueResponse(league.Id, league.OrganizationId, league.Name));
});

app.MapGet("/api/v1/ping", () => Results.Text("pong", statusCode: 200));

app.Run();

public partial class Program { }

internal sealed record CreateLeagueRequest(string Name);

internal sealed record LeagueResponse(Guid Id, Guid OrganizationId, string Name);

internal static class ProgramHelpers
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };

    internal static IResult JsonOk(object? value) => Results.Text(
        JsonSerializer.Serialize(value, JsonOptions),
        MediaTypeNames.Application.Json,
        statusCode: 200);

    internal static IResult JsonCreated(string uri, object? value) => Results.Text(
        JsonSerializer.Serialize(value, JsonOptions),
        MediaTypeNames.Application.Json,
        statusCode: 201);
}