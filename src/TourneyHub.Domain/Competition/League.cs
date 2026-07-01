using TourneyHub.Domain.Common;

namespace TourneyHub.Domain.Competition;

/// <summary>
/// Minimal tenant-scoped entity used to anchor the tenancy foundation and its isolation
/// tests (FR-020, FR-151). Fields are added per the League slice; here it exists to prove
/// the scoping invariant end-to-end. <see cref="TenantEntity.OrganizationId"/> is stamped
/// server-side on save.
/// </summary>
public class League : TenantEntity
{
    public string Name { get; private set; }

    // EF materialization constructor.
    private League()
    {
        Name = string.Empty;
    }

    public League(string name)
    {
        Name = name;
    }
}
