using TourneyHub.Domain.Common;

namespace TourneyHub.Domain.Competition;

public enum MatchState { Scheduled, InProgress, Completed, Cancelled }

public class Match : TenantEntity
{
    public Guid TournamentId { get; private set; }
    public int RoundNumber { get; private set; }
    public int PositionInRound { get; private set; }
    public Guid? ParticipantAId { get; private set; }
    public Guid? ParticipantBId { get; private set; }
    public Guid? WinnerId { get; private set; }
    public MatchState State { get; private set; }
    public bool IsByeMatch { get; private set; }
    public Guid? AdvanceToMatchId { get; private set; }

    private Match()
    {
    }

    public Match(
        Guid tournamentId,
        int roundNumber,
        int positionInRound,
        Guid? participantAId,
        Guid? participantBId,
        bool isByeMatch)
    {
        TournamentId = tournamentId;
        RoundNumber = roundNumber;
        PositionInRound = positionInRound;
        ParticipantAId = participantAId;
        ParticipantBId = participantBId;
        State = MatchState.Scheduled;
        IsByeMatch = isByeMatch;
    }

    public void SetAdvanceToMatch(Guid advanceToMatchId)
    {
        AdvanceToMatchId = advanceToMatchId;
    }
}

public class MatchOperationException : Exception
{
    public string Code { get; }
    public MatchOperationException(string code, string message) : base(message) { Code = code; }
}