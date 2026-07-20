using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using Microsoft.EntityFrameworkCore;

namespace TourneyHub.Infrastructure.Persistence;

internal sealed class IdempotencyEntry
{
    [Key]
    public long Id { get; private set; }

    public Guid OrganizationId { get; private set; }

    [MaxLength(256)]
    public string Key { get; private set; } = null!;

    [MaxLength(64)]
    public string RequestHash { get; private set; } = null!;

    public byte[] ResponseBody { get; private set; } = null!;

    [MaxLength(64)]
    public string ResponseContentType { get; private set; } = null!;

    public int ResponseStatusCode { get; private set; }

    public DateTime CreatedAt { get; private set; } = DateTime.UtcNow;

    private IdempotencyEntry() { }

    public IdempotencyEntry(Guid organizationId, string key, string requestHash, byte[] responseBody, string responseContentType, int responseStatusCode)
    {
        OrganizationId = organizationId;
        Key = key;
        RequestHash = requestHash;
        ResponseBody = responseBody;
        ResponseContentType = responseContentType;
        ResponseStatusCode = responseStatusCode;
    }
}

internal static class IdempotencyConfiguration
{
    public static void ConfigureIdempotencyKeys(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<IdempotencyEntry>(b =>
        {
            b.ToTable("idempotency_keys");
            b.HasKey(e => e.Id);
            b.HasIndex(e => new { e.OrganizationId, e.Key }).IsUnique();
            b.Property(e => e.OrganizationId).IsRequired();
            b.Property(e => e.Key).IsRequired().HasMaxLength(256);
            b.Property(e => e.RequestHash).IsRequired().HasMaxLength(64);
            b.Property(e => e.ResponseBody).IsRequired();
            b.Property(e => e.ResponseContentType).IsRequired().HasMaxLength(64);
            b.Property(e => e.ResponseStatusCode).IsRequired();
            b.Property(e => e.CreatedAt).IsRequired();
        });
    }
}