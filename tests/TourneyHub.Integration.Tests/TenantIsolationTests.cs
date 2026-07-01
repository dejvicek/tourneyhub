using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using TourneyHub.Application.Tenancy;
using TourneyHub.Domain.Competition;
using TourneyHub.Domain.Organizations;
using TourneyHub.Infrastructure.Persistence;
using Xunit;

namespace TourneyHub.Integration.Tests;

/// <summary>
/// The tenant-isolation harness (FR-152, NFR-024) against a REAL relational engine
/// (SQLite in-memory — provider-agnostic, no Docker, runs everywhere incl. CI). Two
/// organizations are seeded, each with a league; every test asserts an OUTCOME, not a
/// mechanism:
///   - reads only ever return the current org's rows;
///   - fetching another org's row by id returns nothing;
///   - inserts are stamped with the current org;
///   - writes to another org's row are rejected.
/// A failure here means cross-tenant access has leaked — a P0 defect. Each test gets a
/// fresh in-memory database (xUnit constructs the class per test).
/// </summary>
public sealed class TenantIsolationTests : IAsyncLifetime
{
    private SqliteConnection _connection = null!;

    private Guid _orgA;
    private Guid _orgB;
    private Guid _leagueA;
    private Guid _leagueB;

    private sealed class FixedTenant(Guid organizationId) : ITenantContext
    {
        public Guid OrganizationId { get; } = organizationId;

        public bool HasTenant => OrganizationId != Guid.Empty;
    }

    private TourneyHubDbContext NewContext(Guid tenant)
    {
        var options = new DbContextOptionsBuilder<TourneyHubDbContext>()
            .UseSqlite(_connection)
            .Options;

        return new TourneyHubDbContext(options, new FixedTenant(tenant));
    }

    public async Task InitializeAsync()
    {
        // Keep the connection open so the in-memory database survives across contexts.
        _connection = new SqliteConnection("DataSource=:memory:");
        await _connection.OpenAsync();

        await using (var ctx = NewContext(Guid.Empty))
        {
            await ctx.Database.EnsureCreatedAsync();
        }

        var orgA = new Organization("Org A", "org-a");
        var orgB = new Organization("Org B", "org-b");
        _orgA = orgA.Id;
        _orgB = orgB.Id;

        // Organizations are the tenant root (not tenant-scoped) — seed both together.
        await using (var ctx = NewContext(_orgA))
        {
            ctx.Organizations.AddRange(orgA, orgB);
            var leagueA = new League("League A");
            ctx.Leagues.Add(leagueA); // stamped org A on save
            await ctx.SaveChangesAsync();
            _leagueA = leagueA.Id;
        }

        await using (var ctx = NewContext(_orgB))
        {
            var leagueB = new League("League B");
            ctx.Leagues.Add(leagueB); // stamped org B on save
            await ctx.SaveChangesAsync();
            _leagueB = leagueB.Id;
        }
    }

    public async Task DisposeAsync() => await _connection.DisposeAsync();

    [Fact]
    public async Task Query_returns_only_current_tenant_rows()
    {
        await using var ctx = NewContext(_orgA);

        var leagues = await ctx.Leagues.ToListAsync();

        Assert.Single(leagues);
        Assert.Equal(_leagueA, leagues[0].Id);
        Assert.All(leagues, l => Assert.Equal(_orgA, l.OrganizationId));
    }

    [Fact]
    public async Task Cross_org_fetch_by_id_returns_nothing()
    {
        await using var ctx = NewContext(_orgA);

        // Act as org A but ask for org B's league.
        var found = await ctx.Leagues.FirstOrDefaultAsync(l => l.Id == _leagueB);

        Assert.Null(found);
    }

    [Fact]
    public async Task Inserted_row_is_stamped_with_current_tenant_and_invisible_to_others()
    {
        Guid newId;
        await using (var ctxA = NewContext(_orgA))
        {
            var league = new League("Another A");
            ctxA.Leagues.Add(league);
            await ctxA.SaveChangesAsync();
            newId = league.Id;
            Assert.Equal(_orgA, league.OrganizationId);
        }

        await using var ctxB = NewContext(_orgB);
        Assert.Null(await ctxB.Leagues.FirstOrDefaultAsync(l => l.Id == newId));
    }

    [Fact]
    public async Task Cross_tenant_write_is_rejected()
    {
        // Load org A's league while acting as org A.
        League league;
        await using (var ctxA = NewContext(_orgA))
        {
            league = await ctxA.Leagues.SingleAsync(l => l.Id == _leagueA);
        }

        // Attach it to an org-B context and try to persist a change.
        await using var ctxB = NewContext(_orgB);
        ctxB.Attach(league);
        ctxB.Entry(league).State = EntityState.Modified;

        await Assert.ThrowsAsync<InvalidOperationException>(() => ctxB.SaveChangesAsync());
    }
}
