using TourneyHub.Domain.Competition;
using TourneyHub.Domain.Logic.Scoring;

namespace TourneyHub.Domain.Logic.Rankings;

public sealed record TournamentStandingInput(
    Guid TournamentId,
    Guid ParticipantId,
    Guid? SeasonId,
    int Points,
    int Wins,
    int Losses,
    int Draws,
    int PointsScored,
    int PointsConceded,
    int PointsDifference,
    int Byes,
    int Rank);

public sealed record SeasonRankingInput(
    Guid SeasonId,
    Guid UserId,
    int Points,
    int MatchesPlayed,
    int Rank);

public sealed record TournamentStandingsResult(
    Guid TournamentId,
    IReadOnlyList<TournamentStandingInput> Standings);

public sealed record SeasonRankingsResult(
    Guid SeasonId,
    IReadOnlyList<SeasonRankingInput> Rankings);

public static class RankingCalculator
{
    public static TournamentStandingsResult ComputeTournamentStandings(
        Guid tournamentId,
        Guid? seasonId,
        IReadOnlyList<Guid> participantIds,
        IReadOnlyList<Match> completedMatches,
        ScoringConfig scoringConfig,
        string rngSeed)
    {
        ArgumentNullException.ThrowIfNull(participantIds);
        ArgumentNullException.ThrowIfNull(completedMatches);
        ArgumentNullException.ThrowIfNull(scoringConfig);
        ArgumentNullException.ThrowIfNull(rngSeed);

        var matchInputs = completedMatches
            .Where(m => m.State is MatchState.Completed or MatchState.Walkover)
            .Select(m => ConvertToMatchInput(m))
            .ToList();

        var standings = TieBreakerResolver.ComputeStandings(participantIds, matchInputs, scoringConfig, rngSeed);

        var result = standings.Select(s => new TournamentStandingInput(
            tournamentId,
            s.ParticipantId,
            seasonId,
            s.Points,
            s.Wins,
            s.Losses,
            s.Draws,
            s.PointsScored,
            s.PointsConceded,
            s.PointsDifference,
            s.Byes,
            s.Rank)).ToList();

        return new TournamentStandingsResult(tournamentId, result.AsReadOnly());
    }

    public static SeasonRankingsResult ComputeSeasonRankings(
        Guid seasonId,
        IReadOnlyList<TournamentStandingsResult> tournamentStandings,
        IReadOnlyDictionary<Guid, IReadOnlyList<Guid>> participantMembers)
    {
        ArgumentNullException.ThrowIfNull(tournamentStandings);
        ArgumentNullException.ThrowIfNull(participantMembers);

        var userStats = new Dictionary<Guid, (int points, int matchesPlayed)>();

        foreach (var tournamentResult in tournamentStandings)
        {
            foreach (var standing in tournamentResult.Standings)
            {
                if (!participantMembers.TryGetValue(standing.ParticipantId, out var members)
                    || members.Count == 0)
                {
                    continue;
                }

                var matchesPlayedPerMember = standing.Wins + standing.Losses + standing.Draws + standing.Byes;

                foreach (var userId in members)
                {
                    if (!userStats.TryGetValue(userId, out var stats))
                    {
                        stats = (0, 0);
                    }

                    userStats[userId] = (
                        stats.points + standing.Points,
                        stats.matchesPlayed + matchesPlayedPerMember
                    );
                }
            }
        }

        var sorted = userStats
            .OrderByDescending(kv => kv.Value.points)
            .ThenBy(kv => kv.Key)
            .ToList();

        var rankings = new List<SeasonRankingInput>();
        int rank = 1;
        foreach (var (userId, (points, matchesPlayed)) in sorted)
        {
            rankings.Add(new SeasonRankingInput(seasonId, userId, points, matchesPlayed, rank++));
        }

        return new SeasonRankingsResult(seasonId, rankings.AsReadOnly());
    }

    public static ScoringConfig GetDefaultScoringConfig() => ScoringPresets.Football;

    private static StandingsMatchInput ConvertToMatchInput(Match match)
    {
        var scoreA = match.ScoreA ?? 0;
        var scoreB = match.ScoreB ?? 0;

        if (match.IsByeMatch)
        {
            return new StandingsMatchInput(
                match.ParticipantAId ?? Guid.Empty,
                Guid.Empty,
                scoreA,
                scoreB,
                match.WinnerId,
                IsBye: true);
        }

        return new StandingsMatchInput(
            match.ParticipantAId ?? Guid.Empty,
            match.ParticipantBId ?? Guid.Empty,
            scoreA,
            scoreB,
            match.WinnerId);
    }
}