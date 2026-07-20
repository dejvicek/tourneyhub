using TourneyHub.Domain.Competition;

namespace TourneyHub.Application.Competition;

public sealed record CreateTournamentCommand(
    string DisciplineName,
    string ResultModel,
    int TeamSize,
    string FormatType,
    string? ResultEntryMode = null,
    Guid? LeagueId = null,
    Guid? SeasonId = null,
    TournamentScoreConfig? ScoreConfig = null,
    int? BestOf = null,
    string? Currency = null,
    long? EntryFeeAmountMinor = null,
    DateTime? RegOpenAt = null,
    DateTime? RegCloseAt = null,
    int? MaxParticipants = null);

public sealed record RegisterParticipantCommand(
    string? ParticipantDisplayName,
    List<string>? RosterInviteEmails);

public sealed record AcceptMemberCommand();
