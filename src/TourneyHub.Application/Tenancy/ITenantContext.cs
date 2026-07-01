namespace TourneyHub.Application.Tenancy;

/// <summary>
/// Resolves the CURRENT organization (tenant) for the unit of work — server-side, from the
/// authenticated principal / active organization membership, NEVER from client input
/// (NFR-004, FR-152, FR-154). Every tenant-scoped read is filtered by this value and every
/// tenant-scoped write is stamped with it.
/// </summary>
public interface ITenantContext
{
    /// <summary>The resolved organization id. Throws/!<see cref="HasTenant"/> when unresolved.</summary>
    Guid OrganizationId { get; }

    /// <summary>True when a tenant has been resolved for the current scope.</summary>
    bool HasTenant { get; }
}
