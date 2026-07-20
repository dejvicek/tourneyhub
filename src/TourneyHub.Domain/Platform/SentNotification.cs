namespace TourneyHub.Domain.Platform;

/// <summary>
/// Tracks sent notifications for idempotency (at-least-once delivery).
/// Duplicate detection is based on <see cref="OutboxMessageId"/> + <see cref="Recipient"/>
/// compound unique index so a redelivered outbox message does not produce a duplicate email.
/// </summary>
public class SentNotification
{
    public Guid Id { get; private set; } = Guid.NewGuid();
    public Guid OutboxMessageId { get; private set; }
    public string Recipient { get; private set; } = null!;
    public string Subject { get; private set; } = null!;
    public DateTime SentAt { get; private set; }

    private SentNotification() { }

    public SentNotification(Guid outboxMessageId, string recipient, string subject)
    {
        OutboxMessageId = outboxMessageId;
        Recipient = recipient;
        Subject = subject;
        SentAt = DateTime.UtcNow;
    }
}
