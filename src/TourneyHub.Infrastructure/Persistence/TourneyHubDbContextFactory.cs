using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;
using TourneyHub.Application.Tenancy;

namespace TourneyHub.Infrastructure.Persistence;

/// <summary>
/// Design-time factory so <c>dotnet ef migrations</c> can construct the context without the
/// application host / DI. Uses a placeholder connection string (migration generation does not
/// connect) and a design-time tenant that resolves to no organization.
/// </summary>
public sealed class TourneyHubDbContextFactory : IDesignTimeDbContextFactory<TourneyHubDbContext>
{
    public TourneyHubDbContext CreateDbContext(string[] args)
    {
        var options = new DbContextOptionsBuilder<TourneyHubDbContext>()
            .UseNpgsql("Host=localhost;Port=5432;Database=tourneyhub_design;Username=postgres;Password=postgres")
            .Options;

        return new TourneyHubDbContext(options, new DesignTimeTenantContext());
    }

    private sealed class DesignTimeTenantContext : ITenantContext
    {
        public Guid OrganizationId => Guid.Empty;

        public bool HasTenant => false;
    }
}
