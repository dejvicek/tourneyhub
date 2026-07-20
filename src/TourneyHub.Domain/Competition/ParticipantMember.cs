using TourneyHub.Domain.Common;

namespace TourneyHub.Domain.Competition;

public enum ParticipantMemberStatus { Pending, Accepted }

public class ParticipantMember : Entity
{
    public Guid ParticipantId { get; private set; }
    public Guid TournamentId { get; private set; }
    public Guid UserId { get; private set; }
    public ParticipantMemberStatus Status { get; private set; }

    private ParticipantMember()
    {
    }

    public ParticipantMember(Guid participantId, Guid tournamentId, Guid userId, ParticipantMemberStatus status = ParticipantMemberStatus.Pending)
    {
        ParticipantId = participantId;
        TournamentId = tournamentId;
        UserId = userId;
        Status = status;
    }

    public void Accept()
    {
        if (Status == ParticipantMemberStatus.Accepted)
            throw new ParticipantMemberOperationException("member_already_accepted", "Member has already accepted.");
        Status = ParticipantMemberStatus.Accepted;
    }
}

public class ParticipantMemberOperationException : Exception
{
    public string Code { get; }
    public ParticipantMemberOperationException(string code, string message) : base(message) { Code = code; }
}
