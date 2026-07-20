using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using TourneyHub.Application.Common;
using TourneyHub.Application.Identity;
using TourneyHub.Application.Identity.Commands;
using TourneyHub.Domain.Identity;
using TourneyHub.Domain.Organizations;
using TourneyHub.Infrastructure.Persistence;

namespace TourneyHub.Infrastructure.Identity;

internal sealed partial class InvitationService : IInvitationService
{
    private readonly TourneyHubDbContext _db;
    private readonly ILogger<InvitationService> _logger;

    public InvitationService(TourneyHubDbContext db, ILogger<InvitationService> logger)
    {
        _db = db;
        _logger = logger;
    }

    public async Task<Invitation> CreateAsync(
        CreateInvitationCommand command,
        Guid organizationId,
        Guid invitedByUserId,
        CancellationToken ct)
    {
        var invitation = new Invitation(
            organizationId,
            command.Email,
            command.ScopeType,
            command.ScopeId,
            command.Role,
            invitedByUserId);

        _db.Invitations.Add(invitation);
        await _db.SaveChangesAsync(ct);

        LogInvitationCreated(invitation.Id, command.Email, command.ScopeType.ToString(), command.ScopeId);
        return invitation;
    }

    public async Task<Invitation?> GetByIdAsync(Guid invitationId, CancellationToken ct)
    {
        return await _db.Invitations
            .FirstOrDefaultAsync(i => i.Id == invitationId, ct);
    }

    public async Task<Invitation> AcceptAsync(Guid invitationId, Guid userId, string userEmail, CancellationToken ct)
    {
        var invitation = await _db.Invitations
            .FirstOrDefaultAsync(i => i.Id == invitationId, ct);

        if (invitation is null)
        {
            throw new InvitationOperationException(ErrorCodes.InvitationNotFound, "Invitation not found.");
        }

        if (!string.Equals(invitation.Email, userEmail, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvitationOperationException(ErrorCodes.InvitationEmailMismatch, "The authenticated email does not match the invitation.");
        }

        ThrowIfNotAcceptable(invitation);

        invitation.Accept();

        var membership = new Membership(userId, invitation.OrganizationId, MapRole(invitation.Role));
        _db.Memberships.Add(membership);

        await _db.SaveChangesAsync(ct);

        LogInvitationAccepted(invitation.Id, userId, invitation.Email);
        return invitation;
    }

    public async Task DeclineAsync(Guid invitationId, Guid userId, string userEmail, CancellationToken ct)
    {
        var invitation = await _db.Invitations
            .FirstOrDefaultAsync(i => i.Id == invitationId, ct);

        if (invitation is null)
        {
            throw new InvitationOperationException(ErrorCodes.InvitationNotFound, "Invitation not found.");
        }

        if (!string.Equals(invitation.Email, userEmail, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvitationOperationException(ErrorCodes.InvitationEmailMismatch, "The authenticated email does not match the invitation.");
        }

        invitation.Decline();
        await _db.SaveChangesAsync(ct);

        LogInvitationDeclined(invitation.Id, userId, invitation.Email);
    }

    public async Task<IReadOnlyList<Invitation>> GetPendingForEmailAsync(string email, CancellationToken ct)
    {
        var normalizedEmail = email.ToLowerInvariant();
        return await _db.Invitations
            .Where(i => i.Email.Equals(normalizedEmail) && i.State == InvitationState.Pending)
            .ToListAsync(ct);
    }

    private static MembershipRole MapRole(InvitedRole role) => role switch
    {
        InvitedRole.Organizer => MembershipRole.Organizer,
        InvitedRole.Player => MembershipRole.Player,
        _ => throw new ArgumentOutOfRangeException(nameof(role)),
    };

    private static void ThrowIfNotAcceptable(Invitation invitation)
    {
        if (invitation.State == InvitationState.Pending && invitation.IsExpired())
        {
            invitation.TryExpire();
            throw new InvitationOperationException(ErrorCodes.InvitationExpired, "Invitation has expired.");
        }

        if (invitation.State != InvitationState.Pending)
        {
            var (code, message) = invitation.State switch
            {
                InvitationState.Accepted => (ErrorCodes.InvitationAlreadyAccepted, "Invitation has already been accepted."),
                InvitationState.Declined => (ErrorCodes.InvitationDeclined, "Invitation has been declined."),
                InvitationState.Revoked => (ErrorCodes.InvitationRevoked, "Invitation has been revoked."),
                InvitationState.Expired => (ErrorCodes.InvitationExpired, "Invitation has expired."),
                _ => ("invitation_not_pending", "Invitation cannot be accepted."),
            };

            throw new InvitationOperationException(code, message);
        }
    }

    [LoggerMessage(Level = LogLevel.Information, Message = "Invitation {InvitationId} created for {Email} to {ScopeType} {ScopeId}")]
    private partial void LogInvitationCreated(Guid invitationId, string email, string scopeType, Guid scopeId);

    [LoggerMessage(Level = LogLevel.Information, Message = "Invitation {InvitationId} accepted by user {UserId} ({Email})")]
    private partial void LogInvitationAccepted(Guid invitationId, Guid userId, string email);

    [LoggerMessage(Level = LogLevel.Information, Message = "Invitation {InvitationId} declined by user {UserId} ({Email})")]
    private partial void LogInvitationDeclined(Guid invitationId, Guid userId, string email);
}
