using TourneyHub.Domain.Competition;

namespace TourneyHub.Application.Competition;

public sealed record SubmitResultCommand(
    int? ScoreA,
    int? ScoreB,
    Guid? WinnerId,
    Guid? ForfeitedParticipantId,
    bool IsDraw);

public sealed record ForfeitMatchCommand(
    Guid ForfeitedParticipantId);