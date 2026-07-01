namespace TourneyHub.Domain.Common;

/// <summary>
/// Base for tenant-scoped entities. Carries a non-null <see cref="OrganizationId"/>
/// (NFR-004, FR-151). The value is assigned SERVER-SIDE by the persistence layer from
/// the resolved tenant context — never from client input. Reading or writing another
/// organization's row is a P0 defect (FR-152, NFR-024), enforced by a global query
/// filter and a SaveChanges guard.
/// </summary>
public abstract class TenantEntity : Entity
{
    /// <summary>Owning organization (tenant). Set by the persistence layer, not the caller.</summary>
    public Guid OrganizationId { get; private set; }
}
