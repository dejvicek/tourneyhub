using TourneyHub.Domain.Common;

namespace TourneyHub.Domain.Competition;

public enum MatchState { Pending, Ready, InProgress, AwaitingConfirmation, Walkover, Completed, Cancelled }

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
    public int? ScoreA { get; private set; }
    public int? ScoreB { get; private set; }
    public Guid? ForfeitedParticipantId { get; private set; }
    public bool IsDraw { get; private set; }

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
        State = MatchState.Pending;
        IsByeMatch = isByeMatch;
    }

    public void SetAdvanceToMatch(Guid advanceToMatchId)
    {
        AdvanceToMatchId = advanceToMatchId;
    }

    public void SetReady()
    {
        EnsureNotCancelled();
        if (State != MatchState.Pending)
            throw new MatchOperationException("invalid_match_state", "Can only transition to Ready from Pending.");
        if (ParticipantAId is null || ParticipantBId is null)
            throw new MatchOperationException("participants_not_determined", "Both participants must be determined to set Ready.");
        State = MatchState.Ready;
    }

    public void StartInProgress()
    {
        EnsureNotCancelled();
        if (State != MatchState.Ready)
            throw new MatchOperationException("invalid_match_state", "Can only transition to InProgress from Ready.");
        State = MatchState.InProgress;
    }

    public void SubmitResult(int? scoreA, int? scoreB, Guid? winnerId, Guid? forfeitedParticipantId, bool isDraw)
    {
        EnsureNotCancelled();
        if (State is not MatchState.Ready and not MatchState.InProgress)
            throw new MatchOperationException("invalid_match_state", "Can only submit result from Ready or InProgress.");
        if (ParticipantAId is null || ParticipantBId is null)
            throw new MatchOperationException("participants_not_determined", "Both participants must be determined to submit a result.");

        ScoreA = scoreA;
        ScoreB = scoreB;
        WinnerId = winnerId;
        ForfeitedParticipantId = forfeitedParticipantId;
        IsDraw = isDraw;

        State = MatchState.AwaitingConfirmation;
    }

    public void ConfirmResult()
    {
        EnsureNotCancelled();
        if (State is not MatchState.AwaitingConfirmation and not MatchState.Walkover)
            throw new MatchOperationException("invalid_match_state", "Can only confirm result from AwaitingConfirmation or Walkover.");
        State = MatchState.Completed;
    }

    public void DisputeResult()
    {
        EnsureNotCancelled();
        if (State != MatchState.AwaitingConfirmation)
            throw new MatchOperationException("invalid_match_state", "Can only dispute result from AwaitingConfirmation.");
        ScoreA = null;
        ScoreB = null;
        WinnerId = null;
        ForfeitedParticipantId = null;
        IsDraw = false;
        State = MatchState.Ready;
    }

    public void MarkWalkover(Guid advancingParticipantId)
    {
        EnsureNotCancelled();
        if (State != MatchState.Ready)
            throw new MatchOperationException("invalid_match_state", "Can only mark walkover from Ready.");
        if (advancingParticipantId != ParticipantAId && advancingParticipantId != ParticipantBId)
            throw new MatchOperationException("invalid_walkover", "Advancing participant must be one of the match participants.");
        WinnerId = advancingParticipantId;
        State = MatchState.Walkover;
    }

    public void EditResult(int? scoreA, int? scoreB, Guid? winnerId, Guid? forfeitedParticipantId, bool isDraw)
    {
        EnsureNotCancelled();
        if (State != MatchState.Completed)
            throw new MatchOperationException("invalid_match_state", "Can only edit result of a Completed match.");

        ScoreA = scoreA;
        ScoreB = scoreB;
        WinnerId = winnerId;
        ForfeitedParticipantId = forfeitedParticipantId;
        IsDraw = isDraw;

        State = MatchState.AwaitingConfirmation;

        RaiseDomainEvent(new MatchResultEditedEvent(Id, TournamentId));
    }

    public void Cancel()
    {
        if (State is MatchState.Completed or MatchState.Cancelled)
            throw new MatchOperationException("invalid_match_state", "Cannot cancel a Completed or already Cancelled match.");
        State = MatchState.Cancelled;
    }

    public void SetParticipant(Guid participantId)
    {
        if (ParticipantAId is null)
        {
            ParticipantAId = participantId;
        }
        else if (ParticipantBId is null)
        {
            ParticipantBId = participantId;
        }
        else
        {
            throw new MatchOperationException("match_full", "Both participant slots are already filled.");
        }
    }

    public bool IsComplete() => State == MatchState.Completed;

    public void SetWinner(Guid winnerId)
    {
        if (winnerId != ParticipantAId && winnerId != ParticipantBId)
            throw new MatchOperationException("invalid_winner", "Winner must be one of the match participants.");
        WinnerId = winnerId;
    }

    private void EnsureNotCancelled()
    {
        if (State == MatchState.Cancelled)
            throw new MatchOperationException("match_cancelled", "Cannot modify a cancelled match.");
    }
}

public class MatchOperationException : Exception
{
    public string Code { get; }
    public MatchOperationException(string code, string message) : base(message) { Code = code; }
}

public record MatchResultSubmittedEvent(Guid MatchId, Guid TournamentId) : DomainEvent;

public record MatchResultEditedEvent(Guid MatchId, Guid TournamentId) : DomainEvent;

public record ParticipantForfeitedEvent(Guid MatchId, Guid ParticipantId) : DomainEvent;

public record ParticipantWithdrawnEvent(Guid TournamentId, Guid ParticipantId) : DomainEvent;