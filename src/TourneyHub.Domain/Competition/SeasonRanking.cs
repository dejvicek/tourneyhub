namespace TourneyHub.Domain.Competition;

public class SeasonRanking : TourneyHub.Domain.Common.TenantEntity
{
    public Guid SeasonId { get; private set; }
    public Guid UserId { get; private set; }
    public int Points { get; private set; }
    public int MatchesPlayed { get; private set; }
    public int Rank { get; private set; }

    private SeasonRanking()
    {
    }

    public SeasonRanking(
        Guid seasonId,
        Guid userId,
        int points,
        int matchesPlayed,
        int rank)
    {
        SeasonId = seasonId;
        UserId = userId;
        Points = points;
        MatchesPlayed = matchesPlayed;
        Rank = rank;
    }

    public void UpdateFromEntry(int points, int matchesPlayed, int rank)
    {
        Points = points;
        MatchesPlayed = matchesPlayed;
        Rank = rank;
    }
}