using TourneyHub.Domain.Common;

namespace TourneyHub.Domain.Identity.Events;

public sealed record UserRegisteredEvent(
    Guid UserId,
    string Email,
    string DisplayName,
    string VerificationToken) : DomainEvent;
