using TourneyHub.Domain.Competition;

namespace TourneyHub.Application.Competition;

public interface ITournamentService
{
    Task<Tournament> CreateAsync(CreateTournamentCommand command, Guid organizationId, Guid ownerUserId, CancellationToken ct);

    Task<IReadOnlyList<Tournament>> ListAsync(Guid organizationId, Guid? leagueId, string? status, CancellationToken ct);

    Task<Tournament?> GetByIdAsync(Guid tournamentId, CancellationToken ct);

    Task<Participant> RegisterParticipantAsync(
        Guid tournamentId,
        RegisterParticipantCommand command,
        Guid submittedByUserId,
        CancellationToken ct);

    Task<ParticipantMember> AcceptMemberAsync(Guid participantId, Guid userId, CancellationToken ct);
}
