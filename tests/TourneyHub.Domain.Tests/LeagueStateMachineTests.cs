using TourneyHub.Domain.Competition;
using Xunit;

namespace TourneyHub.Domain.Tests;

public class LeagueStateMachineTests
{
    [Fact]
    public void New_league_is_active()
    {
        var league = new League("Test League", "test-league", LeagueVisibility.Public, Guid.NewGuid());

        Assert.Equal(LeagueState.Active, league.State);
    }

    [Fact]
    public void New_league_sets_all_properties()
    {
        var ownerId = Guid.NewGuid();
        var league = new League("Test League", "test-league", LeagueVisibility.Public, ownerId, "A test league");

        Assert.Equal("Test League", league.Name);
        Assert.Equal("test-league", league.Slug);
        Assert.Equal(LeagueVisibility.Public, league.Visibility);
        Assert.Equal(ownerId, league.OwnerId);
        Assert.Equal("A test league", league.Description);
    }

    [Fact]
    public void Active_league_can_be_archived()
    {
        var league = new League("Test League", "test-league", LeagueVisibility.Public, Guid.NewGuid());

        league.Archive();

        Assert.Equal(LeagueState.Archived, league.State);
    }

    [Fact]
    public void Archived_league_can_be_unarchived()
    {
        var league = new League("Test League", "test-league", LeagueVisibility.Public, Guid.NewGuid());
        league.Archive();

        league.Unarchive();

        Assert.Equal(LeagueState.Active, league.State);
    }

    [Fact]
    public void Archived_league_cannot_be_archived_again()
    {
        var league = new League("Test League", "test-league", LeagueVisibility.Public, Guid.NewGuid());
        league.Archive();

        var ex = Assert.Throws<LeagueOperationException>(() => league.Archive());
        Assert.Equal("league_already_archived", ex.Code);
    }

    [Fact]
    public void Active_league_cannot_be_unarchived()
    {
        var league = new League("Test League", "test-league", LeagueVisibility.Public, Guid.NewGuid());

        var ex = Assert.Throws<LeagueOperationException>(() => league.Unarchive());
        Assert.Equal("league_not_archived", ex.Code);
    }

    [Fact]
    public void Active_league_can_be_deleted()
    {
        var league = new League("Test League", "test-league", LeagueVisibility.Public, Guid.NewGuid());

        league.Delete();

        Assert.Equal(LeagueState.Deleted, league.State);
    }

    [Fact]
    public void Archived_league_can_be_deleted()
    {
        var league = new League("Test League", "test-league", LeagueVisibility.Public, Guid.NewGuid());
        league.Archive();

        league.Delete();

        Assert.Equal(LeagueState.Deleted, league.State);
    }

    [Fact]
    public void Deleted_league_cannot_be_archived()
    {
        var league = new League("Test League", "test-league", LeagueVisibility.Public, Guid.NewGuid());
        league.Delete();

        var ex = Assert.Throws<LeagueOperationException>(() => league.Archive());
        Assert.Equal("league_deleted", ex.Code);
    }

    [Fact]
    public void Deleted_league_cannot_be_deleted_again()
    {
        var league = new League("Test League", "test-league", LeagueVisibility.Public, Guid.NewGuid());
        league.Delete();

        var ex = Assert.Throws<LeagueOperationException>(() => league.Delete());
        Assert.Equal("league_already_deleted", ex.Code);
    }

    [Fact]
    public void Active_league_can_update_fields()
    {
        var league = new League("Test League", "test-league", LeagueVisibility.Public, Guid.NewGuid());

        league.Update("Updated League", LeagueVisibility.Private, "Updated desc");

        Assert.Equal("Updated League", league.Name);
        Assert.Equal(LeagueVisibility.Private, league.Visibility);
        Assert.Equal("Updated desc", league.Description);
    }

    [Fact]
    public void Archived_league_can_update_fields()
    {
        var league = new League("Test League", "test-league", LeagueVisibility.Public, Guid.NewGuid());
        league.Archive();

        league.Update("Updated League", LeagueVisibility.Private, "Updated desc");

        Assert.Equal("Updated League", league.Name);
        Assert.Equal(LeagueVisibility.Private, league.Visibility);
        Assert.Equal("Updated desc", league.Description);
    }

    [Fact]
    public void Deleted_league_cannot_update_fields()
    {
        var league = new League("Test League", "test-league", LeagueVisibility.Public, Guid.NewGuid());
        league.Delete();

        var ex = Assert.Throws<LeagueOperationException>(
            () => league.Update("Updated", LeagueVisibility.Private, "desc"));
        Assert.Equal("league_deleted", ex.Code);
    }

    [Fact]
    public void Ownership_can_be_transferred()
    {
        var league = new League("Test League", "test-league", LeagueVisibility.Public, Guid.NewGuid());
        var newOwner = Guid.NewGuid();

        league.TransferOwnership(newOwner);

        Assert.Equal(newOwner, league.OwnerId);
    }

    [Fact]
    public void Deleted_league_cannot_transfer_ownership()
    {
        var league = new League("Test League", "test-league", LeagueVisibility.Public, Guid.NewGuid());
        league.Delete();

        var ex = Assert.Throws<LeagueOperationException>(
            () => league.TransferOwnership(Guid.NewGuid()));
        Assert.Equal("league_deleted", ex.Code);
    }

    [Fact]
    public void League_visibility_values_are_correct()
    {
        var values = Enum.GetValues<LeagueVisibility>();
        Assert.Equal(3, values.Length);
        Assert.Contains(LeagueVisibility.Public, values);
        Assert.Contains(LeagueVisibility.Unlisted, values);
        Assert.Contains(LeagueVisibility.Private, values);
    }

    [Fact]
    public void League_state_values_are_correct()
    {
        var values = Enum.GetValues<LeagueState>();
        Assert.Equal(3, values.Length);
        Assert.Contains(LeagueState.Active, values);
        Assert.Contains(LeagueState.Archived, values);
        Assert.Contains(LeagueState.Deleted, values);
    }
}
