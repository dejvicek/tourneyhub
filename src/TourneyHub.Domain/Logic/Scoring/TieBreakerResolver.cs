using System.Security.Cryptography;
using System.Text;
using TourneyHub.Domain.Competition;

namespace TourneyHub.Domain.Logic.Scoring;

public sealed record StandingsMatchInput(
    Guid ParticipantAId,
    Guid ParticipantBId,
    int HomeScore,
    int AwayScore,
    Guid? WinnerId,
    bool IsBye = false);

public sealed class StandingsEntry
{
    public int Rank { get; set; }
    public Guid ParticipantId { get; init; }
    public int Points { get; init; }
    public int Wins { get; init; }
    public int Losses { get; init; }
    public int Draws { get; init; }
    public int PointsScored { get; init; }
    public int PointsConceded { get; init; }
    public int PointsDifference { get; init; }
    public int Byes { get; init; }
}

public static class TieBreakerResolver
{
    public static IReadOnlyList<StandingsEntry> ComputeStandings(
        IReadOnlyList<Guid> participantIds,
        IReadOnlyList<StandingsMatchInput> matches,
        ScoringConfig config,
        string rngSeed)
    {
        ArgumentNullException.ThrowIfNull(participantIds);
        ArgumentNullException.ThrowIfNull(matches);
        ArgumentNullException.ThrowIfNull(config);
        ArgumentNullException.ThrowIfNull(rngSeed);

        if (participantIds.Count == 0)
            return Array.Empty<StandingsEntry>();

        var stats = new Dictionary<Guid, (int points, int wins, int losses, int draws, int scored, int conceded, int byes)>();

        foreach (var pid in participantIds)
        {
            stats[pid] = (0, 0, 0, 0, 0, 0, 0);
        }

        foreach (var match in matches)
        {
            if (match.IsBye)
            {
                var (bp, bw, bl, bd, bs, bc, by_) = stats[match.ParticipantAId];
                stats[match.ParticipantAId] = (bp + config.ByePoints, bw, bl, bd, bs, bc, by_ + 1);
                continue;
            }

            var matchResult = new MatchResult(match.HomeScore, match.AwayScore);
            var (homePoints, awayPoints) = ScoringCalculator.CalculatePoints(matchResult, config);

            UpdateParticipantStats(ref stats, match.ParticipantAId, homePoints, match.HomeScore, match.AwayScore,
                matchResult, isHome: true);
            UpdateParticipantStats(ref stats, match.ParticipantBId, awayPoints, match.AwayScore, match.HomeScore,
                matchResult, isHome: false);
        }

        foreach (var pid in participantIds)
        {
            if (!stats.ContainsKey(pid))
            {
                stats[pid] = (0, 0, 0, 0, 0, 0, 0);
            }
        }

        var sortedIds = new List<Guid>(participantIds);
        SortByTieBreakers(sortedIds, stats, matches, config, rngSeed);

        var standings = new List<StandingsEntry>();
        int rank = 1;
        foreach (var pid in sortedIds)
        {
            var (points, wins, losses, draws, scored, conceded, byes) = stats[pid];
            standings.Add(new StandingsEntry
            {
                Rank = rank++,
                ParticipantId = pid,
                Points = points,
                Wins = wins,
                Losses = losses,
                Draws = draws,
                PointsScored = scored,
                PointsConceded = conceded,
                PointsDifference = scored - conceded,
                Byes = byes,
            });
        }

        return standings.AsReadOnly();
    }

    private static void UpdateParticipantStats(
        ref Dictionary<Guid, (int points, int wins, int losses, int draws, int scored, int conceded, int byes)> stats,
        Guid participantId,
        int earnedPoints,
        int ownScore,
        int opponentScore,
        MatchResult result,
        bool isHome)
    {
        var prev = stats[participantId];
        stats[participantId] = (
            prev.points + earnedPoints,
            prev.wins + (ownScore > opponentScore ? 1 : 0),
            prev.losses + (ownScore < opponentScore ? 1 : 0),
            prev.draws + (ownScore == opponentScore ? 1 : 0),
            prev.scored + ownScore,
            prev.conceded + opponentScore,
            prev.byes
        );
    }

