namespace TourneyHub.Domain.Common;

/// <summary>
/// Persisted domain event awaiting publication (transactional outbox).
/// Written in the same DB transaction as the state change that produced it;
/// a background dispatcher delivers it at-least-once (ADR-0001 §3).
/// Carries an optional OrganizationId for tenant-scoped events; non-tenant-scoped
/// events (e.g. registration) use Guid.Empty.
/// </summary>
public class OutboxMessage : Entity
{
    public Guid OrganizationId { get; private set; }

    public string AggregateType { get; private set; } = null!;

    public Guid AggregateId { get; private set; }

    public int AggregateVersion { get; private set; }

    public string EventType { get; private set; } = null!;

    public string Payload { get; private set; } = null!;

    public DateTime OccurredAt { get; private set; }

    public DateTime? PublishedAt { get; private set; }

    public int RetryCount { get; private set; }

    private OutboxMessage() { }

    public OutboxMessage(
        string aggregateType,
        Guid aggregateId,
        int aggregateVersion,
        string eventType,
        string payload,
        DateTime occurredAt,
        Guid organizationId = default)
    {
        OrganizationId = organizationId;
        AggregateType = aggregateType;
        AggregateId = aggregateId;
        AggregateVersion = aggregateVersion;
        EventType = eventType;
        Payload = payload;
        OccurredAt = occurredAt;
        RetryCount = 0;
    }

    public void MarkPublished()
    {
        PublishedAt = DateTime.UtcNow;
    }

    public void IncrementRetry()
    {
        RetryCount++;
    }
}
