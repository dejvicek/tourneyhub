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

    Task SeedAsync(Guid tournamentId, SeedTournamentCommand command, CancellationToken ct);

    Task<IReadOnlyList<Match>> GenerateBracketAsync(Guid tournamentId, GenerateBracketCommand command, CancellationToken ct);

    Task<IReadOnlyList<Match>> GenerateScheduleAsync(Guid tournamentId, GenerateBracketCommand command, CancellationToken ct);

    Task<Match> SubmitResultAsync(Guid matchId, SubmitResultCommand command, Guid organizationId, Guid actorUserId, int ifMatchVersion, CancellationToken ct);

    Task<Match> ForfeitMatchAsync(Guid matchId, ForfeitMatchCommand command, Guid organizationId, Guid actorUserId, CancellationToken ct);

    Task<Participant> WithdrawParticipantAsync(Guid participantId, Guid organizationId, Guid actorUserId, CancellationToken ct);

    Task<IReadOnlyList<TournamentStanding>> GetTournamentStandingsAsync(Guid tournamentId, CancellationToken ct);

    Task<TournamentOverview?> GetTournamentOverviewAsync(Guid tournamentId, CancellationToken ct);

    Task<IReadOnlyList<SeasonRanking>> GetSeasonRankingsAsync(Guid seasonId, CancellationToken ct);
}
