using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using TourneyHub.Application.Common;
using TourneyHub.Application.Competition;
using TourneyHub.Domain.Competition;
using TourneyHub.Infrastructure.Persistence;

namespace TourneyHub.Infrastructure.Competition;

internal sealed partial class TournamentService : ITournamentService
{
    private readonly TourneyHubDbContext _db;
    private readonly ILogger<TournamentService> _logger;

    public TournamentService(TourneyHubDbContext db, ILogger<TournamentService> logger)
    {
        _db = db;
        _logger = logger;
    }

    public async Task<Tournament> CreateAsync(
        CreateTournamentCommand command, Guid organizationId, Guid ownerUserId, CancellationToken ct)
    {
        var resultModel = MapResultModel(command.ResultModel);
        var formatType = MapFormatType(command.FormatType);
        var resultEntryMode = MapResultEntryMode(command.ResultEntryMode);

        if (command.LeagueId.HasValue)
        {
            var league = await _db.Leagues
                .FirstOrDefaultAsync(l => l.Id == command.LeagueId.Value && l.State != LeagueState.Deleted, ct);
            if (league is null)
                throw new TournamentOperationException(ErrorCodes.LeagueNotFound, "League not found.");

            if (command.SeasonId.HasValue)
            {
                var season = await _db.Seasons
                    .FirstOrDefaultAsync(s => s.Id == command.SeasonId.Value, ct);
                if (season is null || season.LeagueId != league.Id)
                    throw new TournamentOperationException("season_not_found", "Season not found or does not belong to the specified league.");
            }
        }

        var tournament = new Tournament(
            command.DisciplineName,
            resultModel,
            command.TeamSize,
            formatType,
            resultEntryMode,
            command.LeagueId,
            command.SeasonId,
            command.ScoreConfig,
            command.BestOf,
            command.Currency,
            command.EntryFeeAmountMinor,
            command.RegOpenAt,
            command.RegCloseAt,
            command.MaxParticipants);

        tournament.OpenRegistration();

        _db.Tournaments.Add(tournament);
        await _db.SaveChangesAsync(ct);

        LogTournamentCreated(tournament.Id, tournament.DisciplineName);
        return tournament;
    }

    public async Task<IReadOnlyList<Tournament>> ListAsync(
        Guid organizationId, Guid? leagueId, string? status, CancellationToken ct)
    {
        var query = _db.Tournaments.AsQueryable();

        if (leagueId.HasValue)
        {
            query = query.Where(t => t.LeagueId == leagueId.Value);
        }

        if (!string.IsNullOrWhiteSpace(status)
            && Enum.TryParse<TournamentState>(status, ignoreCase: true, out var state))
        {
            query = query.Where(t => t.State == state);
        }

        return await query
            .OrderByDescending(t => t.State == TournamentState.RegistrationOpen)
            .ThenByDescending(t => t.State == TournamentState.InProgress)
            .ThenBy(t => t.DisciplineName)
            .ToListAsync(ct);
    }

    public async Task<Tournament?> GetByIdAsync(Guid tournamentId, CancellationToken ct)
    {
        return await _db.Tournaments
            .FirstOrDefaultAsync(t => t.Id == tournamentId, ct);
    }

