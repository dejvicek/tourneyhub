using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using TourneyHub.Application.Common;
using TourneyHub.Application.Competition;
using TourneyHub.Domain.Competition;
using TourneyHub.Domain.Logic.Formats;
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

    public async Task SeedAsync(Guid tournamentId, SeedTournamentCommand command, CancellationToken ct)
    {
        var tournament = await GetTournamentRequiredAsync(tournamentId, ct);

        if (tournament.FormatType != FormatType.SingleElimination && tournament.FormatType != FormatType.RoundRobin)
            throw new TournamentOperationException("seed_not_supported", "Seeding is only supported for Single Elimination and Round Robin tournaments.");

        if (tournament.State != TournamentState.RegistrationClosed)
            throw new TournamentOperationException(ErrorCodes.InvalidTournamentState, "Can only seed from RegistrationClosed state.");

        var confirmedParticipants = await _db.Participants
            .Where(p => p.TournamentId == tournamentId && p.Status == ParticipantState.Confirmed)
            .OrderBy(p => p.Id)
            .ToListAsync(ct);

        if (confirmedParticipants.Count < 2)
            throw new TournamentOperationException(ErrorCodes.InsufficientParticipants, "At least 2 confirmed participants are required to seed.");

        if (command.Method == "manual" && command.Order is { Count: > 0 })
        {
            if (command.Order.Count != confirmedParticipants.Count)
                throw new TournamentOperationException("seed_count_mismatch", $"Expected {confirmedParticipants.Count} participant IDs in seed order, got {command.Order.Count}.");

            var participantIds = confirmedParticipants.Select(p => p.Id).ToHashSet();
            foreach (var id in command.Order)
            {
                if (!participantIds.Contains(id))
                    throw new TournamentOperationException("invalid_participant_id", $"Participant {id} is not a confirmed participant in this tournament.");
            }

            var rngSeed = Guid.NewGuid().ToString("N");
            tournament.SetRngSeed(rngSeed);
        }
        else
        {
            var rngSeed = Guid.NewGuid().ToString("N");
            tournament.SetRngSeed(rngSeed);
        }

        tournament.Seed();
        await _db.SaveChangesAsync(ct);

        LogTournamentSeeded(tournamentId);
    }

    public async Task<IReadOnlyList<Match>> GenerateBracketAsync(Guid tournamentId, GenerateBracketCommand command, CancellationToken ct)
    {
        var tournament = await GetTournamentRequiredAsync(tournamentId, ct);

        if (tournament.FormatType != FormatType.SingleElimination)
            throw new TournamentOperationException("bracket_not_supported", "Bracket generation is only supported for Single Elimination tournaments.");

        if (!command.Force && tournament.State != TournamentState.Seeded)
            throw new TournamentOperationException(ErrorCodes.InvalidTournamentState, "Tournament must be in Seeded state to generate bracket.");

        if (command.Force && tournament.State is not TournamentState.Seeded and not TournamentState.InProgress)
            throw new TournamentOperationException(ErrorCodes.InvalidTournamentState, "Bracket can only be force-regenerated from Seeded or InProgress states.");

        var anyCompleted = await _db.Matches
            .AnyAsync(m => m.TournamentId == tournamentId && m.State == MatchState.Completed, ct);

        if (anyCompleted && !command.Force)
            throw new TournamentOperationException(ErrorCodes.BracketAlreadyGenerated, "Bracket cannot be regenerated after match results have been entered.");

        var existingMatches = await _db.Matches
            .Where(m => m.TournamentId == tournamentId)
            .ToListAsync(ct);

        var confirmedParticipants = await _db.Participants
            .Where(p => p.TournamentId == tournamentId && p.Status == ParticipantState.Confirmed)
            .OrderBy(p => p.Id)
            .ToListAsync(ct);

        if (confirmedParticipants.Count < 2)
            throw new TournamentOperationException(ErrorCodes.InsufficientParticipants, "At least 2 confirmed participants are required to generate a bracket.");

        int participantCount = confirmedParticipants.Count;
        var rngSeed = tournament.RngSeed ?? "default";

        var orderedSeeds = SingleEliminationGenerator.ShuffleSeeds(participantCount, rngSeed);
        var bracket = SingleEliminationGenerator.Generate(participantCount, rngSeed);

        var matches = new List<Match>();
        foreach (var bm in bracket.Matches)
        {
            int? seedA = bm.SeedA;
            int? seedB = bm.SeedB;

            Guid? participantAId = seedA.HasValue && seedA.Value <= orderedSeeds.Count
                ? confirmedParticipants[orderedSeeds[seedA.Value - 1] - 1].Id
                : null;

            Guid? participantBId = seedB.HasValue && seedB.Value <= orderedSeeds.Count
                ? confirmedParticipants[orderedSeeds[seedB.Value - 1] - 1].Id
                : null;

            var match = new Match(
                tournamentId,
                bm.RoundNumber,
                bm.PositionInRound,
                participantAId,
                participantBId,
                bm.IsByeMatch);

            matches.Add(match);
        }

        for (int i = 0; i < matches.Count; i++)
        {
            var bm = bracket.Matches[i];
            if (bm.AdvanceToRound.HasValue && bm.AdvanceToPosition.HasValue)
            {
                var advanceToMatch = matches.First(m =>
                    m.RoundNumber == bm.AdvanceToRound.Value &&
                    m.PositionInRound == bm.AdvanceToPosition.Value);
                matches[i].SetAdvanceToMatch(advanceToMatch.Id);
            }
        }

        if (existingMatches.Count > 0)
        {
            _db.Matches.RemoveRange(existingMatches);
        }

        _db.Matches.AddRange(matches);

        if (tournament.State == TournamentState.Seeded)
        {
            tournament.StartInProgress();
        }

        await _db.SaveChangesAsync(ct);

        LogBracketGenerated(tournamentId, matches.Count);
        return matches.AsReadOnly();
    }

    public async Task<IReadOnlyList<Match>> GenerateScheduleAsync(Guid tournamentId, GenerateBracketCommand command, CancellationToken ct)
    {
        var tournament = await GetTournamentRequiredAsync(tournamentId, ct);

        if (tournament.FormatType != FormatType.RoundRobin)
            throw new TournamentOperationException("schedule_not_supported", "Schedule generation is only supported for Round Robin tournaments.");

        if (!command.Force && tournament.State != TournamentState.Seeded)
            throw new TournamentOperationException(ErrorCodes.InvalidTournamentState, "Tournament must be in Seeded state to generate schedule.");

        if (command.Force && tournament.State is not TournamentState.Seeded and not TournamentState.InProgress)
            throw new TournamentOperationException(ErrorCodes.InvalidTournamentState, "Schedule can only be force-regenerated from Seeded or InProgress states.");

        var anyCompleted = await _db.Matches
            .AnyAsync(m => m.TournamentId == tournamentId && m.State == MatchState.Completed, ct);

        if (anyCompleted && !command.Force)
            throw new TournamentOperationException(ErrorCodes.BracketAlreadyGenerated, "Schedule cannot be regenerated after match results have been entered.");

        var existingMatches = await _db.Matches
            .Where(m => m.TournamentId == tournamentId)
            .ToListAsync(ct);

        var confirmedParticipants = await _db.Participants
            .Where(p => p.TournamentId == tournamentId && p.Status == ParticipantState.Confirmed)
            .OrderBy(p => p.Id)
            .ToListAsync(ct);

        if (confirmedParticipants.Count < 2)
            throw new TournamentOperationException(ErrorCodes.InsufficientParticipants, "At least 2 confirmed participants are required to generate a schedule.");

        int participantCount = confirmedParticipants.Count;
        var rngSeed = tournament.RngSeed ?? "default";

        var shuffledSeeds = RoundRobinGenerator.ShuffleParticipants(participantCount, rngSeed);
        var schedule = RoundRobinGenerator.Generate(participantCount);

        var matches = new List<Match>();
        foreach (var round in schedule.Rounds)
        {
            int positionInRound = 1;

            foreach (var pairing in round.Pairings)
            {
                int seedA = pairing.SeedA;
                int seedB = pairing.SeedB;

                Guid participantAId = confirmedParticipants[shuffledSeeds[seedA - 1] - 1].Id;
                Guid participantBId = confirmedParticipants[shuffledSeeds[seedB - 1] - 1].Id;

                var match = new Match(
                    tournamentId,
                    round.RoundNumber,
                    positionInRound,
                    participantAId,
                    participantBId,
                    false);

                matches.Add(match);
                positionInRound++;
            }

            foreach (var byeSeed in round.Byes)
            {
                Guid byeParticipantId = confirmedParticipants[shuffledSeeds[byeSeed - 1] - 1].Id;

                var match = new Match(
                    tournamentId,
                    round.RoundNumber,
                    positionInRound,
                    byeParticipantId,
                    null,
                    true);

                matches.Add(match);
                positionInRound++;
            }
        }

        if (existingMatches.Count > 0)
        {
            _db.Matches.RemoveRange(existingMatches);
        }

        _db.Matches.AddRange(matches);

        if (tournament.State == TournamentState.Seeded)
        {
            tournament.StartInProgress();
        }

        await _db.SaveChangesAsync(ct);

        LogScheduleGenerated(tournamentId, matches.Count);
        return matches.AsReadOnly();
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

    [LoggerMessage(Level = LogLevel.Information, Message = "Tournament {TournamentId} seeded")]
    private partial void LogTournamentSeeded(Guid tournamentId);

    [LoggerMessage(Level = LogLevel.Information, Message = "Bracket generated for tournament {TournamentId} with {MatchCount} matches")]
    private partial void LogBracketGenerated(Guid tournamentId, int matchCount);

    [LoggerMessage(Level = LogLevel.Information, Message = "Schedule generated for tournament {TournamentId} with {MatchCount} matches")]
    private partial void LogScheduleGenerated(Guid tournamentId, int matchCount);
}
