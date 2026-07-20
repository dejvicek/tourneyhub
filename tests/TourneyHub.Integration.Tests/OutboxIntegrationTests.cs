using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Testcontainers.PostgreSql;
using TourneyHub.Application.Tenancy;
using TourneyHub.Domain.Common;
using TourneyHub.Domain.Identity;
using TourneyHub.Domain.Organizations;
using TourneyHub.Domain.Platform;
using TourneyHub.Infrastructure.Persistence;
using Xunit;

namespace TourneyHub.Integration.Tests;

/// <summary>
/// Integration tests for the transactional outbox, audit-log append-only behaviour,
/// and consent-record persistence. Uses PostgreSQL via Testcontainers.
/// </summary>
public sealed class OutboxIntegrationTests : IAsyncLifetime
{
    private readonly PostgreSqlContainer _postgres = new PostgreSqlBuilder()
        .WithDatabase("tourneyhub_outbox_test")
        .WithUsername("tourneyhub")
        .WithPassword("tourneyhub")
        .Build();

    private Guid _orgId;

    private sealed class FixedTenant(Guid organizationId) : ITenantContext
    {
        public Guid OrganizationId { get; } = organizationId;
        public bool HasTenant => OrganizationId != Guid.Empty;
    }

    private TourneyHubDbContext NewContext()
    {
        var options = new DbContextOptionsBuilder<TourneyHubDbContext>()
            .UseNpgsql(_postgres.GetConnectionString())
            .Options;

        return new TourneyHubDbContext(options, new FixedTenant(_orgId));
    }

    private TestTourneyHubDbContext NewTestContext()
    {
        var options = new DbContextOptionsBuilder<TourneyHubDbContext>()
            .UseNpgsql(_postgres.GetConnectionString())
            .Options;

        return new TestTourneyHubDbContext(options, new FixedTenant(_orgId));
    }

    public async Task InitializeAsync()
    {
        await _postgres.StartAsync();

        var options = new DbContextOptionsBuilder<TourneyHubDbContext>()
            .UseNpgsql(_postgres.GetConnectionString())
            .Options;

        await using (var ctx = new TourneyHubDbContext(options, new FixedTenant(Guid.Empty)))
        {
            await ctx.Database.MigrateAsync();

            var org = new Organization("Outbox Test Org", "outbox-test-org");
            ctx.Organizations.Add(org);
            await ctx.SaveChangesAsync();
            _orgId = org.Id;
        }

        await using (var testCtx = new TestTourneyHubDbContext(options, new FixedTenant(Guid.Empty)))
        {
            await testCtx.Database.EnsureCreatedAsync();
        }
    }

    public async Task DisposeAsync()
    {
        await _postgres.DisposeAsync();
    }

    [Fact]
    public async Task Domain_event_captured_as_outbox_message_in_same_transaction()
    {
        await using var db = NewTestContext();

        var entity = new TestEntity("entity-1");
        entity.RaiseTestEvent("test-value");
        db.TestEntities.Add(entity);
        await db.SaveChangesAsync();

        var allMessages = await db.Set<OutboxMessage>().ToListAsync();

        var outboxMessages = allMessages
            .Where(m => m.AggregateId == entity.Id)
            .ToList();

        Assert.Single(outboxMessages);
        var msg = outboxMessages[0];
        Assert.Equal(nameof(TestEntity), msg.AggregateType);
        Assert.Equal(0, msg.AggregateVersion);
        Assert.Contains("TestEventRaised", msg.EventType);
        Assert.Contains("test-value", msg.Payload);
        Assert.Null(msg.PublishedAt);
        Assert.Equal(_orgId, msg.OrganizationId);
    }

    [Fact]
    public async Task Domain_events_from_multiple_entities_are_all_captured()
    {
        await using var db = NewTestContext();

        var entity1 = new TestEntity("multi-1");
        entity1.RaiseTestEvent("first");
        db.TestEntities.Add(entity1);

        var entity2 = new TestEntity("multi-2");
        entity2.RaiseTestEvent("second");
        entity2.RaiseTestEvent("third");
        db.TestEntities.Add(entity2);

        await db.SaveChangesAsync();

        var count = await db.Set<OutboxMessage>()
            .Where(m => m.AggregateId == entity1.Id || m.AggregateId == entity2.Id)
            .CountAsync();

        Assert.Equal(3, count);
    }

    [Fact]
    public async Task Audit_event_can_be_created_and_retrieved()
    {
        await using var db = NewContext();

        var audit = new AuditEvent(
            "user-1", "league_created", "League", "league-1",
            null, "{\"name\":\"Test League\"}", "127.0.0.1", "Mozilla/5.0");

        db.AuditEvents.Add(audit);
        await db.SaveChangesAsync();

        var saved = await db.AuditEvents.FirstOrDefaultAsync(a => a.Id == audit.Id);
        Assert.NotNull(saved);
        Assert.Equal("user-1", saved.ActorId);
        Assert.Equal("league_created", saved.Action);
        Assert.Equal("League", saved.TargetType);
        Assert.Equal(_orgId, saved.OrganizationId);
    }

    [Fact]
    public async Task Audit_event_properties_cannot_be_modified_after_construction()
    {
        await using var db = NewContext();

        var audit = new AuditEvent(
            "user-1", "test_action", "Test", "test-1",
            "{\"status\":\"old\"}", "{\"status\":\"new\"}", "127.0.0.1", null);

        db.AuditEvents.Add(audit);
        await db.SaveChangesAsync();

        var saved = await db.AuditEvents.FirstOrDefaultAsync(a => a.Id == audit.Id);
        Assert.NotNull(saved);

        // Verify all writable properties have private setters at type level.
        // The entity model enforces immutability via private setters.
        var type = typeof(AuditEvent);
        var publicInstanceProperties = type.GetProperties(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
        foreach (var prop in publicInstanceProperties)
        {
            var setter = prop.GetSetMethod(nonPublic: false);
            Assert.Null(setter);
        }
    }

    [Fact]
    public async Task Consent_record_persists_correctly()
    {
        await using var db = NewContext();

        var userId = Guid.NewGuid();
        var record = new ConsentRecord(userId, "v1.0");
        db.ConsentRecords.Add(record);
        await db.SaveChangesAsync();

        var saved = await db.ConsentRecords.FirstOrDefaultAsync(c => c.Id == record.Id);
        Assert.NotNull(saved);
        Assert.Equal(userId, saved.UserId);
        Assert.Equal("v1.0", saved.PolicyVersion);
    }

    [Fact]
    public async Task Domain_events_are_cleared_after_save()
    {
        await using var db = NewTestContext();

        var entity = new TestEntity("clear-entity");
        entity.RaiseTestEvent("before-save");

        Assert.NotEmpty(entity.DomainEvents);

        db.TestEntities.Add(entity);
        await db.SaveChangesAsync();

        Assert.Empty(entity.DomainEvents);
    }

    [Fact]
    public async Task Unpublished_outbox_messages_found_by_dispatcher_query()
    {
        await using var db = NewTestContext();

        var entity = new TestEntity("dispatch-entity");
        entity.RaiseTestEvent("dispatch-event");
        db.TestEntities.Add(entity);
        await db.SaveChangesAsync();

        var pending = await db.Set<OutboxMessage>()
            .Where(m => m.PublishedAt == null && m.RetryCount < 3)
            .OrderBy(m => m.OccurredAt)
            .ToListAsync();

        Assert.NotEmpty(pending);
    }
}