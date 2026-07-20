using System.Net.Mime;
using System.Security.Claims;
using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Routing;
using TourneyHub.Application.Common;
using TourneyHub.Application.Competition;
using TourneyHub.Domain.Competition;

namespace TourneyHub.Api.Extensions;

internal static class LeaguesEndpoints
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };

    public static RouteGroupBuilder MapLeaguesEndpoints(this IEndpointRouteBuilder app)
    {
        var leagues = app.MapGroup("/api/v1/leagues");

        leagues.MapGet("/", ListAsync).WithOpenApi();
        leagues.MapPost("/", CreateAsync).WithOpenApi();
        leagues.MapGet("/{leagueId:guid}", GetByIdAsync).WithOpenApi();
        leagues.MapPut("/{leagueId:guid}", UpdateAsync).WithOpenApi();
        leagues.MapPost("/{leagueId:guid}/archive", ArchiveAsync).WithOpenApi();
        leagues.MapPost("/{leagueId:guid}/unarchive", UnarchiveAsync).WithOpenApi();
        leagues.MapPost("/{leagueId:guid}/transfer-ownership", TransferOwnershipAsync).WithOpenApi();
        leagues.MapDelete("/{leagueId:guid}", DeleteAsync).WithOpenApi();

        leagues.MapPost("/{leagueId:guid}/seasons", CreateSeasonAsync).WithOpenApi();
        leagues.MapGet("/{leagueId:guid}/seasons", ListSeasonsAsync).WithOpenApi();
        leagues.MapPost("/seasons/{seasonId:guid}/activate", ActivateSeasonAsync).WithOpenApi();
        leagues.MapPost("/seasons/{seasonId:guid}/close", CloseSeasonAsync).WithOpenApi();
        leagues.MapPost("/seasons/{seasonId:guid}/cancel", CancelSeasonAsync).WithOpenApi();

        return leagues;
    }

    public static RouteGroupBuilder MapPublicEndpoints(this IEndpointRouteBuilder app)
    {
        var publicEndpoints = app.MapGroup("/api/v1/public");

        publicEndpoints.MapGet("/leagues/{slug}", GetPublicBySlugAsync)
            .WithOpenApi()
            .AllowAnonymous();

        return publicEndpoints;
    }

    private static async Task<IResult> ListAsync(
        ILeagueService leagueService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        var orgId = GetOrgId(httpContext);
        if (orgId is null)
        {
            return WriteProblem(400, ErrorCodes.NoTenantResolved, "No organization context resolved.");
        }

        var leagues = await leagueService.ListAsync(orgId.Value, ct);
        return JsonOk(leagues.Select(MapLeagueResponse).ToList());
    }

    private static async Task<IResult> CreateAsync(
        [FromBody] CreateLeagueRequest request,
        ILeagueService leagueService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        var userId = GetUserId(httpContext);
        if (userId is null)
        {
            return WriteProblem(401, ErrorCodes.Unauthorized, "Authentication required.");
        }

        var orgId = GetOrgId(httpContext);
        if (orgId is null)
        {
            return WriteProblem(400, ErrorCodes.NoTenantResolved, "No organization context resolved.");
        }

        try
        {
            var command = new CreateLeagueCommand(
                request.Name, request.Slug, MapVisibility(request.Visibility), request.Description);
            var league = await leagueService.CreateAsync(command, orgId.Value, userId.Value, ct);
            return JsonCreated($"/api/v1/leagues/{league.Id}", MapLeagueResponse(league));
        }
        catch (LeagueOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.SlugAlreadyTakenInOrg => (409, ex.Code),
                _ => (400, ex.Code),
            };
            return WriteProblem(status, code, ex.Message);
        }
    }

    private static async Task<IResult> GetByIdAsync(
        Guid leagueId,
        ILeagueService leagueService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        var orgId = GetOrgId(httpContext);
        if (orgId is null)
        {
            return WriteProblem(400, ErrorCodes.NoTenantResolved, "No organization context resolved.");
        }

        var league = await leagueService.GetByIdAsync(leagueId, ct);
        if (league is null)
        {
            return WriteProblem(404, ErrorCodes.NotFound, "League not found.");
        }

        httpContext.Response.Headers.ETag = $"\"{league.Version}\"";
        return JsonOk(MapLeagueResponse(league));
    }

    private static async Task<IResult> UpdateAsync(
        Guid leagueId,
        [FromBody] UpdateLeagueRequest request,
        ILeagueService leagueService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        try
        {
            var command = new UpdateLeagueCommand(
                request.Name, MapVisibility(request.Visibility), request.Description);
            var league = await leagueService.UpdateAsync(leagueId, command, ct);
            httpContext.Response.Headers.ETag = $"\"{league.Version}\"";
            return JsonOk(MapLeagueResponse(league));
        }
        catch (LeagueOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.LeagueNotFound => (404, ex.Code),
                _ => (400, ex.Code),
            };
            return WriteProblem(status, code, ex.Message);
        }
    }

    private static async Task<IResult> ArchiveAsync(
        Guid leagueId,
        ILeagueService leagueService,
        CancellationToken ct)
    {
        try
        {
            var league = await leagueService.ArchiveAsync(leagueId, ct);
            return JsonOk(MapLeagueResponse(league));
        }
        catch (LeagueOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.LeagueNotFound => (404, ex.Code),
                _ => (409, ex.Code),
            };
            return WriteProblem(status, code, ex.Message);
        }
    }

    private static async Task<IResult> UnarchiveAsync(
        Guid leagueId,
        ILeagueService leagueService,
        CancellationToken ct)
    {
        try
        {
            var league = await leagueService.UnarchiveAsync(leagueId, ct);
            return JsonOk(MapLeagueResponse(league));
        }
        catch (LeagueOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.LeagueNotFound => (404, ex.Code),
                _ => (409, ex.Code),
            };
            return WriteProblem(status, code, ex.Message);
        }
    }

    private static async Task<IResult> TransferOwnershipAsync(
        Guid leagueId,
        [FromBody] TransferLeagueOwnershipRequest request,
        ILeagueService leagueService,
        CancellationToken ct)
    {
        try
        {
            var league = await leagueService.TransferOwnershipAsync(leagueId, request.NewOwnerUserId, ct);
            return JsonOk(MapLeagueResponse(league));
        }
        catch (LeagueOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.LeagueNotFound => (404, ex.Code),
                _ => (400, ex.Code),
            };
            return WriteProblem(status, code, ex.Message);
        }
    }

    private static async Task<IResult> DeleteAsync(
        Guid leagueId,
        ILeagueService leagueService,
        CancellationToken ct)
    {
        try
        {
            await leagueService.DeleteAsync(leagueId, ct);
            return Results.NoContent();
        }
        catch (LeagueOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.LeagueNotFound => (404, ex.Code),
                _ => (400, ex.Code),
            };
            return WriteProblem(status, code, ex.Message);
        }
    }

    private static async Task<IResult> CreateSeasonAsync(
        Guid leagueId,
        [FromBody] CreateSeasonRequest request,
        ILeagueService leagueService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        try
        {
            var command = new CreateSeasonCommand(request.Name, request.StartsAt, request.EndsAt);
            var season = await leagueService.CreateSeasonAsync(leagueId, command, ct);
            return JsonCreated($"/api/v1/seasons/{season.Id}", MapSeasonResponse(season));
        }
        catch (LeagueOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.LeagueNotFound => (404, ex.Code),
                ErrorCodes.LeagueArchived => (409, ex.Code),
                _ => (400, ex.Code),
            };
            return WriteProblem(status, code, ex.Message);
        }
        catch (SeasonOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.SeasonAlreadyActive => (409, ex.Code),
                _ => (400, ex.Code),
            };
            return WriteProblem(status, code, ex.Message);
        }
    }

    private static async Task<IResult> ListSeasonsAsync(
        Guid leagueId,
        ILeagueService leagueService,
        CancellationToken ct)
    {
        var seasons = await leagueService.ListSeasonsAsync(leagueId, ct);
        return JsonOk(seasons.Select(MapSeasonResponse).ToList());
    }

    private static async Task<IResult> ActivateSeasonAsync(
        Guid seasonId,
        ILeagueService leagueService,
        CancellationToken ct)
    {
        try
        {
            var season = await leagueService.ActivateSeasonAsync(seasonId, ct);
            return JsonOk(MapSeasonResponse(season));
        }
        catch (SeasonOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.NotFound => (404, ex.Code),
                ErrorCodes.SeasonAlreadyActive => (409, ex.Code),
                _ => (400, ex.Code),
            };
            return WriteProblem(status, code, ex.Message);
        }
        catch (LeagueOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.LeagueArchived => (409, ex.Code),
                _ => (400, ex.Code),
            };
            return WriteProblem(status, code, ex.Message);
        }
    }

    private static async Task<IResult> CloseSeasonAsync(
        Guid seasonId,
        ILeagueService leagueService,
        CancellationToken ct)
    {
        try
        {
            var season = await leagueService.CloseSeasonAsync(seasonId, ct);
            return JsonOk(MapSeasonResponse(season));
        }
        catch (SeasonOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.NotFound => (404, ex.Code),
                _ => (409, ex.Code),
            };
            return WriteProblem(status, code, ex.Message);
        }
    }

    private static async Task<IResult> CancelSeasonAsync(
        Guid seasonId,
        ILeagueService leagueService,
        CancellationToken ct)
    {
        try
        {
            var season = await leagueService.CancelSeasonAsync(seasonId, ct);
            return JsonOk(MapSeasonResponse(season));
        }
        catch (SeasonOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.NotFound => (404, ex.Code),
                _ => (409, ex.Code),
            };
            return WriteProblem(status, code, ex.Message);
        }
    }

    private static async Task<IResult> GetPublicBySlugAsync(
        string slug,
        ILeagueService leagueService,
        CancellationToken ct)
    {
        var league = await leagueService.GetBySlugForPublicAsync(slug, ct);
        if (league is null)
        {
            return WriteProblem(404, ErrorCodes.NotFound, "League not found.");
        }

        return JsonOk(MapLeagueResponse(league));
    }

    private static Guid? GetUserId(HttpContext httpContext)
    {
        var subClaim = httpContext.User.FindFirst(ClaimTypes.NameIdentifier)
                       ?? httpContext.User.FindFirst("sub");
        if (subClaim is not null && Guid.TryParse(subClaim.Value, out var userId))
        {
            return userId;
        }

        return null;
    }

    private static Guid? GetOrgId(HttpContext httpContext)
    {
        if (httpContext.Request.Headers.TryGetValue("X-Organization-Id", out var values)
            && Guid.TryParse(values.FirstOrDefault(), out var orgId))
        {
            return orgId;
        }

        return null;
    }

    private static LeagueVisibility MapVisibility(string? visibility) => visibility?.ToLowerInvariant() switch
    {
        "public" => LeagueVisibility.Public,
        "unlisted" => LeagueVisibility.Unlisted,
        "private" => LeagueVisibility.Private,
        null => LeagueVisibility.Private,
        _ => throw new LeagueOperationException("invalid_visibility", $"Invalid visibility: {visibility}. Must be 'public', 'unlisted', or 'private'."),
    };

    private static LeagueResponse MapLeagueResponse(League league) => new(
        league.Id,
        league.OrganizationId,
        league.Name,
        league.Slug,
        league.Description,
        league.Visibility.ToString().ToLowerInvariant(),
        league.OwnerId,
        league.State.ToString().ToLowerInvariant(),
        league.Version);

    private static SeasonResponse MapSeasonResponse(Season season) => new(
        season.Id,
        season.LeagueId,
        season.OrganizationId,
        season.Name,
        season.State.ToString().ToLowerInvariant(),
        season.StartedAt,
        season.CompletedAt,
        season.RngSeed,
        season.Version);

    private static IResult JsonOk(object? value) => Results.Text(
        JsonSerializer.Serialize(value, JsonOptions),
        MediaTypeNames.Application.Json,
        statusCode: 200);

    private static IResult JsonCreated(string uri, object? value) => Results.Text(
        JsonSerializer.Serialize(value, JsonOptions),
        MediaTypeNames.Application.Json,
        statusCode: 201);

    private static IResult WriteProblem(int status, string code, string detail)
    {
        var problem = new
        {
            type = $"https://tourneyhub.dev/errors/{code}",
            title = status switch
            {
                400 => "Bad Request",
                401 => "Unauthorized",
                404 => "Not Found",
                409 => "Conflict",
                _ => "Error",
            },
            status,
            detail,
            code,
        };

        return Results.Text(
            JsonSerializer.Serialize(problem, JsonOptions),
            "application/problem+json",
            statusCode: status);
    }
}

internal sealed record CreateLeagueRequest(string Name, string? Visibility, string? Slug, string? Description);

internal sealed record UpdateLeagueRequest(string? Name, string? Visibility, string? Description);

internal sealed record TransferLeagueOwnershipRequest(Guid NewOwnerUserId);

internal sealed record CreateSeasonRequest(string Name, DateTime? StartsAt, DateTime? EndsAt);

internal sealed record LeagueResponse(
    Guid Id, Guid OrganizationId, string Name, string Slug, string? Description,
    string Visibility, Guid OwnerId, string State, int Version);

internal sealed record SeasonResponse(
    Guid Id, Guid LeagueId, Guid OrganizationId, string Name, string State,
    DateTime? StartedAt, DateTime? CompletedAt, string? RngSeed, int Version);
