using TourneyHub.Domain.Common;

namespace TourneyHub.Domain.Organizations;

public class Membership : Entity
{
    public Guid UserId { get; private set; }

    public Guid OrganizationId { get; private set; }

    public MembershipRole Role { get; private set; }

    public MembershipState State { get; private set; }

    public DateTime JoinedAt { get; private set; }

    private Membership()
    {
    }

    public Membership(Guid userId, Guid organizationId, MembershipRole role)
    {
        UserId = userId;
        OrganizationId = organizationId;
        Role = role;
        State = MembershipState.Active;
        JoinedAt = DateTime.UtcNow;
    }

    public void ChangeRole(MembershipRole newRole)
    {
        Role = newRole;
    }

    public void Suspend()
    {
        State = MembershipState.Suspended;
    }

    public void Reactivate()
    {
        State = MembershipState.Active;
    }
}

public enum MembershipRole
{
    OrgOwner,
    Organizer,
    Player,
}

public enum MembershipState
{
    Active,
    Suspended,
}
