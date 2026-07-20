namespace TourneyHub.Application.Notifications;

/// <summary>
/// Distinguishes transactional notifications (necessary for core flows,
/// not subject to marketing opt-out) from engagement notifications
/// (subject to user opt-out, Future — FR-143).
/// </summary>
public enum NotificationCategory
{
    Transactional,
    Engagement
}