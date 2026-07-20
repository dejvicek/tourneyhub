using TourneyHub.Domain.Competition;
using Xunit;

namespace TourneyHub.Domain.Tests;

public class ScoringSystemEntityTests
{
    [Fact]
    public void New_scoring_system_sets_name_and_config()
    {
        var config = ScoringPresets.Football;
        var system = new ScoringSystem("My Scoring", config);

        Assert.Equal("My Scoring", system.Name);
        Assert.Same(config, system.Config);
    }

    [Fact]
    public void New_scoring_system_throws_on_null_config()
    {
        Assert.Throws<ArgumentNullException>(() => new ScoringSystem("My Scoring", null!));
    }

    [Fact]
    public void Update_changes_name_and_config()
    {
        var system = new ScoringSystem("Original", ScoringPresets.Football);

        var newConfig = ScoringPresets.Chess;
        system.Update("Updated", newConfig);

        Assert.Equal("Updated", system.Name);
        Assert.Same(newConfig, system.Config);
    }

    [Fact]
    public void Scoring_presets_are_distinct()
    {
        var football = ScoringPresets.Football;
        var chess = ScoringPresets.Chess;
        var winOnly = ScoringPresets.WinOnly;

        Assert.NotEqual(football.WinPoints, chess.WinPoints);
        Assert.False(winOnly.AllowDraws);
        Assert.Equal(TieBreaker.PointsScored, football.TieBreakers[1]);
    }

    [Fact]
    public void Entity_extends_tenant_entity()
    {
        var system = new ScoringSystem("Test", ScoringPresets.Football);

        Assert.NotEqual(Guid.Empty, system.Id);
        Assert.Equal(0, system.Version);
    }
}