    public async Task<Participant> RegisterParticipantAsync(
        Guid tournamentId,
        RegisterParticipantCommand command,
        Guid submittedByUserId,
        CancellationToken ct)
    {
        var tournament = await GetTournamentRequiredAsync(tournamentId, ct);

        if (!tournament.IsRegistrationOpen())
            throw new TournamentOperationException(ErrorCodes.RegistrationClosed, "Registration is not open for this tournament.");

        if (tournament.MaxParticipants.HasValue)
        {
            var confirmedCount = await _db.Participants
                .CountAsync(p => p.TournamentId == tournamentId && p.Status == ParticipantState.Confirmed, ct);
            if (confirmedCount >= tournament.MaxParticipants.Value)
                throw new TournamentOperationException(ErrorCodes.RegistrationFull, "Tournament has reached its maximum capacity.");
        }

        var alreadyMember = await _db.ParticipantMembers
            .AnyAsync(m => m.TournamentId == tournamentId && m.UserId == submittedByUserId, ct);
        if (alreadyMember)
            throw new TournamentOperationException(ErrorCodes.DuplicatePlayerInTournament, "You are already registered in this tournament.");

        var participant = new Participant(tournamentId, submittedByUserId, command.ParticipantDisplayName);

        _db.Participants.Add(participant);

        _db.ParticipantMembers.Add(new ParticipantMember(
            participant.Id, tournamentId, submittedByUserId, ParticipantMemberStatus.Accepted));

        if (command.RosterInviteEmails is { Count: > 0 })
        {
            if (tournament.TeamSize == 1)
                throw new TournamentOperationException("roster_not_applicable", "Roster invites are only valid for team tournaments (teamSize > 1).");

            var maxInvites = tournament.TeamSize - 1;
            if (command.RosterInviteEmails.Count > maxInvites)
                throw new TournamentOperationException("too_many_invites", $"You can only invite up to {maxInvites} additional members.");

            foreach (var email in command.RosterInviteEmails)
            {
                var normalizedEmail = email.Trim().ToUpperInvariant();
                var user = await _db.Users
                    .FirstOrDefaultAsync(u => u.NormalizedEmail == normalizedEmail, ct);
                if (user is null)
                    throw new TournamentOperationException("user_not_found", $"User with email '{email}' not found.");

                var duplicate = await _db.ParticipantMembers
                    .AnyAsync(m => m.TournamentId == tournamentId && m.UserId == user.Id, ct);
                if (duplicate)
                    throw new TournamentOperationException(ErrorCodes.DuplicatePlayerInTournament, $"User '{email}' is already registered in this tournament.");

                _db.ParticipantMembers.Add(new ParticipantMember(
                    participant.Id, tournamentId, user.Id, ParticipantMemberStatus.Pending));
            }
        }

        if (tournament.TeamSize == 1)
        {
            participant.Confirm();
        }

        await _db.SaveChangesAsync(ct);

        LogParticipantRegistered(participant.Id, tournamentId);
        return participant;
    }

    public async Task<ParticipantMember> AcceptMemberAsync(Guid participantId, Guid userId, CancellationToken ct)
    {
        var member = await _db.ParticipantMembers
            .FirstOrDefaultAsync(m => m.ParticipantId == participantId && m.UserId == userId, ct)
            ?? throw new ParticipantMemberOperationException("member_not_found", "Member record not found.");

        member.Accept();

        var participant = await _db.Participants
            .FirstAsync(p => p.Id == participantId, ct);

        var tournament = await GetTournamentRequiredAsync(participant.TournamentId, ct);

        var acceptedCount = await _db.ParticipantMembers
            .CountAsync(m => m.ParticipantId == participantId && m.Status == ParticipantMemberStatus.Accepted, ct);

        if (acceptedCount >= tournament.TeamSize && participant.Status == ParticipantState.Incomplete)
        {
            participant.Confirm();
        }

        await _db.SaveChangesAsync(ct);

        LogMemberAccepted(member.Id, participantId, userId);
        return member;
    }

    private async Task<Tournament> GetTournamentRequiredAsync(Guid tournamentId, CancellationToken ct)
    {
        return await _db.Tournaments.FirstOrDefaultAsync(t => t.Id == tournamentId, ct)
            ?? throw new TournamentOperationException("tournament_not_found", "Tournament not found.");
    }

    private static ResultModel MapResultModel(string resultModel) => resultModel.ToLowerInvariant() switch
    {
        "winner" => ResultModel.Winner,
        "score" => ResultModel.Score,
        _ => throw new TournamentOperationException("invalid_result_model", $"Invalid result model: {resultModel}. Must be 'winner' or 'score'."),
    };

    private static FormatType MapFormatType(string formatType) => formatType.ToLowerInvariant() switch
    {
        "singleelimination" => FormatType.SingleElimination,
        "roundrobin" => FormatType.RoundRobin,
        _ => throw new TournamentOperationException("invalid_format_type", $"Invalid format type: {formatType}. Must be 'SingleElimination' or 'RoundRobin'."),
    };

    private static ResultEntryMode MapResultEntryMode(string? resultEntryMode) => resultEntryMode?.ToLowerInvariant() switch
    {
        null or "organizer" => ResultEntryMode.Organizer,
        "playerselfreport" => ResultEntryMode.PlayerSelfReport,
        _ => throw new TournamentOperationException("invalid_result_entry_mode", $"Invalid result entry mode: {resultEntryMode}. Must be 'organizer' or 'playerSelfReport'."),
    };

    [LoggerMessage(Level = LogLevel.Information, Message = "Tournament {TournamentId} '{DisciplineName}' created")]
    private partial void LogTournamentCreated(Guid tournamentId, string disciplineName);

    [LoggerMessage(Level = LogLevel.Information, Message = "Participant {ParticipantId} registered for tournament {TournamentId}")]
    private partial void LogParticipantRegistered(Guid participantId, Guid tournamentId);

    [LoggerMessage(Level = LogLevel.Information, Message = "Member {MemberId} accepted for participant {ParticipantId}, user {UserId}")]
    private partial void LogMemberAccepted(Guid memberId, Guid participantId, Guid userId);
}
