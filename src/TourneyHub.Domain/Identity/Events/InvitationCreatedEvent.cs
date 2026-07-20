using TourneyHub.Domain.Common;

namespace TourneyHub.Domain.Identity.Events;

public sealed record InvitationCreatedEvent(
    Guid InvitationId,
    Guid OrganizationId,
    string Email,
    InvitationScopeType ScopeType,
    Guid ScopeId,
    InvitedRole Role) : DomainEvent;
