namespace TourneyHub.Domain.Competition;

public enum TieBreaker
{
    HeadToHead,
    PointsScored,
    Wins,
    PointsDifference,
    Random,
}

public sealed record ScoringConfig
{
    public int WinPoints { get; init; } = 3;
    public int DrawPoints { get; init; } = 1;
    public int LossPoints { get; init; }
    public int ByePoints { get; init; }
    public int ParticipationPoints { get; init; }
    public bool AllowDraws { get; init; } = true;
    public IReadOnlyList<TieBreaker> TieBreakers { get; init; } = Array.Empty<TieBreaker>();

    public ScoringConfig() { }

    public ScoringConfig(
        int winPoints,
        int drawPoints,
        int lossPoints,
        int byePoints,
        int participationPoints,
        bool allowDraws,
        IReadOnlyList<TieBreaker> tieBreakers)
    {
        WinPoints = winPoints;
        DrawPoints = drawPoints;
        LossPoints = lossPoints;
        ByePoints = byePoints;
        ParticipationPoints = participationPoints;
        AllowDraws = allowDraws;
        TieBreakers = tieBreakers;
    }
}

public static class ScoringPresets
{
    public static ScoringConfig Football => new(
        winPoints: 3,
        drawPoints: 1,
        lossPoints: 0,
        byePoints: 0,
        participationPoints: 0,
        allowDraws: true,
        tieBreakers: new[] { TieBreaker.HeadToHead, TieBreaker.PointsScored, TieBreaker.Wins, TieBreaker.Random });

    public static ScoringConfig Chess => new(
        winPoints: 1,
        drawPoints: 0,
        lossPoints: 0,
        byePoints: 1,
        participationPoints: 0,
        allowDraws: true,
        tieBreakers: new[] { TieBreaker.HeadToHead, TieBreaker.Wins, TieBreaker.Random });

    public static ScoringConfig WinOnly => new(
        winPoints: 1,
        drawPoints: 0,
        lossPoints: 0,
        byePoints: 1,
        participationPoints: 0,
        allowDraws: false,
        tieBreakers: new[] { TieBreaker.HeadToHead, TieBreaker.PointsScored, TieBreaker.PointsDifference, TieBreaker.Random });
}
