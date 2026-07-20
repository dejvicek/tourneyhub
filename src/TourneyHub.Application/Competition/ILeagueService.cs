using TourneyHub.Domain.Competition;

namespace TourneyHub.Application.Competition;

public interface ILeagueService
{
    Task<League> CreateAsync(CreateLeagueCommand command, Guid organizationId, Guid ownerUserId, CancellationToken ct);

    Task<IReadOnlyList<League>> ListAsync(Guid organizationId, CancellationToken ct);

    Task<League?> GetByIdAsync(Guid leagueId, CancellationToken ct);

    Task<League?> GetBySlugForPublicAsync(string slug, CancellationToken ct);

    Task<League> UpdateAsync(Guid leagueId, UpdateLeagueCommand command, CancellationToken ct);

    Task<League> ArchiveAsync(Guid leagueId, CancellationToken ct);

    Task<League> UnarchiveAsync(Guid leagueId, CancellationToken ct);

    Task<League> TransferOwnershipAsync(Guid leagueId, Guid newOwnerId, CancellationToken ct);

    Task DeleteAsync(Guid leagueId, CancellationToken ct);

    Task<Season> CreateSeasonAsync(Guid leagueId, CreateSeasonCommand command, CancellationToken ct);

    Task<Season> ActivateSeasonAsync(Guid seasonId, CancellationToken ct);

    Task<Season> CloseSeasonAsync(Guid seasonId, CancellationToken ct);

    Task<Season> CancelSeasonAsync(Guid seasonId, CancellationToken ct);

    Task<IReadOnlyList<Season>> ListSeasonsAsync(Guid leagueId, CancellationToken ct);
}
