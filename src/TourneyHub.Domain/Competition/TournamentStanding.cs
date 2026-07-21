namespace TourneyHub.Domain.Competition;

public class TournamentStanding : TourneyHub.Domain.Common.TenantEntity
{
    public Guid TournamentId { get; private set; }
    public Guid ParticipantId { get; private set; }
    public int Points { get; private set; }
    public int Wins { get; private set; }
    public int Losses { get; private set; }
    public int Draws { get; private set; }
    public int PointsScored { get; private set; }
    public int PointsConceded { get; private set; }
    public int PointsDifference { get; private set; }
    public int Byes { get; private set; }
    public int Rank { get; private set; }

    private TournamentStanding()
    {
    }

    public TournamentStanding(
        Guid tournamentId,
        Guid participantId,
        int points,
        int wins,
        int losses,
        int draws,
        int pointsScored,
        int pointsConceded,
        int pointsDifference,
        int byes,
        int rank)
    {
        TournamentId = tournamentId;
        ParticipantId = participantId;
        Points = points;
        Wins = wins;
        Losses = losses;
        Draws = draws;
        PointsScored = pointsScored;
        PointsConceded = pointsConceded;
        PointsDifference = pointsDifference;
        Byes = byes;
        Rank = rank;
    }

    public void UpdateFromEntry(
        int points,
        int wins,
        int losses,
        int draws,
        int pointsScored,
        int pointsConceded,
        int pointsDifference,
        int byes,
        int rank)
    {
        Points = points;
        Wins = wins;
        Losses = losses;
        Draws = draws;
        PointsScored = pointsScored;
        PointsConceded = pointsConceded;
        PointsDifference = pointsDifference;
        Byes = byes;
        Rank = rank;
    }
}