using TourneyHub.Domain.Organizations;

namespace TourneyHub.Application.Organizations;

public interface IOrganizationService
{
    Task<Organization> CreateAsync(CreateOrganizationCommand command, Guid ownerUserId, CancellationToken cancellationToken = default);

    Task<IReadOnlyList<Organization>> ListUserOrganizationsAsync(Guid userId, CancellationToken cancellationToken = default);

    Task<Organization?> GetByIdAsync(Guid organizationId, CancellationToken cancellationToken = default);

    Task TransferOwnershipAsync(Guid organizationId, Guid currentOwnerId, Guid newOwnerUserId, CancellationToken cancellationToken = default);

    Task SetSuspensionAsync(Guid organizationId, bool suspended, string? reason, Guid actorId, CancellationToken cancellationToken = default);
}
