using System.Text.Json;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Identity.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.ChangeTracking;
using TourneyHub.Application.Tenancy;
using TourneyHub.Domain.Common;
using TourneyHub.Domain.Competition;
using TourneyHub.Domain.Identity;
using TourneyHub.Domain.Organizations;
using TourneyHub.Domain.Platform;

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
public class TourneyHubDbContext : IdentityDbContext<User, IdentityRole<Guid>, Guid>
{
    private readonly ITenantContext _tenant;

    public TourneyHubDbContext(DbContextOptions<TourneyHubDbContext> options, ITenantContext tenant)
        : base(options)
    {
        _tenant = tenant;
    }

    public DbSet<Organization> Organizations => Set<Organization>();

    public DbSet<League> Leagues => Set<League>();

    public DbSet<Season> Seasons => Set<Season>();

    public DbSet<ScoringSystem> ScoringSystems => Set<ScoringSystem>();

    public DbSet<OutboxMessage> OutboxMessages => Set<OutboxMessage>();

    public DbSet<AuditEvent> AuditEvents => Set<AuditEvent>();

    public DbSet<ConsentRecord> ConsentRecords => Set<ConsentRecord>();

    public DbSet<Membership> Memberships => Set<Membership>();

    public DbSet<Invitation> Invitations => Set<Invitation>();

    public DbSet<SentNotification> SentNotifications => Set<SentNotification>();

    public DbSet<Tournament> Tournaments => Set<Tournament>();

    public DbSet<Participant> Participants => Set<Participant>();

    public DbSet<ParticipantMember> ParticipantMembers => Set<ParticipantMember>();

    public DbSet<Match> Matches => Set<Match>();

    internal DbSet<IdempotencyEntry> IdempotencyEntries => Set<IdempotencyEntry>();

    /// <summary>
    /// Test entity used by integration tests to exercise the domain-event capture +
    /// transactional-outbox path end-to-end. Not part of the production domain model.
    /// </summary>
    // internal DbSet<TestEntity> TestEntities => Set<TestEntity>();

