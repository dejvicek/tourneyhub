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

internal static class TournamentsEndpoints
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };

    public static RouteGroupBuilder MapTournamentsEndpoints(this IEndpointRouteBuilder app)
    {
        var tournaments = app.MapGroup("/api/v1/tournaments");

        tournaments.MapGet("/", ListAsync).WithOpenApi();
        tournaments.MapPost("/", CreateAsync).WithOpenApi();
        tournaments.MapGet("/{tournamentId:guid}", GetByIdAsync).WithOpenApi();
        tournaments.MapPost("/{tournamentId:guid}/registrations", RegisterParticipantAsync).WithOpenApi();
        tournaments.MapPost("/{tournamentId:guid}/seed", SeedAsync).WithOpenApi();
        tournaments.MapPost("/{tournamentId:guid}/generate-bracket", GenerateBracketAsync).WithOpenApi();

        var participants = app.MapGroup("/api/v1/participants");
        participants.MapPost("/{participantId:guid}/members/accept", AcceptMemberAsync).WithOpenApi();

        return tournaments;
    }

    private static async Task<IResult> ListAsync(
        [FromQuery] Guid? leagueId,
        [FromQuery] string? status,
        ITournamentService tournamentService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        var orgId = GetOrgId(httpContext);
        if (orgId is null)
            return WriteProblem(400, ErrorCodes.NoTenantResolved, "No organization context resolved.");

        var tournaments = await tournamentService.ListAsync(orgId.Value, leagueId, status, ct);
        return JsonOk(tournaments.Select(MapTournamentResponse).ToList());
    }

    private static async Task<IResult> CreateAsync(
        [FromBody] CreateTournamentRequest request,
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
            var command = new CreateTournamentCommand(
                request.DisciplineName,
                request.ResultModel,
                request.TeamSize,
                request.FormatType,
                request.ResultEntryMode,
                request.LeagueId,
                request.SeasonId,
                request.ScoreConfig,
                request.BestOf,
                request.Currency,
                request.EntryFeeAmountMinor,
                request.RegOpenAt,
                request.RegCloseAt,
                request.MaxParticipants);

            var tournament = await tournamentService.CreateAsync(command, orgId.Value, userId.Value, ct);
            return JsonCreated($"/api/v1/tournaments/{tournament.Id}", MapTournamentResponse(tournament));
        }
        catch (TournamentOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.LeagueNotFound => (404, ex.Code),
                _ => (400, ex.Code),
            };
            return WriteProblem(status, code, ex.Message);
        }
    }

    private static async Task<IResult> GetByIdAsync(
        Guid tournamentId,
        ITournamentService tournamentService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        var orgId = GetOrgId(httpContext);
        if (orgId is null)
            return WriteProblem(400, ErrorCodes.NoTenantResolved, "No organization context resolved.");

        var tournament = await tournamentService.GetByIdAsync(tournamentId, ct);
        if (tournament is null)
            return WriteProblem(404, ErrorCodes.NotFound, "Tournament not found.");

        httpContext.Response.Headers.ETag = $"\"{tournament.Version}\"";
        return JsonOk(MapTournamentResponse(tournament));
    }

    private static async Task<IResult> RegisterParticipantAsync(
        Guid tournamentId,
        [FromBody] RegisterParticipantRequest request,
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
            var command = new RegisterParticipantCommand(
                request.ParticipantDisplayName,
                request.RosterInviteEmails);

            var participant = await tournamentService.RegisterParticipantAsync(tournamentId, command, userId.Value, ct);
            return JsonCreated($"/api/v1/participants/{participant.Id}", MapParticipantResponse(participant));
        }
        catch (TournamentOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.RegistrationClosed => (409, ex.Code),
                ErrorCodes.RegistrationFull => (409, ex.Code),
                ErrorCodes.DuplicatePlayerInTournament => (409, ex.Code),
                _ => (400, ex.Code),
            };
            return WriteProblem(status, code, ex.Message);
        }
    }

    private static async Task<IResult> AcceptMemberAsync(
        Guid participantId,
        ITournamentService tournamentService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        var userId = GetUserId(httpContext);
        if (userId is null)
            return WriteProblem(401, ErrorCodes.Unauthorized, "Authentication required.");

        try
        {
            var member = await tournamentService.AcceptMemberAsync(participantId, userId.Value, ct);
            return JsonOk(MapMemberResponse(member));
        }
        catch (ParticipantMemberOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                "member_not_found" => (404, ex.Code),
                _ => (409, ex.Code),
            };
            return WriteProblem(status, code, ex.Message);
        }
    }

    private static async Task<IResult> SeedAsync(
        Guid tournamentId,
        [FromBody] SeedTournamentRequest request,
        ITournamentService tournamentService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        var orgId = GetOrgId(httpContext);
        if (orgId is null)
            return WriteProblem(400, ErrorCodes.NoTenantResolved, "No organization context resolved.");

        try
        {
            var command = new SeedTournamentCommand(request.Method, request.Order);
            await tournamentService.SeedAsync(tournamentId, command, ct);
            return Results.Ok();
        }
        catch (TournamentOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.InvalidTournamentState => (409, ex.Code),
                ErrorCodes.InsufficientParticipants => (409, ex.Code),
                "seed_count_mismatch" => (422, ex.Code),
                "invalid_participant_id" => (422, ex.Code),
                "seed_not_supported" => (422, ex.Code),
                _ => (400, ex.Code),
            };
            return WriteProblem(status, code, ex.Message);
        }
    }

    private static async Task<IResult> GenerateBracketAsync(
        Guid tournamentId,
        [FromBody] GenerateBracketRequest request,
        ITournamentService tournamentService,
        HttpContext httpContext,
        CancellationToken ct)
    {
        var orgId = GetOrgId(httpContext);
        if (orgId is null)
            return WriteProblem(400, ErrorCodes.NoTenantResolved, "No organization context resolved.");

        try
        {
            var command = new GenerateBracketCommand(request.Force);
            var matches = await tournamentService.GenerateBracketAsync(tournamentId, command, ct);
            return JsonOk(matches.Select(MapMatchResponse).ToList());
        }
        catch (TournamentOperationException ex)
        {
            var (status, code) = ex.Code switch
            {
                ErrorCodes.InvalidTournamentState => (409, ex.Code),
                ErrorCodes.InsufficientParticipants => (409, ex.Code),
                ErrorCodes.BracketAlreadyGenerated => (409, ex.Code),
                "bracket_not_supported" => (422, ex.Code),
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

    private static TournamentResponse MapTournamentResponse(Tournament t) => new(
        t.Id,
        t.OrganizationId,
        t.LeagueId,
        t.SeasonId,
        t.DisciplineName,
        t.ResultModel.ToString().ToLowerInvariant(),
        t.TeamSize,
        t.FormatType.ToString().ToLowerInvariant(),
        t.ResultEntryMode.ToString().ToLowerInvariant(),
        t.State.ToString().ToLowerInvariant(),
        t.RngSeed,
        t.Currency,
        t.EntryFeeAmountMinor,
        t.BestOf,
        t.RegOpenAt,
        t.RegCloseAt,
        t.MaxParticipants,
        t.ScoreConfig,
        t.Version);

    private static ParticipantResponse MapParticipantResponse(Participant p) => new(
        p.Id,
        p.TournamentId,
        p.CaptainUserId,
        p.DisplayName,
        p.Status.ToString().ToLowerInvariant(),
        p.Version);

    private static MemberResponse MapMemberResponse(ParticipantMember m) => new(
        m.Id,
        m.ParticipantId,
        m.TournamentId,
        m.UserId,
        m.Status.ToString().ToLowerInvariant(),
        m.Version);

    private static MatchResponse MapMatchResponse(Match m) => new(
        m.Id,
        m.TournamentId,
        m.RoundNumber,
        m.PositionInRound,
        m.ParticipantAId,
        m.ParticipantBId,
        m.State.ToString().ToLowerInvariant(),
        m.IsByeMatch,
        m.Version);

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

internal sealed record CreateTournamentRequest(
    string DisciplineName,
    string ResultModel,
    int TeamSize,
    string FormatType,
    string? ResultEntryMode,
    Guid? LeagueId,
    Guid? SeasonId,
    TournamentScoreConfig? ScoreConfig,
    int? BestOf,
    string? Currency,
    long? EntryFeeAmountMinor,
    DateTime? RegOpenAt,
    DateTime? RegCloseAt,
    int? MaxParticipants);

internal sealed record RegisterParticipantRequest(
    string? ParticipantDisplayName,
    List<string>? RosterInviteEmails);

internal sealed record TournamentResponse(
    Guid Id,
    Guid OrganizationId,
    Guid? LeagueId,
    Guid? SeasonId,
    string DisciplineName,
    string ResultModel,
    int TeamSize,
    string FormatType,
    string ResultEntryMode,
    string State,
    string? RngSeed,
    string? Currency,
    long? EntryFeeAmountMinor,
    int? BestOf,
    DateTime? RegOpenAt,
    DateTime? RegCloseAt,
    int? MaxParticipants,
    TournamentScoreConfig? ScoreConfig,
    int Version);

internal sealed record ParticipantResponse(
    Guid Id,
    Guid TournamentId,
    Guid CaptainUserId,
    string? DisplayName,
    string Status,
    int Version);

internal sealed record MemberResponse(
    Guid Id,
    Guid ParticipantId,
    Guid TournamentId,
    Guid UserId,
    string Status,
    int Version);

internal sealed record SeedTournamentRequest(
    string Method,
    List<Guid>? Order);

internal sealed record GenerateBracketRequest(
    bool Force);

internal sealed record MatchResponse(
    Guid Id,
    Guid TournamentId,
    int Round,
    int Slot,
    Guid? ParticipantA,
    Guid? ParticipantB,
    string State,
    bool IsByeMatch,
    int Version);
