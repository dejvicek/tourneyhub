using TourneyHub.Application.Identity.Commands;
using TourneyHub.Domain.Identity;

namespace TourneyHub.Application.Identity;

public interface IInvitationService
{
    Task<Invitation> CreateAsync(CreateInvitationCommand command, Guid organizationId, Guid invitedByUserId, CancellationToken ct);

    Task<Invitation?> GetByIdAsync(Guid invitationId, CancellationToken ct);

    Task<Invitation> AcceptAsync(Guid invitationId, Guid userId, string userEmail, CancellationToken ct);

    Task DeclineAsync(Guid invitationId, Guid userId, string userEmail, CancellationToken ct);

    Task<IReadOnlyList<Invitation>> GetPendingForEmailAsync(string email, CancellationToken ct);
}
