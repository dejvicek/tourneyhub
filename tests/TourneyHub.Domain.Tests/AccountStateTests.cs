using TourneyHub.Domain.Identity;
using Xunit;

namespace TourneyHub.Domain.Tests;

public class AccountStateTests
{
    [Fact]
    public void New_user_defaults_to_pending_verification()
    {
        var user = new User();

        Assert.Equal(AccountState.PendingVerification, user.State);
    }

    [Fact]
    public void State_transitions_through_enum_values()
    {
        var states = Enum.GetValues<AccountState>();

        Assert.Equal(4, states.Length);
        Assert.Contains(AccountState.PendingVerification, states);
        Assert.Contains(AccountState.Active, states);
        Assert.Contains(AccountState.Suspended, states);
        Assert.Contains(AccountState.Banned, states);
    }

    [Fact]
    public void Pending_verification_can_transition_to_active()
    {
        var user = new User { State = AccountState.PendingVerification };

        user.State = AccountState.Active;

        Assert.Equal(AccountState.Active, user.State);
    }

    [Fact]
    public void Active_can_transition_to_suspended()
    {
        var user = new User { State = AccountState.Active };

        user.State = AccountState.Suspended;

        Assert.Equal(AccountState.Suspended, user.State);
    }

    [Fact]
    public void Active_can_transition_to_banned()
    {
        var user = new User { State = AccountState.Active };

        user.State = AccountState.Banned;

        Assert.Equal(AccountState.Banned, user.State);
    }

    [Fact]
    public void Suspended_or_banned_accounts_should_block_access()
    {
        Assert.True(IsBlocked(AccountState.Suspended));
        Assert.True(IsBlocked(AccountState.Banned));
        Assert.False(IsBlocked(AccountState.Active));
        Assert.False(IsBlocked(AccountState.PendingVerification));
    }

    private static bool IsBlocked(AccountState state) =>
        state is AccountState.Suspended or AccountState.Banned;
}