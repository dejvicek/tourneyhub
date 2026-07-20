using TourneyHub.Domain.Competition;
using Xunit;

namespace TourneyHub.Domain.Tests;

public class SeasonStateMachineTests
{
    [Fact]
    public void New_season_is_upcoming()
    {
        var season = new Season(Guid.NewGuid(), "Season 1");

        Assert.Equal(SeasonState.Upcoming, season.State);
    }

    [Fact]
    public void New_season_sets_properties()
    {
        var leagueId = Guid.NewGuid();
        var startsAt = DateTime.UtcNow.AddDays(7);
        var endsAt = DateTime.UtcNow.AddMonths(3);

        var season = new Season(leagueId, "Season 1", startsAt, endsAt);

        Assert.Equal(leagueId, season.LeagueId);
        Assert.Equal("Season 1", season.Name);
        Assert.Equal(startsAt, season.StartedAt);
        Assert.Equal(endsAt, season.CompletedAt);
        Assert.Null(season.RngSeed);
    }

    [Fact]
    public void Upcoming_season_can_be_activated()
    {
        var season = new Season(Guid.NewGuid(), "Season 1");

        season.Activate();

        Assert.Equal(SeasonState.Active, season.State);
    }

    [Fact]
    public void Active_season_cannot_be_activated_again()
    {
        var season = new Season(Guid.NewGuid(), "Season 1");
        season.Activate();

        var ex = Assert.Throws<SeasonOperationException>(() => season.Activate());
        Assert.Equal("season_not_upcoming", ex.Code);
    }

    [Fact]
    public void Closed_season_cannot_be_activated()
    {
        var season = new Season(Guid.NewGuid(), "Season 1");
        season.Activate();
        season.Close();

        var ex = Assert.Throws<SeasonOperationException>(() => season.Activate());
        Assert.Equal("season_not_upcoming", ex.Code);
    }

    [Fact]
    public void Cancelled_season_cannot_be_activated()
    {
        var season = new Season(Guid.NewGuid(), "Season 1");
        season.Cancel();

        var ex = Assert.Throws<SeasonOperationException>(() => season.Activate());
        Assert.Equal("season_not_upcoming", ex.Code);
    }

    [Fact]
    public void Active_season_can_be_closed()
    {
        var season = new Season(Guid.NewGuid(), "Season 1");
        season.Activate();

        season.Close();

        Assert.Equal(SeasonState.Closed, season.State);
        Assert.NotNull(season.CompletedAt);
    }

    [Fact]
    public void Closing_sets_completed_at()
    {
        var before = DateTime.UtcNow;
        var season = new Season(Guid.NewGuid(), "Season 1");
        season.Activate();

        season.Close();

        Assert.True(season.CompletedAt >= before);
        Assert.True(season.CompletedAt <= DateTime.UtcNow);
    }

    [Fact]
    public void Upcoming_season_cannot_be_closed()
    {
        var season = new Season(Guid.NewGuid(), "Season 1");

        var ex = Assert.Throws<SeasonOperationException>(() => season.Close());
        Assert.Equal("season_not_active", ex.Code);
    }

    [Fact]
    public void Closed_season_cannot_be_closed_again()
    {
        var season = new Season(Guid.NewGuid(), "Season 1");
        season.Activate();
        season.Close();

        var ex = Assert.Throws<SeasonOperationException>(() => season.Close());
        Assert.Equal("season_not_active", ex.Code);
    }

    [Fact]
    public void Upcoming_season_can_be_cancelled()
    {
        var season = new Season(Guid.NewGuid(), "Season 1");

        season.Cancel();

        Assert.Equal(SeasonState.Cancelled, season.State);
    }

    [Fact]
    public void Active_season_can_be_cancelled()
    {
        var season = new Season(Guid.NewGuid(), "Season 1");
        season.Activate();

        season.Cancel();

        Assert.Equal(SeasonState.Cancelled, season.State);
    }

    [Fact]
    public void Closed_season_cannot_be_cancelled()
    {
        var season = new Season(Guid.NewGuid(), "Season 1");
        season.Activate();
        season.Close();

        var ex = Assert.Throws<SeasonOperationException>(() => season.Cancel());
        Assert.Equal("season_already_closed", ex.Code);
    }

    [Fact]
    public void Cancelled_season_cannot_be_cancelled_again()
    {
        var season = new Season(Guid.NewGuid(), "Season 1");
        season.Cancel();

        var ex = Assert.Throws<SeasonOperationException>(() => season.Cancel());
        Assert.Equal("season_already_cancelled", ex.Code);
    }

    [Fact]
    public void Upcoming_and_active_seasons_are_mutable()
    {
        var upcoming = new Season(Guid.NewGuid(), "Season 1");
        Assert.True(upcoming.IsMutable());

        upcoming.Activate();
        Assert.True(upcoming.IsMutable());
    }

    [Fact]
    public void Closed_and_cancelled_seasons_are_immutable()
    {
        var season = new Season(Guid.NewGuid(), "Season 1");
        season.Activate();
        season.Close();
        Assert.False(season.IsMutable());

        var season2 = new Season(Guid.NewGuid(), "Season 2");
        season2.Cancel();
        Assert.False(season2.IsMutable());
    }

    [Fact]
    public void Activation_sets_started_at_if_not_set()
    {
        var season = new Season(Guid.NewGuid(), "Season 1");
        Assert.Null(season.StartedAt);

        season.Activate();

        Assert.NotNull(season.StartedAt);
    }

    [Fact]
    public void Activation_preserves_existing_started_at()
    {
        var startsAt = new DateTime(2026, 1, 1, 0, 0, 0, DateTimeKind.Utc);
        var season = new Season(Guid.NewGuid(), "Season 1", startsAt, null);

        season.Activate();

        Assert.Equal(startsAt, season.StartedAt);
    }

    [Fact]
    public void Season_state_values_are_correct()
    {
        var values = Enum.GetValues<SeasonState>();
        Assert.Equal(4, values.Length);
        Assert.Contains(SeasonState.Upcoming, values);
        Assert.Contains(SeasonState.Active, values);
        Assert.Contains(SeasonState.Closed, values);
        Assert.Contains(SeasonState.Cancelled, values);
    }
}
