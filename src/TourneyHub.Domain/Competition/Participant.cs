using TourneyHub.Domain.Common;

namespace TourneyHub.Domain.Competition;

public enum ParticipantState { Incomplete, Confirmed }

public class Participant : TenantEntity
{
    public Guid TournamentId { get; private set; }
    public Guid CaptainUserId { get; private set; }
    public string? DisplayName { get; private set; }
    public ParticipantState Status { get; private set; }

    private Participant()
    {
    }

    public Participant(Guid tournamentId, Guid captainUserId, string? displayName = null)
    {
        TournamentId = tournamentId;
        CaptainUserId = captainUserId;
        DisplayName = displayName?.Trim();
        Status = ParticipantState.Incomplete;
    }

    public void Confirm()
    {
        if (Status == ParticipantState.Confirmed)
            throw new ParticipantOperationException("participant_already_confirmed", "Participant is already confirmed.");
        Status = ParticipantState.Confirmed;
    }

    public void Withdraw(Guid tournamentId)
    {
        if (Status != ParticipantState.Confirmed)
            throw new ParticipantOperationException("not_confirmed", "Only confirmed participants can withdraw.");
        Status = ParticipantState.Confirmed;
        RaiseDomainEvent(new ParticipantWithdrawnEvent(tournamentId, Id));
    }
}

public class ParticipantOperationException : Exception
{
    public string Code { get; }
    public ParticipantOperationException(string code, string message) : base(message) { Code = code; }
}
