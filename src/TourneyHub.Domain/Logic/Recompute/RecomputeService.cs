using TourneyHub.Domain.Competition;

namespace TourneyHub.Domain.Logic.Recompute;

public sealed class RecomputeResult
{
    public List<AdvancementUpdate> AdvancementUpdates { get; init; } = [];
    public bool TournamentComplete { get; set; }
}

public sealed class AdvancementUpdate
{
    public Guid MatchId { get; init; }
    public Guid AdvancingParticipantId { get; init; }
}

public static class RecomputeService
{
    public static RecomputeResult Compute(
        IReadOnlyList<Match> matches,
        FormatType formatType,
        TournamentScoreConfig? scoreConfig)
    {
        ArgumentNullException.ThrowIfNull(matches);

        var result = new RecomputeResult();

        if (matches.Count == 0)
            return result;

        if (formatType == FormatType.SingleElimination)
        {
            ComputeSingleElimination(matches, scoreConfig, result);
        }

        return result;
    }

    private static void ComputeSingleElimination(
        IReadOnlyList<Match> matches,
        TournamentScoreConfig? scoreConfig,
        RecomputeResult result)
    {
        var lookup = matches.ToDictionary(m => m.Id);

        var completedOrWalkover = matches
            .Where(m => m.State is MatchState.Completed or MatchState.Walkover)
            .ToList();

        foreach (var match in completedOrWalkover)
        {
            var winner = DetermineWinner(match, scoreConfig);
            if (winner is null || match.AdvanceToMatchId is null)
                continue;

            result.AdvancementUpdates.Add(new AdvancementUpdate
            {
                MatchId = match.AdvanceToMatchId.Value,
                AdvancingParticipantId = winner.Value,
            });
        }

        var maxRound = matches.Max(m => m.RoundNumber);
        var finalRoundMatches = matches
            .Where(m => m.RoundNumber == maxRound)
            .ToList();

        result.TournamentComplete = finalRoundMatches.All(m =>
            m.State is MatchState.Completed or MatchState.Walkover);
    }

    public static Guid? DetermineWinner(Match match, TournamentScoreConfig? scoreConfig)
    {
        ArgumentNullException.ThrowIfNull(match);
        if (match.WinnerId is not null)
            return match.WinnerId;

        if (match.IsDraw)
            return null;

        if (match.ForfeitedParticipantId is not null)
        {
            if (match.ForfeitedParticipantId == match.ParticipantAId)
                return match.ParticipantBId;
            if (match.ForfeitedParticipantId == match.ParticipantBId)
                return match.ParticipantAId;
        }

        if (match.ScoreA.HasValue && match.ScoreB.HasValue)
        {
            if (match.ScoreA > match.ScoreB)
                return match.ParticipantAId;
            if (match.ScoreB > match.ScoreA)
                return match.ParticipantBId;
            return null;
        }

        return null;
    }
}