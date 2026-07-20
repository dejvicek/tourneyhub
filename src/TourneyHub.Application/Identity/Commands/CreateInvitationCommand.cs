using TourneyHub.Domain.Identity;

namespace TourneyHub.Application.Identity.Commands;

public sealed record CreateInvitationCommand(
    string Email,
    InvitationScopeType ScopeType,
    Guid ScopeId,
    InvitedRole Role);

public sealed record InvitationResponse(
    Guid Id,
    Guid OrganizationId,
    string Email,
    string ScopeType,
    Guid ScopeId,
    string Role,
    string State,
    int Version,
    DateTime ExpiresAt);
