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

internal static class MatchesEndpoints
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };

    public static RouteGroupBuilder MapMatchesEndpoints(this IEndpointRouteBuilder app)
    {
        var matches = app.MapGroup("/api/v1/matches");

        matches.MapPatch("/{matchId:guid}/result", SubmitResultAsync).WithOpenApi();
        matches.MapPost("/{matchId:guid}/forfeit", ForfeitMatchAsync).WithOpenApi();

        return matches;
    }

    public static RouteGroupBuilder MapParticipantWithdrawalEndpoints(this IEndpointRouteBuilder app)
    {
        var participants = app.MapGroup("/api/v1/participants");

        participants.MapPost("/{participantId:guid}/withdraw", WithdrawParticipantAsync).WithOpenApi();

        return participants;
    }

    private static async Task<IResult> SubmitResultAsync(
        Guid matchId,
        [FromBody] SubmitResultRequest request,
        ITournamentService tournamentService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        var userId = GetUserId(httpContext);
        if (userId is null)
            return WriteProblem(401, ErrorCodes.Unauthorized, "Authentication required.");

        var orgId = GetOrgId(httpContext);
        if (orgId is null)
            return WriteProblem(400, ErrorCodes.NoTenantResolved, "No organization context resolved.");

        if (!httpContext.Request.Headers.TryGetValue("If-Match", out var ifMatchValues))
            return WriteProblem(428, ErrorCodes.PreconditionRequired, "If-Match header is required for result submission.");

        var ifMatch = ifMatchValues.FirstOrDefault()?.Trim('"');
        if (string.IsNullOrEmpty(ifMatch) || !int.TryParse(ifMatch, out var expectedVersion))
            return WriteProblem(400, ErrorCodes.ValidationFailed, "Invalid If-Match header value.");

        try
        {
            var command = new SubmitResultCommand(
                request.ScoreA,
                request.ScoreB,
                request.WinnerId,
                request.ForfeitedParticipantId,
                request.IsDraw);

            var match = await tournamentService.SubmitResultAsync(matchId, command, orgId.Value, userId.Value, expectedVersion, ct);

            httpContext.Response.Headers.ETag = $"\"{match.Version}\"";
            return JsonOk(MapMatchResponse(match));
        }
        catch (MatchOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.MatchNotFound => (404, ex.Code),
                ErrorCodes.InvalidMatchState => (409, ex.Code),
                ErrorCodes.ConcurrencyConflict => (409, ex.Code),
                ErrorCodes.ParticipantNotDetermined => (409, ex.Code),
                ErrorCodes.DrawsNotAllowed => (422, ex.Code),
                ErrorCodes.ScoreOutOfRange => (422, ex.Code),
                ErrorCodes.WinnerMismatch => (422, ex.Code),
                ErrorCodes.InvalidForfeit => (422, ex.Code),
                _ => (400, ex.Code),
            };
            return WriteProblem(status, code, ex.Message);
        }
        catch (TournamentOperationException ex)
        {
            return WriteProblem(409, ex.Code, ex.Message);
        }
    }

    private static async Task<IResult> ForfeitMatchAsync(
        Guid matchId,
        [FromBody] ForfeitMatchRequest request,
        ITournamentService tournamentService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        var userId = GetUserId(httpContext);
        if (userId is null)
            return WriteProblem(401, ErrorCodes.Unauthorized, "Authentication required.");

        var orgId = GetOrgId(httpContext);
        if (orgId is null)
            return WriteProblem(400, ErrorCodes.NoTenantResolved, "No organization context resolved.");

        try
        {
            var command = new ForfeitMatchCommand(request.ForfeitedParticipantId);
            var match = await tournamentService.ForfeitMatchAsync(matchId, command, orgId.Value, userId.Value, ct);

            return JsonOk(MapMatchResponse(match));
        }
        catch (MatchOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.MatchNotFound => (404, ex.Code),
                ErrorCodes.InvalidMatchState => (409, ex.Code),
                ErrorCodes.InvalidForfeit => (422, ex.Code),
                _ => (400, ex.Code),
            };
            return WriteProblem(status, code, ex.Message);
        }
        catch (TournamentOperationException ex)
        {
            return WriteProblem(409, ex.Code, ex.Message);
        }
    }

    private static async Task<IResult> WithdrawParticipantAsync(
        Guid participantId,
        ITournamentService tournamentService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        var userId = GetUserId(httpContext);
        if (userId is null)
            return WriteProblem(401, ErrorCodes.Unauthorized, "Authentication required.");

        var orgId = GetOrgId(httpContext);
        if (orgId is null)
            return WriteProblem(400, ErrorCodes.NoTenantResolved, "No organization context resolved.");

        try
        {
            var participant = await tournamentService.WithdrawParticipantAsync(participantId, orgId.Value, userId.Value, ct);
            return JsonOk(MapParticipantResponse(participant));
        }
        catch (ParticipantOperationException ex)
        {
            return WriteProblem(404, ex.Code, ex.Message);
        }
        catch (TournamentOperationException ex)
        {
            return WriteProblem(409, ex.Code, ex.Message);
        }
    }

    private static Guid? GetUserId(HttpContext httpContext)
    {
        var subClaim = httpContext.User.FindFirst(ClaimTypes.NameIdentifier)
                       ?? httpContext.User.FindFirst("sub");
        if (subClaim is not null && Guid.TryParse(subClaim.Value, out var userId))
            return userId;
        return null;
    }

    private static Guid? GetOrgId(HttpContext httpContext)
    {
        if (httpContext.Request.Headers.TryGetValue("X-Organization-Id", out var values)
            && Guid.TryParse(values.FirstOrDefault(), out var orgId))
            return orgId;
        return null;
    }

    private static MatchDetailResponse MapMatchResponse(Match m) => new(
        m.Id,
        m.TournamentId,
        m.RoundNumber,
        m.PositionInRound,
        m.ParticipantAId,
        m.ParticipantBId,
        m.State.ToString(),
        m.IsByeMatch,
        m.WinnerId,
        m.ScoreA,
        m.ScoreB,
        m.ForfeitedParticipantId,
        m.IsDraw,
        m.AdvanceToMatchId,
        m.Version);

    private static ParticipantResponse MapParticipantResponse(Participant p) => new(
        p.Id,
        p.TournamentId,
        p.CaptainUserId,
        p.DisplayName,
        p.Status.ToString().ToLowerInvariant(),
        p.Version);

    private static IResult JsonOk(object? value) => Results.Text(
        JsonSerializer.Serialize(value, JsonOptions),
        MediaTypeNames.Application.Json,
        statusCode: 200);

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
                422 => "Unprocessable Entity",
                428 => "Precondition Required",
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

internal sealed record SubmitResultRequest(
    int? ScoreA,
    int? ScoreB,
    Guid? WinnerId,
    Guid? ForfeitedParticipantId,
    bool IsDraw);

internal sealed record ForfeitMatchRequest(
    Guid ForfeitedParticipantId);

internal sealed record MatchDetailResponse(
    Guid Id,
    Guid TournamentId,
    int Round,
    int Slot,
    Guid? ParticipantA,
    Guid? ParticipantB,
    string State,
    bool IsByeMatch,
    Guid? WinnerId,
    int? ScoreA,
    int? ScoreB,
    Guid? ForfeitedParticipantId,
    bool IsDraw,
    Guid? AdvanceToMatchId,
    int Version);