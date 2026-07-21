using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using TourneyHub.Application.Common;
using TourneyHub.Application.Competition;
using TourneyHub.Domain.Competition;
using TourneyHub.Domain.Logic.Formats;
using TourneyHub.Domain.Logic.Rankings;
using TourneyHub.Domain.Logic.Recompute;
using TourneyHub.Domain.Logic.Scoring;
using TourneyHub.Domain.Platform;
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

        foreach (var match in matches)
        {
            if (match.IsByeMatch)
            {
                var advancingId = match.ParticipantAId ?? match.ParticipantBId;
                if (advancingId is not null)
                {
                    match.MarkWalkover(advancingId.Value);
                }
            }
            else if (match.ParticipantAId is not null && match.ParticipantBId is not null)
            {
                match.SetReady();
            }
        }

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

        foreach (var match in matches)
        {
            if (match.IsByeMatch)
            {
                var advancingId = match.ParticipantAId ?? match.ParticipantBId;
                if (advancingId is not null)
                {
                    match.MarkWalkover(advancingId.Value);
                }
            }
            else if (match.ParticipantAId is not null && match.ParticipantBId is not null)
            {
                match.SetReady();
            }
        }

        if (tournament.State == TournamentState.Seeded)
        {
            tournament.StartInProgress();
        }

        await _db.SaveChangesAsync(ct);

        LogScheduleGenerated(tournamentId, matches.Count);
        return matches.AsReadOnly();
    }

    public async Task<Match> SubmitResultAsync(
        Guid matchId,
        SubmitResultCommand command,
        Guid organizationId,
        Guid actorUserId,
        int ifMatchVersion,
        CancellationToken ct)
    {
        var match = await _db.Matches
            .FirstOrDefaultAsync(m => m.Id == matchId, ct)
            ?? throw new MatchOperationException(ErrorCodes.MatchNotFound, "Match not found.");

        if (match.Version != ifMatchVersion)
            throw new MatchOperationException(ErrorCodes.ConcurrencyConflict, "Stale version. Please refresh and try again.");

        var tournament = await _db.Tournaments
            .FirstOrDefaultAsync(t => t.Id == match.TournamentId, ct)
            ?? throw new TournamentOperationException("tournament_not_found", "Tournament not found.");

        if (tournament.State != TournamentState.InProgress)
        {
            if (tournament.State == TournamentState.Completed)
            {
                tournament.Reopen();
            }
            else
            {
                throw new TournamentOperationException(ErrorCodes.InvalidTournamentState, "Can only submit results for InProgress tournaments.");
            }
        }

        ValidateResult(command, tournament.ResultModel, tournament.ScoreConfig, match);

        var isEdit = match.State == MatchState.Completed;

        if (isEdit)
        {
            match.EditResult(command.ScoreA, command.ScoreB, command.WinnerId, command.ForfeitedParticipantId, command.IsDraw);
        }
        else
        {
            match.SubmitResult(command.ScoreA, command.ScoreB, command.WinnerId, command.ForfeitedParticipantId, command.IsDraw);
        }

if (match.WinnerId is null && !match.IsDraw && match.ForfeitedParticipantId is null)
            {
                var determinedWinner = RecomputeService.DetermineWinner(match, tournament.ScoreConfig);
                if (determinedWinner is not null)
                {
                    match.SetWinner(determinedWinner.Value);
                }
            }

        match.ConfirmResult();

        var matches = await _db.Matches
            .Where(m => m.TournamentId == tournament.Id)
            .ToListAsync(ct);

        var recomputeResult = RecomputeService.Compute(matches, tournament.FormatType, tournament.ScoreConfig);

        foreach (var update in recomputeResult.AdvancementUpdates)
        {
            var targetMatch = matches.First(m => m.Id == update.MatchId);
            targetMatch.SetParticipant(update.AdvancingParticipantId);

            if (targetMatch.ParticipantAId is not null && targetMatch.ParticipantBId is not null
                && targetMatch.State == MatchState.Pending)
            {
                targetMatch.SetReady();
            }
        }

        if (recomputeResult.TournamentComplete)
        {
            tournament.Complete();
        }

        await RecomputeStandingsAndRankingsAsync(tournament, ct);

        _db.AuditEvents.Add(new AuditEvent(
                actorUserId.ToString(),
                isEdit ? "result_edit" : "result_submit",
                "Match",
                match.Id.ToString(),
                null,
                System.Text.Json.JsonSerializer.Serialize(new { match.ScoreA, match.ScoreB, match.WinnerId, match.ForfeitedParticipantId, match.IsDraw, match.State }),
                null,
                null));

        await _db.SaveChangesAsync(ct);

        LogResultSubmitted(match.Id, match.TournamentId);
        return match;
    }

    public async Task<Match> ForfeitMatchAsync(
        Guid matchId,
        ForfeitMatchCommand command,
        Guid organizationId,
        Guid actorUserId,
        CancellationToken ct)
    {
        var match = await _db.Matches
            .FirstOrDefaultAsync(m => m.Id == matchId, ct)
            ?? throw new MatchOperationException(ErrorCodes.MatchNotFound, "Match not found.");

        var tournament = await _db.Tournaments
            .FirstOrDefaultAsync(t => t.Id == match.TournamentId, ct)
            ?? throw new TournamentOperationException("tournament_not_found", "Tournament not found.");

        if (tournament.State != TournamentState.InProgress)
            throw new TournamentOperationException(ErrorCodes.InvalidTournamentState, "Can only forfeit matches in InProgress tournaments.");

        if (match.ForfeitedParticipantId is not null)
            throw new MatchOperationException(ErrorCodes.InvalidForfeit, "Match has already been forfeited.");

        if (command.ForfeitedParticipantId != match.ParticipantAId
            && command.ForfeitedParticipantId != match.ParticipantBId)
            throw new MatchOperationException(ErrorCodes.InvalidForfeit, "Forfeited participant is not in this match.");

        var winnerId = command.ForfeitedParticipantId == match.ParticipantAId
            ? match.ParticipantBId
            : match.ParticipantAId;

        match.SubmitResult(null, null, winnerId, command.ForfeitedParticipantId, false);
        match.ConfirmResult();

        var matches = await _db.Matches
            .Where(m => m.TournamentId == tournament.Id)
            .ToListAsync(ct);

        var recomputeResult = RecomputeService.Compute(matches, tournament.FormatType, tournament.ScoreConfig);

        foreach (var update in recomputeResult.AdvancementUpdates)
        {
            var targetMatch = matches.First(m => m.Id == update.MatchId);
            targetMatch.SetParticipant(update.AdvancingParticipantId);

            if (targetMatch.ParticipantAId is not null && targetMatch.ParticipantBId is not null
                && targetMatch.State == MatchState.Pending)
            {
                targetMatch.SetReady();
            }
        }

        if (recomputeResult.TournamentComplete)
        {
            tournament.Complete();
        }

        await RecomputeStandingsAndRankingsAsync(tournament, ct);

        _db.AuditEvents.Add(new AuditEvent(
                actorUserId.ToString(),
                "forfeit",
                "Match",
                match.Id.ToString(),
                null,
                System.Text.Json.JsonSerializer.Serialize(new { match.WinnerId, match.ForfeitedParticipantId, match.State }),
                null,
                null));

        await _db.SaveChangesAsync(ct);

        LogForfeit(match.Id, command.ForfeitedParticipantId);
        return match;
    }

    public async Task<Participant> WithdrawParticipantAsync(
        Guid participantId,
        Guid organizationId,
        Guid actorUserId,
        CancellationToken ct)
    {
        var participant = await _db.Participants
            .FirstOrDefaultAsync(p => p.Id == participantId, ct)
            ?? throw new ParticipantOperationException("participant_not_found", "Participant not found.");

        var tournament = await _db.Tournaments
            .FirstOrDefaultAsync(t => t.Id == participant.TournamentId, ct)
            ?? throw new TournamentOperationException("tournament_not_found", "Tournament not found.");

        if (tournament.State is not TournamentState.InProgress and not TournamentState.Seeded)
            throw new TournamentOperationException(ErrorCodes.InvalidTournamentState, "Can only withdraw from InProgress or Seeded tournaments.");

        var remainingMatches = await _db.Matches
            .Where(m => m.TournamentId == tournament.Id
                        && m.State != MatchState.Completed
                        && m.State != MatchState.Walkover
                        && m.State != MatchState.Cancelled
                        && (m.ParticipantAId == participantId || m.ParticipantBId == participantId))
            .ToListAsync(ct);

        foreach (var match in remainingMatches)
        {
            match.Cancel();

            _db.AuditEvents.Add(new AuditEvent(
                    actorUserId.ToString(),
                    "match_cancelled_due_to_withdrawal",
                    "Match",
                    match.Id.ToString(),
                    null,
                    System.Text.Json.JsonSerializer.Serialize(new { reason = "participant_withdrawal", participantId }),
                    null,
                    null));
        }

        participant.Withdraw(tournament.Id);

        await RecomputeStandingsAndRankingsAsync(tournament, ct);

        await _db.SaveChangesAsync(ct);

        LogWithdrawal(participantId, tournament.Id);
        return participant;
    }

    public async Task<IReadOnlyList<TournamentStanding>> GetTournamentStandingsAsync(
        Guid tournamentId,
        CancellationToken ct)
    {
        return await _db.TournamentStandings
            .Where(s => s.TournamentId == tournamentId)
            .OrderBy(s => s.Rank)
            .ToListAsync(ct);
    }

    public async Task<TournamentOverview?> GetTournamentOverviewAsync(
        Guid tournamentId,
        CancellationToken ct)
    {
        var tournament = await _db.Tournaments
            .IgnoreQueryFilters()
            .FirstOrDefaultAsync(t => t.Id == tournamentId, ct);

        if (tournament is null)
            return null;

        var matches = await _db.Matches
            .IgnoreQueryFilters()
            .Where(m => m.TournamentId == tournamentId)
            .OrderBy(m => m.RoundNumber).ThenBy(m => m.PositionInRound)
            .ToListAsync(ct);

        var standings = await _db.TournamentStandings
            .IgnoreQueryFilters()
            .Where(s => s.TournamentId == tournamentId)
            .OrderBy(s => s.Rank)
            .ToListAsync(ct);

        return new TournamentOverview(tournament, matches.AsReadOnly(), standings.AsReadOnly());
    }

    public async Task<IReadOnlyList<SeasonRanking>> GetSeasonRankingsAsync(
        Guid seasonId,
        CancellationToken ct)
    {
        return await _db.SeasonRankings
            .Where(r => r.SeasonId == seasonId)
            .OrderBy(r => r.Rank)
            .ToListAsync(ct);
    }

    private async Task RecomputeStandingsAndRankingsAsync(
        Tournament tournament,
        CancellationToken ct)
    {
        var scoringConfig = RankingCalculator.GetDefaultScoringConfig();

        var participants = await _db.Participants
            .Where(p => p.TournamentId == tournament.Id)
            .ToListAsync(ct);

        var matches = await _db.Matches
            .Where(m => m.TournamentId == tournament.Id)
            .ToListAsync(ct);

        var seasonId = tournament.SeasonId;

        var standingsResult = RankingCalculator.ComputeTournamentStandings(
            tournament.Id,
            seasonId,
            participants.Select(p => p.Id).ToList(),
            matches,
            scoringConfig,
            tournament.RngSeed ?? "default-seed");

        var existingStandings = await _db.TournamentStandings
            .Where(s => s.TournamentId == tournament.Id)
            .ToListAsync(ct);

        foreach (var input in standingsResult.Standings)
        {
            var existing = existingStandings.FirstOrDefault(s => s.ParticipantId == input.ParticipantId);
            if (existing is not null)
            {
                existing.UpdateFromEntry(input.Points, input.Wins, input.Losses, input.Draws,
                    input.PointsScored, input.PointsConceded, input.PointsDifference, input.Byes, input.Rank);
            }
            else
            {
                _db.TournamentStandings.Add(new TournamentStanding(
                    input.TournamentId,
                    input.ParticipantId,
                    input.Points,
                    input.Wins,
                    input.Losses,
                    input.Draws,
                    input.PointsScored,
                    input.PointsConceded,
                    input.PointsDifference,
                    input.Byes,
                    input.Rank));
            }
        }

        if (seasonId.HasValue)
        {
            var season = await _db.Seasons.FirstOrDefaultAsync(s => s.Id == seasonId.Value, ct);
            if (season is not null && season.State == SeasonState.Closed)
            {
                return;
            }

            var allTournamentStandings = new List<TournamentStandingsResult>();
            var participantMembers = new Dictionary<Guid, IReadOnlyList<Guid>>();

            if (tournament.State == TournamentState.Completed)
            {
                allTournamentStandings.Add(standingsResult);
            }

            var persistedSeasonTournaments = await _db.Tournaments
                .Where(t => t.SeasonId == seasonId.Value
                            && t.State == TournamentState.Completed
                            && t.Id != tournament.Id)
                .ToListAsync(ct);

            foreach (var p in participants)
            {
                if (!participantMembers.ContainsKey(p.Id))
                {
                    var members = await _db.ParticipantMembers
                        .Where(m => m.ParticipantId == p.Id && m.Status == ParticipantMemberStatus.Accepted)
                        .Select(m => m.UserId)
                        .ToListAsync(ct);

                    participantMembers[p.Id] = members;
                }
            }

            foreach (var seasonTournament in persistedSeasonTournaments)
            {
                var tnParticipants = await _db.Participants
                    .Where(p => p.TournamentId == seasonTournament.Id)
                    .ToListAsync(ct);

                foreach (var p in tnParticipants)
                {
                    if (!participantMembers.ContainsKey(p.Id))
                    {
                        var members = await _db.ParticipantMembers
                            .Where(m => m.ParticipantId == p.Id && m.Status == ParticipantMemberStatus.Accepted)
                            .Select(m => m.UserId)
                            .ToListAsync(ct);

                        participantMembers[p.Id] = members;
                    }
                }

                var tnMatches = await _db.Matches
                    .Where(m => m.TournamentId == seasonTournament.Id)
                    .ToListAsync(ct);

                var tnStandings = RankingCalculator.ComputeTournamentStandings(
                    seasonTournament.Id,
                    seasonId,
                    tnParticipants.Select(p => p.Id).ToList(),
                    tnMatches,
                    scoringConfig,
                    seasonTournament.RngSeed ?? "default-seed");

                allTournamentStandings.Add(tnStandings);
            }

            if (allTournamentStandings.Count > 0)
            {
                var seasonRankingsResult = RankingCalculator.ComputeSeasonRankings(
                    seasonId.Value,
                    allTournamentStandings,
                    participantMembers);

                var existingRankings = await _db.SeasonRankings
                    .Where(r => r.SeasonId == seasonId.Value)
                    .ToListAsync(ct);

                foreach (var input in seasonRankingsResult.Rankings)
                {
                    var existing = existingRankings.FirstOrDefault(r => r.UserId == input.UserId);
                    if (existing is not null)
                    {
                        existing.UpdateFromEntry(input.Points, input.MatchesPlayed, input.Rank);
                    }
                    else
                    {
                        _db.SeasonRankings.Add(new SeasonRanking(
                            input.SeasonId,
                            input.UserId,
                            input.Points,
                            input.MatchesPlayed,
                            input.Rank));
                    }
                }
            }
        }
    }

    private async Task<Tournament> GetTournamentRequiredAsync(Guid tournamentId, CancellationToken ct)
    {
        return await _db.Tournaments.FirstOrDefaultAsync(t => t.Id == tournamentId, ct)
            ?? throw new TournamentOperationException("tournament_not_found", "Tournament not found.");
    }

    private static void ValidateResult(
        SubmitResultCommand command,
        ResultModel resultModel,
        TournamentScoreConfig? scoreConfig,
        Match match)
    {
        if (command.ForfeitedParticipantId is not null)
        {
            if (command.ForfeitedParticipantId != match.ParticipantAId
                && command.ForfeitedParticipantId != match.ParticipantBId)
                throw new MatchOperationException(ErrorCodes.InvalidForfeit, "Forfeited participant is not in this match.");

            if (command.WinnerId is null)
                throw new MatchOperationException(ErrorCodes.WinnerMismatch, "Winner must be specified when a participant forfeits.");
            return;
        }

        if (command.IsDraw && scoreConfig is not null && !scoreConfig.AllowDraws)
            throw new MatchOperationException(ErrorCodes.DrawsNotAllowed, "Draws are not allowed by the tournament's score configuration.");

        if (resultModel == ResultModel.Score && command.ScoreA.HasValue && command.ScoreB.HasValue)
        {
            if (command.ScoreA.Value < 0 || command.ScoreB.Value < 0)
                throw new MatchOperationException(ErrorCodes.ScoreOutOfRange, "Scores cannot be negative.");

            if (scoreConfig is not null)
            {
                if (scoreConfig.MinScore.HasValue && (command.ScoreA.Value < scoreConfig.MinScore.Value || command.ScoreB.Value < scoreConfig.MinScore.Value))
                    throw new MatchOperationException(ErrorCodes.ScoreOutOfRange, $"Scores must be at least {scoreConfig.MinScore.Value}.");

                if (scoreConfig.MaxScore.HasValue && (command.ScoreA.Value > scoreConfig.MaxScore.Value || command.ScoreB.Value > scoreConfig.MaxScore.Value))
                    throw new MatchOperationException(ErrorCodes.ScoreOutOfRange, $"Scores must be at most {scoreConfig.MaxScore.Value}.");
            }

            if (!command.IsDraw && command.WinnerId is not null)
            {
                if (command.ScoreA > command.ScoreB && command.WinnerId != match.ParticipantAId)
                    throw new MatchOperationException(ErrorCodes.WinnerMismatch, "Winner must be the participant with the higher score.");

                if (command.ScoreB > command.ScoreA && command.WinnerId != match.ParticipantBId)
                    throw new MatchOperationException(ErrorCodes.WinnerMismatch, "Winner must be the participant with the higher score.");
            }
        }

        if (resultModel == ResultModel.Winner && !command.IsDraw && command.WinnerId is null)
            throw new MatchOperationException(ErrorCodes.WinnerMismatch, "Winner must be specified for result model 'winner'.");
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

    [LoggerMessage(Level = LogLevel.Information, Message = "Match result submitted for match {MatchId} in tournament {TournamentId}")]
    private partial void LogResultSubmitted(Guid matchId, Guid tournamentId);

    [LoggerMessage(Level = LogLevel.Information, Message = "Forfeit recorded for match {MatchId}, forfeited participant {ParticipantId}")]
    private partial void LogForfeit(Guid matchId, Guid participantId);

    [LoggerMessage(Level = LogLevel.Information, Message = "Participant {ParticipantId} withdrew from tournament {TournamentId}")]
    private partial void LogWithdrawal(Guid participantId, Guid tournamentId);
}
