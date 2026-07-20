using TourneyHub.Domain.Common;
using TourneyHub.Domain.Identity.Events;

namespace TourneyHub.Domain.Identity;

public class Invitation : Entity
{
    public Guid OrganizationId { get; private set; }

    public string Email { get; private set; } = string.Empty;

    public InvitationScopeType ScopeType { get; private set; }

    public Guid ScopeId { get; private set; }

    public InvitedRole Role { get; private set; }

    public InvitationState State { get; private set; }

    public Guid InvitedByUserId { get; private set; }

    public DateTime ExpiresAt { get; private set; }

    private Invitation()
    {
    }

    public Invitation(
        Guid organizationId,
        string email,
        InvitationScopeType scopeType,
        Guid scopeId,
        InvitedRole role,
        Guid invitedByUserId)
    {
        OrganizationId = organizationId;
        Email = (email ?? throw new ArgumentNullException(nameof(email))).ToLowerInvariant();
        ScopeType = scopeType;
        ScopeId = scopeId;
        Role = role;
        State = InvitationState.Pending;
        InvitedByUserId = invitedByUserId;
        ExpiresAt = DateTime.UtcNow.AddDays(14);

        RaiseDomainEvent(new InvitationCreatedEvent(Id, OrganizationId, Email, scopeType, scopeId, role));
    }

    public void Accept()
    {
        EnsurePending();
        State = InvitationState.Accepted;
    }

    public void Decline()
    {
        EnsurePending();
        State = InvitationState.Declined;
    }

    public void Revoke()
    {
        if (State is InvitationState.Accepted or InvitationState.Declined or InvitationState.Expired)
        {
            throw new InvitationOperationException("invitation_cannot_revoke", "Only pending invitations can be revoked.");
        }

        State = InvitationState.Revoked;
    }

    public bool TryExpire()
    {
        if (State != InvitationState.Pending) return false;
        if (DateTime.UtcNow <= ExpiresAt) return false;

        State = InvitationState.Expired;
        return true;
    }

    public bool IsExpired() => DateTime.UtcNow > ExpiresAt;

    private void EnsurePending()
    {
        if (State != InvitationState.Pending)
        {
            throw new InvitationOperationException(
                "invitation_not_pending",
                $"Invitation is {State.ToString().ToLowerInvariant()} and cannot be modified.");
        }

        if (IsExpired())
        {
            State = InvitationState.Expired;
            throw new InvitationOperationException(
                "invitation_expired",
                "Invitation has expired and cannot be accepted or declined.");
        }
    }
}

public enum InvitationState
{
    Pending,
    Accepted,
    Declined,
    Revoked,
    Expired,
}

public enum InvitationScopeType
{
    League,
    Organization,
}

public enum InvitedRole
{
    Organizer,
    Player,
}

public class InvitationOperationException : Exception
{
    public string Code { get; }

    public InvitationOperationException(string code, string message) : base(message)
    {
        Code = code;
    }
}
