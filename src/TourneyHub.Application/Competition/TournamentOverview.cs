using TourneyHub.Domain.Competition;

namespace TourneyHub.Application.Competition;

public sealed record TournamentOverview(
    Tournament Tournament,
    IReadOnlyList<Match> Matches,
    IReadOnlyList<TournamentStanding> Standings);