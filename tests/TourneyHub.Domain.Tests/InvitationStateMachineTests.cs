using TourneyHub.Domain.Identity;
using Xunit;

namespace TourneyHub.Domain.Tests;

public class InvitationStateMachineTests
{
    [Fact]
    public void New_invitation_is_pending()
    {
        var invitation = new Invitation(
            Guid.NewGuid(), "test@example.com", InvitationScopeType.League,
            Guid.NewGuid(), InvitedRole.Player, Guid.NewGuid());

        Assert.Equal(InvitationState.Pending, invitation.State);
    }

    [Fact]
    public void New_invitation_has_14_day_expiry()
    {
        var before = DateTime.UtcNow.AddDays(13);
        var invitation = new Invitation(
            Guid.NewGuid(), "test@example.com", InvitationScopeType.League,
            Guid.NewGuid(), InvitedRole.Player, Guid.NewGuid());

        Assert.True(invitation.ExpiresAt > before);
        Assert.True(invitation.ExpiresAt <= DateTime.UtcNow.AddDays(14).AddMinutes(1));
    }

    [Fact]
    public void New_invitation_normalizes_email_to_lowercase()
    {
        var invitation = new Invitation(
            Guid.NewGuid(), "Test@Example.COM", InvitationScopeType.League,
            Guid.NewGuid(), InvitedRole.Player, Guid.NewGuid());

        Assert.Equal("test@example.com", invitation.Email);
    }

    [Fact]
    public void New_invitation_raises_created_event()
    {
        var invitation = new Invitation(
            Guid.NewGuid(), "test@example.com", InvitationScopeType.League,
            Guid.NewGuid(), InvitedRole.Player, Guid.NewGuid());

        Assert.Single(invitation.DomainEvents);
    }

    [Fact]
    public void Pending_invitation_can_be_accepted()
    {
        var invitation = new Invitation(
            Guid.NewGuid(), "test@example.com", InvitationScopeType.League,
            Guid.NewGuid(), InvitedRole.Player, Guid.NewGuid());

        invitation.Accept();

        Assert.Equal(InvitationState.Accepted, invitation.State);
    }

    [Fact]
    public void Pending_invitation_can_be_declined()
    {
        var invitation = new Invitation(
            Guid.NewGuid(), "test@example.com", InvitationScopeType.League,
            Guid.NewGuid(), InvitedRole.Player, Guid.NewGuid());

        invitation.Decline();

        Assert.Equal(InvitationState.Declined, invitation.State);
    }

    [Fact]
    public void Pending_invitation_can_be_revoked()
    {
        var invitation = new Invitation(
            Guid.NewGuid(), "test@example.com", InvitationScopeType.League,
            Guid.NewGuid(), InvitedRole.Player, Guid.NewGuid());

        invitation.Revoke();

        Assert.Equal(InvitationState.Revoked, invitation.State);
    }

    [Fact]
    public void Accepted_invitation_cannot_be_accepted_again()
    {
        var invitation = new Invitation(
            Guid.NewGuid(), "test@example.com", InvitationScopeType.League,
            Guid.NewGuid(), InvitedRole.Player, Guid.NewGuid());
        invitation.Accept();

        var ex = Assert.Throws<InvitationOperationException>(() => invitation.Accept());
        Assert.Equal("invitation_not_pending", ex.Code);
    }

    [Fact]
    public void Accepted_invitation_cannot_be_declined()
    {
        var invitation = new Invitation(
            Guid.NewGuid(), "test@example.com", InvitationScopeType.League,
            Guid.NewGuid(), InvitedRole.Player, Guid.NewGuid());
        invitation.Accept();

        var ex = Assert.Throws<InvitationOperationException>(() => invitation.Decline());
        Assert.Equal("invitation_not_pending", ex.Code);
    }

    [Fact]
    public void Accepted_invitation_cannot_be_revoked()
    {
        var invitation = new Invitation(
            Guid.NewGuid(), "test@example.com", InvitationScopeType.League,
            Guid.NewGuid(), InvitedRole.Player, Guid.NewGuid());
        invitation.Accept();

        var ex = Assert.Throws<InvitationOperationException>(() => invitation.Revoke());
        Assert.Equal("invitation_cannot_revoke", ex.Code);
    }

