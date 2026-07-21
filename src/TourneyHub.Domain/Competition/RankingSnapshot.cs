namespace TourneyHub.Domain.Competition;

public class RankingSnapshot : TourneyHub.Domain.Common.TenantEntity
{
    public Guid SeasonId { get; private set; }
    public DateTime CreatedAt { get; private set; }
    public string Data { get; private set; }

    private RankingSnapshot()
    {
        Data = string.Empty;
    }

    public RankingSnapshot(Guid seasonId, string data)
    {
        SeasonId = seasonId;
        CreatedAt = DateTime.UtcNow;
        Data = data;
    }
}