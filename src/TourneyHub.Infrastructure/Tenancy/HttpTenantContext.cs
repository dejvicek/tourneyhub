using TourneyHub.Application.Tenancy;

namespace TourneyHub.Infrastructure.Tenancy;

/// <summary>
/// Scoped <see cref="ITenantContext"/> implementation populated per-request by
/// <c>TenantResolutionMiddleware</c>. The middleware resolves the active organization
/// from the authenticated principal's membership claims (or <c>X-Organization-Id</c>
/// header for stub/test auth) and calls <see cref="SetTenant"/>.
/// When no tenant is resolved, <see cref="HasTenant"/> is <c>false</c> and accessing
/// <see cref="OrganizationId"/> throws — fail-closed (NFR-004, FR-154).
/// </summary>
public sealed class HttpTenantContext : ITenantContext
{
    private Guid? _organizationId;

    public Guid OrganizationId =>
        _organizationId ?? throw new InvalidOperationException(
            "No tenant resolved for the current scope. Tenant-scoped operations require " +
            "an authenticated user with an active organization membership (NFR-004, FR-154).");

    public bool HasTenant => _organizationId.HasValue;

    public void SetTenant(Guid organizationId)
    {
        _organizationId = organizationId;
    }

    public void ClearTenant()
    {
        _organizationId = null;
    }
}
