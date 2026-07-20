using TourneyHub.Domain.Common;

namespace TourneyHub.Domain.Competition;

public class League : TenantEntity
{
    public string Name { get; private set; }

    public string Slug { get; private set; }

    public string? Description { get; private set; }

    public LeagueVisibility Visibility { get; private set; }

    public Guid OwnerId { get; private set; }

    public LeagueState State { get; private set; }

    private League()
    {
        Name = string.Empty;
        Slug = string.Empty;
    }

    public League(string name, string slug, LeagueVisibility visibility, Guid ownerId, string? description = null)
    {
        Name = name;
        Slug = slug;
        Visibility = visibility;
        OwnerId = ownerId;
        State = LeagueState.Active;
        Description = description;
    }

    public void Update(string name, LeagueVisibility visibility, string? description)
    {
        EnsureNotDeleted();
        Name = name;
        Visibility = visibility;
        Description = description;
    }

    public void Archive()
    {
        EnsureNotDeleted();
        if (State == LeagueState.Archived)
        {
            throw new LeagueOperationException("league_already_archived", "League is already archived.");
        }

        State = LeagueState.Archived;
    }

    public void Unarchive()
    {
        if (State != LeagueState.Archived)
        {
            throw new LeagueOperationException("league_not_archived", "Only archived leagues can be unarchived.");
        }

        State = LeagueState.Active;
    }

    public void Delete()
    {
        if (State == LeagueState.Deleted)
        {
            throw new LeagueOperationException("league_already_deleted", "League is already deleted.");
        }

        State = LeagueState.Deleted;
    }

    public void TransferOwnership(Guid newOwnerId)
    {
        EnsureNotDeleted();
        OwnerId = newOwnerId;
    }

    private void EnsureNotDeleted()
    {
        if (State == LeagueState.Deleted)
        {
            throw new LeagueOperationException("league_deleted", "Cannot modify a deleted league.");
        }
    }
}

public enum LeagueVisibility
{
    Public,
    Unlisted,
    Private,
}

public enum LeagueState
{
    Active,
    Archived,
    Deleted,
}

public class LeagueOperationException : Exception
{
    public string Code { get; }

    public LeagueOperationException(string code, string message) : base(message)
    {
        Code = code;
    }
}
