using TourneyHub.Domain.Competition;

namespace TourneyHub.Application.Competition;

public sealed record CreateLeagueCommand(string Name, string? Slug, LeagueVisibility Visibility, string? Description);

public sealed record UpdateLeagueCommand(string? Name, LeagueVisibility? Visibility, string? Description);

public sealed record CreateSeasonCommand(string Name, DateTime? StartsAt, DateTime? EndsAt);
