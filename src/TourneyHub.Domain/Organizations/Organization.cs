using TourneyHub.Domain.Common;

namespace TourneyHub.Domain.Organizations;

/// <summary>
/// The tenant root (PRD §9). Present in every deployment; hosted holds many, self-host
/// seeds one. An Organization is NOT itself tenant-scoped — it defines the boundary that
/// tenant-scoped entities (<see cref="TenantEntity"/>) belong to.
/// </summary>
public class Organization : Entity
{
    public string Name { get; private set; }

    public string Slug { get; private set; }

    public OrganizationState State { get; private set; }

    public string Plan { get; private set; }

    private Organization()
    {
        Name = string.Empty;
        Slug = string.Empty;
        Plan = string.Empty;
    }

    public Organization(string name, string slug)
    {
        Name = name;
        Slug = slug;
        State = OrganizationState.Active;
        Plan = string.Empty;
    }

    public void SetPlan(string plan)
    {
        Plan = plan;
    }

    public void Suspend()
    {
        State = OrganizationState.Suspended;
    }

    public void Reactivate()
    {
        State = OrganizationState.Active;
    }
}

public enum OrganizationState
{
    Active,
    Suspended,
    Archived,
    Deleted,
}