    protected override void OnModelCreating(ModelBuilder builder)
    {
        ArgumentNullException.ThrowIfNull(builder);

        base.OnModelCreating(builder);

        builder.Entity<User>(b =>
        {
            b.ToTable("users");
            b.Property(u => u.State).HasConversion<string>().IsRequired();
            b.Property(u => u.DisplayName).HasMaxLength(256);
            b.Property(u => u.AvatarUrl).HasMaxLength(2048);
            b.Property(u => u.Locale).HasMaxLength(16);
            b.Property(u => u.Timezone).HasMaxLength(64);
            b.Property(u => u.LastLoginAt);
        });

        builder.Entity<IdentityRole<Guid>>(b =>
        {
            b.ToTable("roles");
        });

        builder.Entity<IdentityUserRole<Guid>>(b =>
        {
            b.ToTable("user_roles");
        });

        builder.Entity<IdentityUserClaim<Guid>>(b =>
        {
            b.ToTable("user_claims");
        });

        builder.Entity<IdentityUserLogin<Guid>>(b =>
        {
            b.ToTable("user_logins");
        });

        builder.Entity<IdentityRoleClaim<Guid>>(b =>
        {
            b.ToTable("role_claims");
        });

        builder.Entity<IdentityUserToken<Guid>>(b =>
        {
            b.ToTable("user_tokens");
        });

        builder.Entity<Organization>(b =>
        {
            b.ToTable("organizations");
            b.HasKey(e => e.Id);
            b.Property(e => e.Name).IsRequired();
            b.Property(e => e.Slug).IsRequired();
            b.Property(e => e.State).HasConversion<string>().IsRequired();
            b.Property(e => e.Plan).HasMaxLength(128).IsRequired();
            b.HasIndex(e => e.Slug).IsUnique();
            b.Property(e => e.Version).IsConcurrencyToken();
        });

        builder.Entity<Membership>(b =>
        {
            b.ToTable("memberships");
            b.HasKey(e => e.Id);
            b.Property(e => e.UserId).IsRequired();
            b.Property(e => e.OrganizationId).IsRequired();
            b.Property(e => e.Role).HasConversion<string>().IsRequired();
            b.Property(e => e.State).HasConversion<string>().IsRequired();
            b.Property(e => e.JoinedAt).IsRequired();
            b.HasIndex(e => new { e.UserId, e.OrganizationId }).IsUnique();
            b.HasOne<Organization>()
                .WithMany()
                .HasForeignKey(e => e.OrganizationId)
                .OnDelete(DeleteBehavior.Restrict);
        });

        builder.Entity<Invitation>(b =>
        {
            b.ToTable("invitations");
            b.HasKey(e => e.Id);
            b.Property(e => e.OrganizationId).IsRequired();
            b.Property(e => e.Email).IsRequired().HasMaxLength(256);
            b.Property(e => e.ScopeType).HasConversion<string>().IsRequired();
            b.Property(e => e.ScopeId).IsRequired();
            b.Property(e => e.Role).HasConversion<string>().IsRequired();
            b.Property(e => e.State).HasConversion<string>().IsRequired();
            b.Property(e => e.InvitedByUserId).IsRequired();
            b.Property(e => e.ExpiresAt).IsRequired();
            b.Property(e => e.Version).IsConcurrencyToken();
            b.HasIndex(e => e.Email);
            b.HasIndex(e => new { e.OrganizationId, e.State });
            b.HasOne<Organization>()
                .WithMany()
                .HasForeignKey(e => e.OrganizationId)
                .OnDelete(DeleteBehavior.Restrict);
        });

        builder.Entity<League>(b =>
        {
            b.ToTable("leagues");
            b.HasKey(e => e.Id);
            b.Property(e => e.OrganizationId).IsRequired();
            b.Property(e => e.Name).IsRequired().HasMaxLength(256);
            b.Property(e => e.Slug).IsRequired().HasMaxLength(128);
            b.Property(e => e.Description).HasMaxLength(2000);
            b.Property(e => e.Visibility).HasConversion<string>().IsRequired();
            b.Property(e => e.OwnerId).IsRequired();
            b.Property(e => e.State).HasConversion<string>().IsRequired();
            b.Property(e => e.Version).IsConcurrencyToken();
            b.HasIndex(e => new { e.OrganizationId, e.Slug }).IsUnique();
            b.HasIndex(e => new { e.OrganizationId, e.Id });
            b.HasQueryFilter(e => e.OrganizationId == _tenant.OrganizationId);
            b.HasOne<Organization>()
                .WithMany()
                .HasForeignKey(e => e.OrganizationId)
                .OnDelete(DeleteBehavior.Restrict);
        });

        builder.Entity<Season>(b =>
        {
            b.ToTable("seasons");
            b.HasKey(e => e.Id);
            b.Property(e => e.OrganizationId).IsRequired();
            b.Property(e => e.LeagueId).IsRequired();
            b.Property(e => e.Name).IsRequired().HasMaxLength(256);
            b.Property(e => e.State).HasConversion<string>().IsRequired();
            b.Property(e => e.StartedAt);
            b.Property(e => e.CompletedAt);
            b.Property(e => e.RngSeed).HasMaxLength(64);
            b.Property(e => e.Version).IsConcurrencyToken();
            b.HasIndex(e => new { e.OrganizationId, e.Id });
            b.HasIndex(e => new { e.LeagueId, e.State }).HasFilter("\"State\" = 'Active'");
            b.HasQueryFilter(e => e.OrganizationId == _tenant.OrganizationId);
            b.HasOne<League>()
                .WithMany()
                .HasForeignKey(e => e.LeagueId)
                .OnDelete(DeleteBehavior.Cascade);
            b.HasOne<Organization>()
                .WithMany()
                .HasForeignKey(e => e.OrganizationId)
                .OnDelete(DeleteBehavior.Restrict);
        });

        builder.Entity<ScoringSystem>(b =>
        {
            b.ToTable("scoring_systems");
            b.HasKey(e => e.Id);
            b.Property(e => e.OrganizationId).IsRequired();
            b.Property(e => e.Name).IsRequired().HasMaxLength(256);
            b.Property(e => e.Config).IsRequired().HasColumnType("jsonb")
                .HasConversion(
                    v => JsonSerializer.Serialize(v, JsonSerializerOptions.Default),
                    v => JsonSerializer.Deserialize<ScoringConfig>(v, JsonSerializerOptions.Default) ?? new ScoringConfig());
            b.Property(e => e.Version).IsConcurrencyToken();
            b.HasIndex(e => new { e.OrganizationId, e.Name }).IsUnique();
            b.HasQueryFilter(e => e.OrganizationId == _tenant.OrganizationId);
            b.HasOne<Organization>()
                .WithMany()
                .HasForeignKey(e => e.OrganizationId)
                .OnDelete(DeleteBehavior.Restrict);
        });

        IdempotencyConfiguration.ConfigureIdempotencyKeys(builder);

        builder.Entity<OutboxMessage>(b =>
        {
            b.ToTable("outbox_messages");
            b.HasKey(e => e.Id);
            b.Property(e => e.OrganizationId).IsRequired();
            b.Property(e => e.AggregateType).IsRequired().HasMaxLength(256);
            b.Property(e => e.AggregateId).IsRequired();
            b.Property(e => e.AggregateVersion).IsRequired();
            b.Property(e => e.EventType).IsRequired().HasMaxLength(256);
            b.Property(e => e.Payload).IsRequired().HasColumnType("jsonb");
            b.Property(e => e.OccurredAt).IsRequired();
            b.Property(e => e.PublishedAt);
            b.Property(e => e.RetryCount).IsRequired();
            b.HasIndex(e => e.PublishedAt).HasFilter("\"PublishedAt\" IS NULL");
            b.HasIndex(e => new { e.OrganizationId, e.AggregateType, e.AggregateId, e.AggregateVersion });
        });

        builder.Entity<AuditEvent>(b =>
        {
            b.ToTable("audit_events");
            b.HasKey(e => e.Id);
            b.Property(e => e.OrganizationId).IsRequired();
            b.Property(e => e.ActorId).IsRequired().HasMaxLength(256);
            b.Property(e => e.Action).IsRequired().HasMaxLength(256);
            b.Property(e => e.TargetType).IsRequired().HasMaxLength(256);
            b.Property(e => e.TargetId).IsRequired().HasMaxLength(256);
            b.Property(e => e.Before).HasColumnType("jsonb");
            b.Property(e => e.After).HasColumnType("jsonb");
            b.Property(e => e.IpAddress).HasMaxLength(64);
            b.Property(e => e.UserAgent).HasMaxLength(512);
            b.Property(e => e.OccurredAt).IsRequired();
            b.HasIndex(e => new { e.OrganizationId, e.TargetType, e.TargetId });
            b.HasQueryFilter(e => e.OrganizationId == _tenant.OrganizationId);
            b.HasOne<Organization>()
                .WithMany()
                .HasForeignKey(e => e.OrganizationId)
                .OnDelete(DeleteBehavior.Restrict);
        });

        builder.Entity<ConsentRecord>(b =>
        {
            b.ToTable("consent_records");
            b.HasKey(e => e.Id);
            b.Property(e => e.UserId).IsRequired();
            b.Property(e => e.PolicyVersion).IsRequired().HasMaxLength(128);
            b.Property(e => e.AcceptedAt).IsRequired();
            b.HasIndex(e => e.UserId);
        });

        builder.Entity<SentNotification>(b =>
        {
            b.ToTable("sent_notifications");
            b.HasKey(e => e.Id);
            b.Property(e => e.OutboxMessageId).IsRequired();
            b.Property(e => e.Recipient).IsRequired().HasMaxLength(256);
            b.Property(e => e.Subject).IsRequired().HasMaxLength(256);
            b.Property(e => e.SentAt).IsRequired();
            b.HasIndex(e => new { e.OutboxMessageId, e.Recipient }).IsUnique();
        });

        // TestEntity configured only in integration tests via a test-specific
        // DbContext; not part of the production model.

        builder.Entity<Tournament>(b =>
        {
            b.ToTable("tournaments");
            b.HasKey(e => e.Id);
            b.Property(e => e.OrganizationId).IsRequired();
            b.Property(e => e.LeagueId);
            b.Property(e => e.SeasonId);
            b.Property(e => e.DisciplineName).IsRequired().HasMaxLength(256);
            b.Property(e => e.ResultModel).HasConversion<string>().IsRequired();
            b.Property(e => e.ScoreConfig).HasColumnType("jsonb")
                .HasConversion(
                    v => JsonSerializer.Serialize(v, JsonSerializerOptions.Default),
                    v => JsonSerializer.Deserialize<TournamentScoreConfig>(v, JsonSerializerOptions.Default));
            b.Property(e => e.TeamSize).IsRequired();
            b.Property(e => e.FormatType).HasConversion<string>().IsRequired();
            b.Property(e => e.ResultEntryMode).HasConversion<string>().IsRequired();
            b.Property(e => e.BestOf);
            b.Property(e => e.State).HasConversion<string>().IsRequired();
            b.Property(e => e.RngSeed).HasMaxLength(64);
            b.Property(e => e.Currency).HasMaxLength(3);
            b.Property(e => e.EntryFeeAmountMinor);
            b.Property(e => e.RegOpenAt);
            b.Property(e => e.RegCloseAt);
            b.Property(e => e.MaxParticipants);
            b.Property(e => e.Version).IsConcurrencyToken();
            b.HasIndex(e => new { e.OrganizationId, e.Id });
            b.HasIndex(e => new { e.LeagueId, e.State });
            b.HasQueryFilter(e => e.OrganizationId == _tenant.OrganizationId);
            b.HasOne<Organization>()
                .WithMany()
                .HasForeignKey(e => e.OrganizationId)
                .OnDelete(DeleteBehavior.Restrict);
            b.HasOne<League>()
                .WithMany()
                .HasForeignKey(e => e.LeagueId)
                .OnDelete(DeleteBehavior.SetNull);
            b.HasOne<Season>()
                .WithMany()
                .HasForeignKey(e => e.SeasonId)
                .OnDelete(DeleteBehavior.SetNull);
        });

        builder.Entity<Participant>(b =>
        {
            b.ToTable("participants");
            b.HasKey(e => e.Id);
            b.Property(e => e.OrganizationId).IsRequired();
            b.Property(e => e.TournamentId).IsRequired();
            b.Property(e => e.CaptainUserId).IsRequired();
            b.Property(e => e.DisplayName).HasMaxLength(256);
            b.Property(e => e.Status).HasConversion<string>().IsRequired();
            b.Property(e => e.Version).IsConcurrencyToken();
            b.HasIndex(e => new { e.OrganizationId, e.Id });
            b.HasIndex(e => new { e.TournamentId, e.Status });
            b.HasQueryFilter(e => e.OrganizationId == _tenant.OrganizationId);
            b.HasOne<Organization>()
                .WithMany()
                .HasForeignKey(e => e.OrganizationId)
                .OnDelete(DeleteBehavior.Restrict);
            b.HasOne<Tournament>()
                .WithMany()
                .HasForeignKey(e => e.TournamentId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        builder.Entity<ParticipantMember>(b =>
        {
            b.ToTable("participant_members");
            b.HasKey(e => e.Id);
            b.Property(e => e.ParticipantId).IsRequired();
            b.Property(e => e.TournamentId).IsRequired();
            b.Property(e => e.UserId).IsRequired();
            b.Property(e => e.Status).HasConversion<string>().IsRequired();
            b.HasIndex(e => new { e.TournamentId, e.UserId }).IsUnique();
            b.HasIndex(e => new { e.ParticipantId, e.UserId }).IsUnique();
            b.HasOne<Participant>()
                .WithMany()
                .HasForeignKey(e => e.ParticipantId)
                .OnDelete(DeleteBehavior.Cascade);
            b.HasOne<Tournament>()
                .WithMany()
                .HasForeignKey(e => e.TournamentId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        builder.Entity<Match>(b =>
        {
            b.ToTable("matches");
            b.HasKey(e => e.Id);
            b.Property(e => e.OrganizationId).IsRequired();
            b.Property(e => e.TournamentId).IsRequired();
            b.Property(e => e.RoundNumber).IsRequired();
            b.Property(e => e.PositionInRound).IsRequired();
            b.Property(e => e.ParticipantAId);
            b.Property(e => e.ParticipantBId);
            b.Property(e => e.WinnerId);
            b.Property(e => e.State).HasConversion<string>().IsRequired();
            b.Property(e => e.IsByeMatch).IsRequired();
            b.Property(e => e.AdvanceToMatchId);
            b.Property(e => e.ScoreA);
            b.Property(e => e.ScoreB);
            b.Property(e => e.ForfeitedParticipantId);
            b.Property(e => e.IsDraw).IsRequired();
            b.Property(e => e.Version).IsConcurrencyToken();
            b.HasIndex(e => new { e.OrganizationId, e.Id });
            b.HasIndex(e => new { e.TournamentId, e.RoundNumber, e.PositionInRound }).IsUnique();
            b.HasQueryFilter(e => e.OrganizationId == _tenant.OrganizationId);
            b.HasOne<Organization>()
                .WithMany()
                .HasForeignKey(e => e.OrganizationId)
                .OnDelete(DeleteBehavior.Restrict);
            b.HasOne<Tournament>()
                .WithMany()
                .HasForeignKey(e => e.TournamentId)
                .OnDelete(DeleteBehavior.Cascade);
            b.HasOne<Participant>()
                .WithMany()
                .HasForeignKey(e => e.ParticipantAId)
                .OnDelete(DeleteBehavior.SetNull);
            b.HasOne<Participant>()
                .WithMany()
                .HasForeignKey(e => e.ParticipantBId)
                .OnDelete(DeleteBehavior.SetNull);
            b.HasOne<Match>()
                .WithMany()
                .HasForeignKey(e => e.AdvanceToMatchId)
                .OnDelete(DeleteBehavior.SetNull);
        });

        builder.Entity<TestEntity>(b =>
        {
            b.ToTable("test_entities");
            b.HasKey(e => e.Id);
            b.Property(e => e.OrganizationId).IsRequired();
            b.Property(e => e.Name).IsRequired().HasMaxLength(256);
            b.HasQueryFilter(e => e.OrganizationId == _tenant.OrganizationId);
            b.HasOne<Organization>()
                .WithMany()
                .HasForeignKey(e => e.OrganizationId)
                .OnDelete(DeleteBehavior.Restrict);
        });
    }

    public override int SaveChanges()
    {
        CaptureDomainEvents();
        StampAndGuardTenant();
        IncrementEntityVersions();
        return base.SaveChanges();
    }

    public override int SaveChanges(bool acceptAllChangesOnSuccess)
    {
        CaptureDomainEvents();
        StampAndGuardTenant();
        IncrementEntityVersions();
        return base.SaveChanges(acceptAllChangesOnSuccess);
    }

    public override Task<int> SaveChangesAsync(CancellationToken cancellationToken = default)
    {
        CaptureDomainEvents();
        StampAndGuardTenant();
        IncrementEntityVersions();
        return base.SaveChangesAsync(cancellationToken);
    }

    public override Task<int> SaveChangesAsync(bool acceptAllChangesOnSuccess, CancellationToken cancellationToken = default)
    {
        CaptureDomainEvents();
        StampAndGuardTenant();
        IncrementEntityVersions();
        return base.SaveChangesAsync(acceptAllChangesOnSuccess, cancellationToken);
    }

    private void IncrementEntityVersions()
    {
        foreach (var entry in ChangeTracker.Entries<Entity>())
        {
            if (entry.State == EntityState.Modified)
            {
                entry.Entity.IncrementVersion();
            }
        }
    }

    /// <summary>
    /// Inserts: stamp the current organization. Updates/deletes: reject if the row belongs
    /// to a different organization, or if the OrganizationId has changed (immutable).
    /// Fails closed when no tenant is resolved (NFR-004, FR-152).
    /// </summary>
    private void StampAndGuardTenant()
    {
        var hasTenantScopedChanges = ChangeTracker.Entries<TenantEntity>().Any();
        if (!hasTenantScopedChanges)
        {
            return;
        }

        if (!_tenant.HasTenant)
        {
            throw new InvalidOperationException(
                "Tenant-scoped write blocked: no organization resolved for the current scope. " +
                "All tenant-scoped writes require an active organization (NFR-004, FR-152, FR-154).");
        }

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
                    var originalOrgId = (Guid)property.OriginalValue!;
                    var currentOrgId = (Guid)property.CurrentValue!;
                    if (originalOrgId != currentOrgId)
                    {
                        throw new InvalidOperationException(
                            "OrganizationId is immutable and cannot be changed after insert.");
                    }

                    if (currentOrgId != _tenant.OrganizationId)
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

    /// <summary>
    /// Captures domain events raised by tracked entities and writes corresponding
    /// <see cref="OutboxMessage"/> rows in the same transaction (no dual-write).
    /// Events are serialised as JSON and stored with aggregate metadata for ordering
    /// and deduplication (ADR-0001 §3).
    /// </summary>
    private void CaptureDomainEvents()
    {
        var entitiesWithEvents = ChangeTracker.Entries<Entity>()
            .Where(e => e.Entity.DomainEvents.Count > 0)
            .ToList();

        if (entitiesWithEvents.Count == 0)
        {
            return;
        }

        var jsonOptions = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };

        foreach (var entry in entitiesWithEvents)
        {
            var entity = entry.Entity;
            var aggregateType = entry.Entity.GetType().Name;
            var aggregateId = entity.Id;
            var aggregateVersion = entity.Version;
            var organizationId = GetEntityOrganizationId(entry, entity);

            foreach (var domainEvent in entity.DomainEvents)
            {
                var eventType = domainEvent.GetType().FullName!;
                var payload = JsonSerializer.Serialize(domainEvent, domainEvent.GetType(), jsonOptions);
                var occurredAt = domainEvent is DomainEvent de ? de.OccurredAt : DateTime.UtcNow;

                var outboxMessage = new OutboxMessage(
                    aggregateType,
                    aggregateId,
                    aggregateVersion,
                    eventType,
                    payload,
                    occurredAt,
                    organizationId);

                OutboxMessages.Add(outboxMessage);
            }

            entity.ClearDomainEvents();
        }
    }

    private Guid GetEntityOrganizationId(EntityEntry entry, Entity entity)
    {
        if (entity is not TenantEntity te) return Guid.Empty;

        if (entry.State == EntityState.Added && _tenant.HasTenant)
        {
            return _tenant.OrganizationId;
        }

        return te.OrganizationId;
    }
}
