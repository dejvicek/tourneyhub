using System.Net.Mime;
using System.Security.Claims;
using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Routing;
using TourneyHub.Application.Common;
using TourneyHub.Application.Identity;
using TourneyHub.Application.Identity.Commands;
using TourneyHub.Domain.Identity;

namespace TourneyHub.Api.Extensions;

internal static class InvitationsEndpoints
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };

    public static RouteGroupBuilder MapInvitationsEndpoints(this IEndpointRouteBuilder app)
    {
        var invitations = app.MapGroup("/api/v1/invitations");

        invitations.MapGet("/{invitationId:guid}", GetByIdAsync).WithOpenApi();
        invitations.MapPost("/{invitationId:guid}/accept", AcceptAsync).WithOpenApi();
        invitations.MapPost("/{invitationId:guid}/decline", DeclineAsync).WithOpenApi();

        return invitations;
    }

    public static RouteGroupBuilder MapLeagueInvitationsEndpoints(this IEndpointRouteBuilder app)
    {
        var leagueInvites = app.MapGroup("/api/v1/leagues/{leagueId:guid}/invitations");

        leagueInvites.MapPost("/", CreateLeagueInvitationAsync).WithOpenApi();

        return leagueInvites;
    }

    private static async Task<IResult> CreateLeagueInvitationAsync(
        Guid leagueId,
        [FromBody] CreateInvitationRequest request,
        IInvitationService invitationService,
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
            var command = new CreateInvitationCommand(
                request.Email,
                InvitationScopeType.League,
                leagueId,
                MapRole(request.Role));

            var invitation = await invitationService.CreateAsync(command, orgId.Value, userId.Value, ct);
            var location = $"/api/v1/invitations/{invitation.Id}";
            return JsonCreated(location, MapResponse(invitation));
        }
        catch (InvitationOperationException ex)
        {
            return WriteProblem(400, ex.Code, ex.Message);
        }
    }

    private static async Task<IResult> GetByIdAsync(
        Guid invitationId,
        IInvitationService invitationService,
        CancellationToken ct)
    {
        var invitation = await invitationService.GetByIdAsync(invitationId, ct);
        if (invitation is null)
        {
            return WriteProblem(404, ErrorCodes.InvitationNotFound, "Invitation not found.");
        }

        return JsonOk(MapResponse(invitation));
    }

    private static async Task<IResult> AcceptAsync(
        Guid invitationId,
        IInvitationService invitationService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        var (userId, email) = GetUserIdentity(httpContext);
        if (userId is null)
        {
            return WriteProblem(401, ErrorCodes.Unauthorized, "Authentication required.");
        }

        try
        {
            var invitation = await invitationService.AcceptAsync(invitationId, userId.Value, email!, ct);
            return JsonOk(MapResponse(invitation));
        }
        catch (InvitationOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.InvitationNotFound => (404, ErrorCodes.InvitationNotFound),
                ErrorCodes.InvitationExpired => (410, ErrorCodes.InvitationExpired),
                ErrorCodes.InvitationAlreadyAccepted => (409, ErrorCodes.InvitationAlreadyAccepted),
                ErrorCodes.InvitationRevoked => (403, ErrorCodes.InvitationRevoked),
                ErrorCodes.InvitationDeclined => (409, ErrorCodes.InvitationDeclined),
                ErrorCodes.InvitationEmailMismatch => (403, ErrorCodes.InvitationEmailMismatch),
                _ => (400, ex.Code),
            };

            return WriteProblem(status, code, ex.Message);
        }
    }

    private static async Task<IResult> DeclineAsync(
        Guid invitationId,
        IInvitationService invitationService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        var (userId, email) = GetUserIdentity(httpContext);
        if (userId is null)
        {
            return WriteProblem(401, ErrorCodes.Unauthorized, "Authentication required.");
        }

        try
        {
            await invitationService.DeclineAsync(invitationId, userId.Value, email!, ct);
            return Results.NoContent();
        }
        catch (InvitationOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.InvitationNotFound => (404, ErrorCodes.InvitationNotFound),
                ErrorCodes.InvitationExpired => (410, ErrorCodes.InvitationExpired),
                ErrorCodes.InvitationRevoked => (403, ErrorCodes.InvitationRevoked),
                ErrorCodes.InvitationEmailMismatch => (403, ErrorCodes.InvitationEmailMismatch),
                _ => (400, ex.Code),
            };

            return WriteProblem(status, code, ex.Message);
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

    private static Guid? GetOrgId(HttpContext httpContext)
    {
        if (httpContext.Request.Headers.TryGetValue("X-Organization-Id", out var values)
            && Guid.TryParse(values.FirstOrDefault(), out var orgId))
        {
            return orgId;
        }

        return null;
    }

    private static (Guid? UserId, string? Email) GetUserIdentity(HttpContext httpContext)
    {
        var userId = GetUserId(httpContext);
        var email = httpContext.User.FindFirst(ClaimTypes.Email)?.Value
                    ?? httpContext.User.FindFirst("email")?.Value;

        return (userId, email);
    }

    private static InvitedRole MapRole(string role) => role?.ToLowerInvariant() switch
    {
        "organizer" => InvitedRole.Organizer,
        "player" => InvitedRole.Player,
        _ => throw new InvitationOperationException("invalid_role", $"Invalid role: {role}. Must be 'organizer' or 'player'."),
    };

    private static InvitationResponse MapResponse(Invitation invitation) => new(
        invitation.Id,
        invitation.OrganizationId,
        invitation.Email,
        invitation.ScopeType.ToString().ToLowerInvariant(),
        invitation.ScopeId,
        invitation.Role.ToString().ToLowerInvariant(),
        invitation.State.ToString().ToLowerInvariant(),
        invitation.Version,
        invitation.ExpiresAt);

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
                410 => "Gone",
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

internal sealed record CreateInvitationRequest(string Email, string Role);