    private static void SortByTieBreakers(
        List<Guid> ids,
        Dictionary<Guid, (int points, int wins, int losses, int draws, int scored, int conceded, int byes)> stats,
        IReadOnlyList<StandingsMatchInput> matches,
        ScoringConfig config,
        string rngSeed)
    {
        ids.Sort((a, b) =>
        {
            var sa = stats[a];
            var sb = stats[b];

            if (sa.points != sb.points)
                return sb.points.CompareTo(sa.points);

            if (config.TieBreakers.Count == 0)
                return 0;

            foreach (var tieBreaker in config.TieBreakers)
            {
                int comparison = ApplyTieBreaker(a, b, ids, stats, matches, tieBreaker, rngSeed);
                if (comparison != 0)
                    return comparison;
            }

            return 0;
        });
    }

    private static int ApplyTieBreaker(
        Guid a,
        Guid b,
        IReadOnlyList<Guid> allIds,
        Dictionary<Guid, (int points, int wins, int losses, int draws, int scored, int conceded, int byes)> stats,
        IReadOnlyList<StandingsMatchInput> matches,
        TieBreaker tieBreaker,
        string rngSeed)
    {
        switch (tieBreaker)
        {
            case TieBreaker.HeadToHead:
                return ResolveHeadToHead(a, b, allIds, stats, matches);

            case TieBreaker.PointsScored:
            {
                var sa = stats[a];
                var sb = stats[b];
                return sb.scored.CompareTo(sa.scored);
            }

            case TieBreaker.Wins:
            {
                var sa = stats[a];
                var sb = stats[b];
                return sb.wins.CompareTo(sa.wins);
            }

            case TieBreaker.PointsDifference:
            {
                var sa = stats[a];
                var sb = stats[b];
                int diffA = sa.scored - sa.conceded;
                int diffB = sb.scored - sb.conceded;
                return diffB.CompareTo(diffA);
            }

            case TieBreaker.Random:
                return ResolveRandom(a, b, rngSeed);

            default:
                return 0;
        }
    }

    private static int ResolveHeadToHead(
        Guid a,
        Guid b,
        IReadOnlyList<Guid> allIds,
        Dictionary<Guid, (int points, int wins, int losses, int draws, int scored, int conceded, int byes)> stats,
        IReadOnlyList<StandingsMatchInput> matches)
    {
        var tiedIds = new HashSet<Guid>();

        foreach (var id in allIds)
        {
            if (stats[id].points == stats[a].points && stats[id].points == stats[b].points)
                tiedIds.Add(id);
        }

        var headToHeadPoints = new Dictionary<Guid, int>();
        foreach (var id in tiedIds)
            headToHeadPoints[id] = 0;

        foreach (var match in matches)
        {
            if (!tiedIds.Contains(match.ParticipantAId) || !tiedIds.Contains(match.ParticipantBId))
                continue;
            if (match.IsBye)
                continue;

            var matchResult = new MatchResult(match.HomeScore, match.AwayScore);
            var h2HConfig = new ScoringConfig
            {
                WinPoints = 3, DrawPoints = 1, LossPoints = 0, ByePoints = 0,
                ParticipationPoints = 0, AllowDraws = true,
            };
            var (hp, ap) = ScoringCalculator.CalculatePoints(matchResult, h2HConfig);

            headToHeadPoints[match.ParticipantAId] += hp;
            headToHeadPoints[match.ParticipantBId] += ap;
        }

        int pa = headToHeadPoints[a];
        int pb = headToHeadPoints[b];
        if (pa != pb)
            return pb.CompareTo(pa);

        return 0;
    }

    private static int ResolveRandom(Guid a, Guid b, string rngSeed)
    {
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(rngSeed + a.ToString("N") + b.ToString("N")));
        long hashA = BitConverter.ToInt64(hash, 0);
        hash = SHA256.HashData(Encoding.UTF8.GetBytes(rngSeed + b.ToString("N") + a.ToString("N")));
        long hashB = BitConverter.ToInt64(hash, 0);

        return hashB.CompareTo(hashA);
    }
}
