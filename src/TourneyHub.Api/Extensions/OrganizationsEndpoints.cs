using System.Net.Mime;
using System.Security.Claims;
using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Routing;
using TourneyHub.Application.Common;
using TourneyHub.Application.Organizations;
using TourneyHub.Domain.Organizations;
using TourneyHub.Infrastructure.Identity;
using TourneyHub.Infrastructure.Organizations;

namespace TourneyHub.Api.Extensions;

internal static class OrganizationsEndpoints
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };
    public static RouteGroupBuilder MapOrganizationsEndpoints(this IEndpointRouteBuilder app)
    {
        var orgs = app.MapGroup("/api/v1/organizations");

        orgs.MapPost("/", CreateAsync).WithOpenApi();
        orgs.MapGet("/", ListAsync).WithOpenApi();
        orgs.MapGet("/{orgId:guid}", GetByIdAsync).WithOpenApi();
        orgs.MapPost("/{orgId:guid}/transfer-ownership", TransferOwnershipAsync).WithOpenApi();
        orgs.MapPut("/{orgId:guid}/suspension", SetSuspensionAsync)
            .WithOpenApi()
            .RequireAuthorization(InstanceAdminRequirement.PolicyName);

        return orgs;
    }

    private static async Task<IResult> CreateAsync(
        [FromBody] CreateOrganizationCommand command,
        IOrganizationService orgService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        var userId = GetUserId(httpContext);
        if (userId is null)
        {
            return WriteProblem(401, ErrorCodes.Unauthorized, "Authentication required.");
        }

        try
        {
            var org = await orgService.CreateAsync(command, userId.Value, ct);
            return JsonCreated($"/api/v1/organizations/{org.Id}", MapResponse(org));
        }
        catch (OrganizationOperationException ex)
        {
            return WriteProblem(409, ErrorCodes.SlugAlreadyTaken, ex.Message);
        }
    }

    private static async Task<IResult> ListAsync(
        IOrganizationService orgService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        var userId = GetUserId(httpContext);
        if (userId is null)
        {
            return WriteProblem(401, ErrorCodes.Unauthorized, "Authentication required.");
        }

        var orgs = await orgService.ListUserOrganizationsAsync(userId.Value, ct);
        return JsonOk(orgs.Select(MapResponse).ToList());
    }

    private static async Task<IResult> GetByIdAsync(
        Guid orgId,
        IOrganizationService orgService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        var userId = GetUserId(httpContext);
        if (userId is null)
        {
            return WriteProblem(401, ErrorCodes.Unauthorized, "Authentication required.");
        }

        var orgs = await orgService.ListUserOrganizationsAsync(userId.Value, ct);
        var org = orgs.FirstOrDefault(o => o.Id == orgId);
        if (org is null)
        {
            return WriteProblem(403, ErrorCodes.Forbidden, "You are not a member of this organization (FR-150).");
        }

        httpContext.Response.Headers.ETag = $"\"{org.Version}\"";
        return JsonOk(MapResponse(org));
    }

    private static async Task<IResult> TransferOwnershipAsync(
        Guid orgId,
        [FromBody] TransferOwnershipRequest request,
        IOrganizationService orgService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        var userId = GetUserId(httpContext);
        if (userId is null)
        {
            return WriteProblem(401, ErrorCodes.Unauthorized, "Authentication required.");
        }

        try
        {
            await orgService.TransferOwnershipAsync(orgId, userId.Value, request.NewOwnerUserId, ct);
            return Results.NoContent();
        }
        catch (OrganizationOperationException ex)
        {
            var status = ex.Code switch
            {
                "forbidden" => 403,
                "not_found" => 404,
                "sole_owner_cannot_leave" => 409,
                _ => 400,
            };

            var errorCode = ex.Code switch
            {
                "sole_owner_cannot_leave" => ErrorCodes.SoleOwnerCannotLeave,
                "not_found" => ErrorCodes.NotFound,
                _ => ErrorCodes.Forbidden,
            };

            return WriteProblem(status, errorCode, ex.Message);
        }
    }

    private static async Task<IResult> SetSuspensionAsync(
        Guid orgId,
        [FromBody] SetSuspensionRequest request,
        IOrganizationService orgService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        var userId = GetUserId(httpContext);
        if (userId is null)
        {
            return WriteProblem(401, ErrorCodes.Unauthorized, "Authentication required.");
        }

        try
        {
            await orgService.SetSuspensionAsync(orgId, request.Suspended, request.Reason, userId.Value, ct);
            return Results.NoContent();
        }
        catch (OrganizationOperationException ex)
        {
            var status = ex.Code switch
            {
                "not_found" => 404,
                _ => 400,
            };

            var errorCode = ex.Code switch
            {
                "not_found" => ErrorCodes.NotFound,
                _ => ErrorCodes.UnknownError,
            };

            return WriteProblem(status, errorCode, ex.Message);
        }
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

    private static OrganizationResponse MapResponse(Organization org) => new(
        org.Id,
        org.Name,
        org.Slug,
        org.State.ToString().ToLowerInvariant(),
        org.Plan,
        org.Version);

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
                401 => "Unauthorized",
                403 => "Forbidden",
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

internal sealed record TransferOwnershipRequest(Guid NewOwnerUserId);

internal sealed record OrganizationResponse(Guid Id, string Name, string Slug, string State, string Plan, int Version);

internal sealed record SetSuspensionRequest(bool Suspended, string? Reason);
