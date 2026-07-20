using TourneyHub.Domain.Common;

namespace TourneyHub.Domain.Competition;

public class Season : TenantEntity
{
    public Guid LeagueId { get; private set; }

    public string Name { get; private set; }

    public SeasonState State { get; private set; }

    public DateTime? StartedAt { get; private set; }

    public DateTime? CompletedAt { get; private set; }

    public string? RngSeed { get; private set; }

    private Season()
    {
        Name = string.Empty;
    }

    public Season(Guid leagueId, string name, DateTime? startsAt = null, DateTime? endsAt = null)
    {
        LeagueId = leagueId;
        Name = name;
        State = SeasonState.Upcoming;
        StartedAt = startsAt;
        CompletedAt = endsAt;
    }

    public void Activate()
    {
        if (State != SeasonState.Upcoming)
        {
            throw new SeasonOperationException("season_not_upcoming", "Only upcoming seasons can be activated.");
        }

        State = SeasonState.Active;
        StartedAt ??= DateTime.UtcNow;
    }

    public void Close()
    {
        if (State != SeasonState.Active)
        {
            throw new SeasonOperationException("season_not_active", "Only active seasons can be closed.");
        }

        State = SeasonState.Closed;
        CompletedAt = DateTime.UtcNow;
    }

    public void Cancel()
    {
        if (State is SeasonState.Closed)
        {
            throw new SeasonOperationException("season_already_closed", "Cannot cancel a closed season.");
        }

        if (State is SeasonState.Cancelled)
        {
            throw new SeasonOperationException("season_already_cancelled", "Season is already cancelled.");
        }

        State = SeasonState.Cancelled;
    }

    public void SetRngSeed(string seed)
    {
        EnsureMutable();
        RngSeed = seed;
    }

    public bool IsMutable()
    {
        return State is SeasonState.Upcoming or SeasonState.Active;
    }

    private void EnsureMutable()
    {
        if (!IsMutable())
        {
            throw new SeasonOperationException("season_immutable", "Season is not in a mutable state.");
        }
    }
}

public enum SeasonState
{
    Upcoming,
    Active,
    Closed,
    Cancelled,
}

public class SeasonOperationException : Exception
{
    public string Code { get; }

    public SeasonOperationException(string code, string message) : base(message)
    {
        Code = code;
    }
}
