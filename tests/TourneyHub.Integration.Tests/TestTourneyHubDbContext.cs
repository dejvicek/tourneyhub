using Microsoft.EntityFrameworkCore;
using TourneyHub.Application.Tenancy;
using TourneyHub.Domain.Common;
using TourneyHub.Domain.Organizations;
using TourneyHub.Infrastructure.Persistence;

namespace TourneyHub.Integration.Tests;

/// <summary>
/// Test-specific DbContext that extends <see cref="TourneyHubDbContext"/> to include
/// <see cref="TestEntity"/> in the model for outbox integration testing.
/// Uses <c>EnsureCreated</c> to build tables from the model at runtime.
/// </summary>
internal sealed class TestTourneyHubDbContext : TourneyHubDbContext
{
    public TestTourneyHubDbContext(DbContextOptions<TourneyHubDbContext> options, ITenantContext tenant)
        : base(options, tenant)
    {
    }

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        modelBuilder.Entity<TestEntity>(b =>
        {
            b.ToTable("test_entities");
            b.HasKey(e => e.Id);
            b.Property(e => e.OrganizationId).IsRequired();
            b.Property(e => e.Name).IsRequired().HasMaxLength(256);
            b.HasOne<Organization>()
                .WithMany()
                .HasForeignKey(e => e.OrganizationId)
                .OnDelete(DeleteBehavior.Restrict);
        });
    }

    public DbSet<TestEntity> TestEntities => Set<TestEntity>();
}