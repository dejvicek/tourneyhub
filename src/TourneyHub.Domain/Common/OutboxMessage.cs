namespace TourneyHub.Domain.Common;

/// <summary>
/// Persisted domain event awaiting publication (transactional outbox).
/// Written in the same DB transaction as the state change that produced it;
/// a background dispatcher delivers it at-least-once (ADR-0001 §3).
/// Tenant-scoped per Step 01 (NFR-004, NFR-024).
/// </summary>
public class OutboxMessage : TenantEntity
{
    /// <summary>Aggregate type name (e.g. "Tournament", "League").</summary>
    public string AggregateType { get; private set; } = null!;

    /// <summary>The aggregate root's ID.</summary>
    public Guid AggregateId { get; private set; }

    /// <summary>Monotonic version of the aggregate at the time this event was raised.</summary>
    public int AggregateVersion { get; private set; }

    /// <summary>Fully-qualified event type name.</summary>
    public string EventType { get; private set; } = null!;

    /// <summary>Serialised event payload (JSON).</summary>
    public string Payload { get; private set; } = null!;

    /// <summary>UTC timestamp when the event occurred.</summary>
    public DateTime OccurredAt { get; private set; }

    /// <summary>UTC timestamp when the event was successfully published; null if pending.</summary>
    public DateTime? PublishedAt { get; private set; }

    /// <summary>Number of delivery attempts so far.</summary>
    public int RetryCount { get; private set; }

    private OutboxMessage() { }

    public OutboxMessage(
        string aggregateType,
        Guid aggregateId,
        int aggregateVersion,
        string eventType,
        string payload,
        DateTime occurredAt)
    {
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