    [Fact]
    public void Declined_invitation_cannot_be_accepted()
    {
        var invitation = new Invitation(
            Guid.NewGuid(), "test@example.com", InvitationScopeType.League,
            Guid.NewGuid(), InvitedRole.Player, Guid.NewGuid());
        invitation.Decline();

        var ex = Assert.Throws<InvitationOperationException>(() => invitation.Accept());
        Assert.Equal("invitation_not_pending", ex.Code);
    }

    [Fact]
    public void Declined_invitation_cannot_be_revoked()
    {
        var invitation = new Invitation(
            Guid.NewGuid(), "test@example.com", InvitationScopeType.League,
            Guid.NewGuid(), InvitedRole.Player, Guid.NewGuid());
        invitation.Decline();

        var ex = Assert.Throws<InvitationOperationException>(() => invitation.Revoke());
        Assert.Equal("invitation_cannot_revoke", ex.Code);
    }

    [Fact]
    public void Revoked_invitation_cannot_be_accepted()
    {
        var invitation = new Invitation(
            Guid.NewGuid(), "test@example.com", InvitationScopeType.League,
            Guid.NewGuid(), InvitedRole.Player, Guid.NewGuid());
        invitation.Revoke();

        var ex = Assert.Throws<InvitationOperationException>(() => invitation.Accept());
        Assert.Equal("invitation_not_pending", ex.Code);
    }

    [Fact]
    public void Expired_invitation_cannot_be_accepted()
    {
        var invitation = new Invitation(
            Guid.NewGuid(), "test@example.com", InvitationScopeType.League,
            Guid.NewGuid(), InvitedRole.Player, Guid.NewGuid());
        invitation.TryExpire();

        Assert.Equal(InvitationState.Pending, invitation.State);
    }

    [Fact]
    public void TryExpire_transitions_when_expired()
    {
        var invitation = CreateExpiredInvitation();

        Assert.True(invitation.TryExpire());
        Assert.Equal(InvitationState.Expired, invitation.State);
    }

    [Fact]
    public void TryExpire_does_not_transition_accepted()
    {
        var invitation = CreateExpiredInvitation();
        typeof(Invitation).GetProperty(nameof(Invitation.State))!
            .SetValue(invitation, InvitationState.Accepted);

        Assert.False(invitation.TryExpire());
        Assert.Equal(InvitationState.Accepted, invitation.State);
    }

    [Fact]
    public void EnsurePending_throws_for_expired()
    {
        var invitation = CreateExpiredInvitation();

        var ex = Assert.Throws<InvitationOperationException>(() => invitation.Accept());
        Assert.Equal("invitation_expired", ex.Code);
        Assert.Equal(InvitationState.Expired, invitation.State);
    }

    [Fact]
    public void IsExpired_returns_false_within_ttl()
    {
        var invitation = new Invitation(
            Guid.NewGuid(), "test@example.com", InvitationScopeType.League,
            Guid.NewGuid(), InvitedRole.Player, Guid.NewGuid());

        Assert.False(invitation.IsExpired());
    }

    [Fact]
    public void IsExpired_returns_true_after_ttl()
    {
        var invitation = CreateExpiredInvitation();

        Assert.True(invitation.IsExpired());
    }

    [Fact]
    public void Expired_invitation_cannot_be_revoked()
    {
        var invitation = CreateExpiredInvitation();
        invitation.TryExpire();

        var ex = Assert.Throws<InvitationOperationException>(() => invitation.Revoke());
        Assert.Equal("invitation_cannot_revoke", ex.Code);
    }

    [Fact]
    public void Invitation_has_all_expected_states()
    {
        var states = Enum.GetValues<InvitationState>();
        Assert.Equal(5, states.Length);
        Assert.Contains(InvitationState.Pending, states);
        Assert.Contains(InvitationState.Accepted, states);
        Assert.Contains(InvitationState.Declined, states);
        Assert.Contains(InvitationState.Revoked, states);
        Assert.Contains(InvitationState.Expired, states);
    }

    private static Invitation CreateExpiredInvitation()
    {
        var invitation = new Invitation(
            Guid.NewGuid(), "test@example.com", InvitationScopeType.League,
            Guid.NewGuid(), InvitedRole.Player, Guid.NewGuid());

        typeof(Invitation).GetProperty(nameof(Invitation.ExpiresAt))!
            .SetValue(invitation, DateTime.UtcNow.AddDays(-1));

        return invitation;
    }
}
