using Microsoft.EntityFrameworkCore;

namespace TourneyHub.Infrastructure.Persistence;

/// <summary>
/// EF Core context. Per-slice DbSets are added as entities are implemented.
///
/// TENANCY GUARDRAIL (NFR-004, FR-151/152): every tenant-scoped entity carries a
/// non-null organization_id, and a GLOBAL QUERY FILTER on the resolved organization
/// MUST be applied in <see cref="OnModelCreating"/> so no query can span tenants.
/// The active organization is resolved server-side (never from client input).
/// </summary>
public class TourneyHubDbContext(DbContextOptions<TourneyHubDbContext> options) : DbContext(options)
{
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        // TODO(tenancy): apply a global query filter keyed on the resolved organization_id
        // to every tenant-scoped entity (NFR-024). Covered by an isolation test in CI.
    }
}
