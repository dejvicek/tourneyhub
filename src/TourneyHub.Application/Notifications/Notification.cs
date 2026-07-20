namespace TourneyHub.Application.Notifications;

/// <summary>
/// A notification message to be delivered through an <see cref="Abstractions.INotificationChannel"/>.
/// Carries tenant context for scoping and a category for opt-out filtering (FR-143).
/// </summary>
public sealed record Notification
{
    /// <summary>Owning organization for tenant scoping (NFR-024).</summary>
    public Guid OrganizationId { get; init; }

    /// <summary>Recipient email address (or identifier for other channels).</summary>
    public string Recipient { get; init; } = null!;

    /// <summary>Subject line (for email channels).</summary>
    public string Subject { get; init; } = null!;

    /// <summary>Plain-text body.</summary>
    public string Body { get; init; } = null!;

    /// <summary>Transactional or engagement (FR-143).</summary>
    public NotificationCategory Category { get; init; } = NotificationCategory.Transactional;
}