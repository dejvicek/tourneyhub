using Microsoft.EntityFrameworkCore;
using TourneyHub.Application.Tenancy;
using TourneyHub.Domain.Common;
using TourneyHub.Domain.Competition;
using TourneyHub.Domain.Organizations;

namespace TourneyHub.Infrastructure.Persistence;

/// <summary>
/// EF Core context. TENANCY GUARDRAIL (NFR-004, NFR-024, FR-151/152):
///   - every <see cref="TenantEntity"/> has a non-null organization_id;
///   - a GLOBAL QUERY FILTER binds every read to the resolved organization, so no query
///     can return another tenant's rows;
///   - <see cref="SaveChanges()"/> stamps the tenant on inserts and REJECTS writes to a
///     row owned by a different organization.
/// The active organization is resolved server-side via <see cref="ITenantContext"/>,
/// never from client input.
/// </summary>
public class TourneyHubDbContext : DbContext
{
    private readonly ITenantContext _tenant;

    public TourneyHubDbContext(DbContextOptions<TourneyHubDbContext> options, ITenantContext tenant)
        : base(options)
    {
        _tenant = tenant;
    }

    public DbSet<Organization> Organizations => Set<Organization>();

    public DbSet<League> Leagues => Set<League>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        modelBuilder.Entity<Organization>(b =>
        {
            b.ToTable("organizations");
            b.HasKey(e => e.Id);
            b.Property(e => e.Name).IsRequired();
            b.Property(e => e.Slug).IsRequired();
            b.Property(e => e.State).HasConversion<string>().IsRequired();
            b.HasIndex(e => e.Slug).IsUnique();
        });

        modelBuilder.Entity<League>(b =>
        {
            b.ToTable("leagues");
            b.HasKey(e => e.Id);
            b.Property(e => e.OrganizationId).IsRequired();
            b.Property(e => e.Name).IsRequired();
            // Composite tenant index for scoped lookups (§18).
            b.HasIndex(e => new { e.OrganizationId, e.Id });
            // Tenant isolation: no read can escape the current organization.
            b.HasQueryFilter(e => e.OrganizationId == _tenant.OrganizationId);
        });
    }

    public override int SaveChanges()
    {
        StampAndGuardTenant();
        return base.SaveChanges();
    }

    public override int SaveChanges(bool acceptAllChangesOnSuccess)
    {
        StampAndGuardTenant();
        return base.SaveChanges(acceptAllChangesOnSuccess);
    }

    public override Task<int> SaveChangesAsync(CancellationToken cancellationToken = default)
    {
        StampAndGuardTenant();
        return base.SaveChangesAsync(cancellationToken);
    }

    public override Task<int> SaveChangesAsync(bool acceptAllChangesOnSuccess, CancellationToken cancellationToken = default)
    {
        StampAndGuardTenant();
        return base.SaveChangesAsync(acceptAllChangesOnSuccess, cancellationToken);
    }

    /// <summary>
    /// Inserts: stamp the current organization. Updates/deletes: reject if the row belongs
    /// to a different organization. This is the write-side half of tenant isolation (FR-152).
    /// </summary>
    private void StampAndGuardTenant()
    {
        foreach (var entry in ChangeTracker.Entries<TenantEntity>())
        {
            var property = entry.Property(nameof(TenantEntity.OrganizationId));

            switch (entry.State)
            {
                case EntityState.Added:
                    property.CurrentValue = _tenant.OrganizationId;
                    break;

                case EntityState.Modified:
                case EntityState.Deleted:
                    var owner = (Guid)property.CurrentValue!;
                    if (owner != _tenant.OrganizationId)
                    {
                        throw new InvalidOperationException(
                            "Cross-tenant write blocked: the entity belongs to a different organization (FR-152, NFR-024).");
                    }

                    break;

                default:
                    break;
            }
        }
    }
}
