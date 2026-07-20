using TourneyHub.Domain.Common;

namespace TourneyHub.Domain.Competition;

public class ScoringSystem : TenantEntity
{
    public string Name { get; private set; }

    public ScoringConfig Config { get; private set; }

    private ScoringSystem()
    {
        Name = string.Empty;
        Config = new ScoringConfig();
    }

    public ScoringSystem(string name, ScoringConfig config)
    {
        ArgumentNullException.ThrowIfNull(config);
        Name = name;
        Config = config;
    }

    public void Update(string name, ScoringConfig config)
    {
        Name = name;
        Config = config;
    }
}
