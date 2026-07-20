namespace TourneyHub.Application.Abstractions;

using TourneyHub.Application.Notifications;

/// <summary>
/// Port for sending notifications (email, SMS, push, etc.).
/// Triggered by domain events via the transactional outbox — a failed send never
/// blocks the originating transaction (FR-141).
/// </summary>
public interface INotificationChannel
{
    /// <summary>Human-readable channel name for logging/selection.</summary>
    string ChannelName { get; }

    /// <summary>Send a single notification. Implementations handle retry/delivery.</summary>
    Task SendAsync(Notification notification, CancellationToken cancellationToken = default);
}