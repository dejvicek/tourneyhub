using TourneyHub.Domain.Common;

namespace TourneyHub.Domain.Identity.Events;

public sealed record PasswordResetRequestedEvent(
    Guid UserId,
    string Email,
    string ResetToken) : DomainEvent;
