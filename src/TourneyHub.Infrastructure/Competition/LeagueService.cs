using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using TourneyHub.Application.Common;
using TourneyHub.Application.Competition;
using TourneyHub.Domain.Competition;
using TourneyHub.Infrastructure.Persistence;

namespace TourneyHub.Infrastructure.Competition;

internal sealed partial class LeagueService : ILeagueService
{
    private readonly TourneyHubDbContext _db;
    private readonly ILogger<LeagueService> _logger;

    public LeagueService(TourneyHubDbContext db, ILogger<LeagueService> logger)
    {
        _db = db;
        _logger = logger;
    }

    public async Task<League> CreateAsync(
        CreateLeagueCommand command, Guid organizationId, Guid ownerUserId, CancellationToken ct)
    {
        var slug = string.IsNullOrWhiteSpace(command.Slug)
            ? GenerateSlug(command.Name)
            : command.Slug.Trim().ToLowerInvariant();

        if (await _db.Leagues.AnyAsync(l => l.OrganizationId == organizationId && l.Slug == slug, ct))
        {
            throw new LeagueOperationException(
                ErrorCodes.SlugAlreadyTakenInOrg,
                $"The slug '{slug}' is already taken in this organization.");
        }

        var league = new League(command.Name.Trim(), slug, command.Visibility, ownerUserId, command.Description?.Trim());
        _db.Leagues.Add(league);
        await _db.SaveChangesAsync(ct);

        LogLeagueCreated(league.Id, league.Name, slug);
        return league;
    }

    public async Task<IReadOnlyList<League>> ListAsync(Guid organizationId, CancellationToken ct)
    {
        return await _db.Leagues
            .Where(l => l.State != LeagueState.Deleted)
            .OrderBy(l => l.Name)
            .ToListAsync(ct);
    }

    public async Task<League?> GetByIdAsync(Guid leagueId, CancellationToken ct)
    {
        return await _db.Leagues
            .FirstOrDefaultAsync(l => l.Id == leagueId && l.State != LeagueState.Deleted, ct);
    }

    public async Task<League?> GetBySlugForPublicAsync(string slug, CancellationToken ct)
    {
        var normalized = slug.Trim().ToLowerInvariant();
        return await _db.Leagues
            .IgnoreQueryFilters()
            .FirstOrDefaultAsync(
                l => l.Slug == normalized
                     && l.Visibility == LeagueVisibility.Public
                     && l.State == LeagueState.Active,
                ct);
    }

    public async Task<League> UpdateAsync(Guid leagueId, UpdateLeagueCommand command, CancellationToken ct)
    {
        var league = await GetRequiredAsync(leagueId, ct);

        var name = command.Name?.Trim() ?? league.Name;
        var visibility = command.Visibility ?? league.Visibility;
        var description = command.Description?.Trim() ?? league.Description;

        league.Update(name, visibility, description);
        await _db.SaveChangesAsync(ct);

        LogLeagueUpdated(league.Id, league.Name);
        return league;
    }

    public async Task<League> ArchiveAsync(Guid leagueId, CancellationToken ct)
    {
        var league = await GetRequiredAsync(leagueId, ct);
        league.Archive();
        await _db.SaveChangesAsync(ct);

        LogLeagueArchived(league.Id);
        return league;
    }

    public async Task<League> UnarchiveAsync(Guid leagueId, CancellationToken ct)
    {
        var league = await GetRequiredAsync(leagueId, ct);
        league.Unarchive();
        await _db.SaveChangesAsync(ct);

        LogLeagueUnarchived(league.Id);
        return league;
    }

    public async Task<League> TransferOwnershipAsync(Guid leagueId, Guid newOwnerId, CancellationToken ct)
    {
        var league = await GetRequiredAsync(leagueId, ct);
        league.TransferOwnership(newOwnerId);
        await _db.SaveChangesAsync(ct);

        LogLeagueOwnershipTransferred(league.Id, newOwnerId);
        return league;
    }

    public async Task DeleteAsync(Guid leagueId, CancellationToken ct)
    {
        var league = await GetRequiredAsync(leagueId, ct);
        league.Delete();
        await _db.SaveChangesAsync(ct);

        LogLeagueDeleted(league.Id);
    }

    public async Task<Season> CreateSeasonAsync(Guid leagueId, CreateSeasonCommand command, CancellationToken ct)
    {
        var league = await GetRequiredAsync(leagueId, ct);

        if (league.State == LeagueState.Archived)
        {
            throw new LeagueOperationException(
                ErrorCodes.LeagueArchived,
                "Cannot create a season in an archived league.");
        }

        var season = new Season(leagueId, command.Name.Trim(), command.StartsAt, command.EndsAt);
        _db.Seasons.Add(season);
        await _db.SaveChangesAsync(ct);

        LogSeasonCreated(season.Id, season.Name, leagueId);
        return season;
    }

    public async Task<Season> ActivateSeasonAsync(Guid seasonId, CancellationToken ct)
    {
        var season = await _db.Seasons.FirstOrDefaultAsync(s => s.Id == seasonId, ct)
            ?? throw new SeasonOperationException(ErrorCodes.NotFound, "Season not found.");

        var league = await _db.Leagues.FirstOrDefaultAsync(l => l.Id == season.LeagueId, ct)
            ?? throw new LeagueOperationException(ErrorCodes.NotFound, "League not found.");

        if (league.State == LeagueState.Archived)
        {
            throw new LeagueOperationException(ErrorCodes.LeagueArchived, "Cannot activate a season in an archived league (FR-029).");
        }

        var hasActiveSeason = await _db.Seasons
            .AnyAsync(s => s.LeagueId == season.LeagueId && s.State == SeasonState.Active && s.Id != seasonId, ct);

        if (hasActiveSeason)
        {
            throw new SeasonOperationException(
                ErrorCodes.SeasonAlreadyActive,
                "There is already an active season in this league. Only one season can be active at a time (BR-002).");
        }

        season.Activate();
        await _db.SaveChangesAsync(ct);

        LogSeasonActivated(season.Id);
        return season;
    }

    public async Task<Season> CloseSeasonAsync(Guid seasonId, CancellationToken ct)
    {
        var season = await _db.Seasons.FirstOrDefaultAsync(s => s.Id == seasonId, ct)
            ?? throw new SeasonOperationException(ErrorCodes.NotFound, "Season not found.");

        season.Close();
        await _db.SaveChangesAsync(ct);

        LogSeasonClosed(season.Id);
        return season;
    }

    public async Task<Season> CancelSeasonAsync(Guid seasonId, CancellationToken ct)
    {
        var season = await _db.Seasons.FirstOrDefaultAsync(s => s.Id == seasonId, ct)
            ?? throw new SeasonOperationException(ErrorCodes.NotFound, "Season not found.");

        season.Cancel();
        await _db.SaveChangesAsync(ct);

        LogSeasonCancelled(season.Id);
        return season;
    }

    public async Task<IReadOnlyList<Season>> ListSeasonsAsync(Guid leagueId, CancellationToken ct)
    {
        return await _db.Seasons
            .Where(s => s.LeagueId == leagueId)
            .OrderByDescending(s => s.State == SeasonState.Active)
            .ThenByDescending(s => s.StartedAt)
            .ToListAsync(ct);
    }

    private async Task<League> GetRequiredAsync(Guid leagueId, CancellationToken ct)
    {
        return await _db.Leagues.FirstOrDefaultAsync(l => l.Id == leagueId, ct)
            ?? throw new LeagueOperationException(ErrorCodes.LeagueNotFound, "League not found.");
    }

    private static string GenerateSlug(string name)
    {
        var baseSlug = name.Trim().ToLowerInvariant().Replace(' ', '-');

        var allowed = new char[baseSlug.Length];
        var pos = 0;
        foreach (var c in baseSlug)
        {
            if (char.IsLetterOrDigit(c) || c == '-')
            {
                allowed[pos++] = c;
            }
        }

        var clean = new string(allowed, 0, pos);
        if (clean.Length == 0)
        {
            clean = "league";
        }

        while (clean.Contains("--"))
        {
            clean = clean.Replace("--", "-");
        }

        return clean.Trim('-');
    }

    [LoggerMessage(Level = LogLevel.Information, Message = "League {LeagueId} '{Name}' created with slug '{Slug}'")]
    private partial void LogLeagueCreated(Guid leagueId, string name, string slug);

    [LoggerMessage(Level = LogLevel.Information, Message = "League {LeagueId} '{Name}' updated")]
    private partial void LogLeagueUpdated(Guid leagueId, string name);

    [LoggerMessage(Level = LogLevel.Information, Message = "League {LeagueId} archived")]
    private partial void LogLeagueArchived(Guid leagueId);

    [LoggerMessage(Level = LogLevel.Information, Message = "League {LeagueId} unarchived")]
    private partial void LogLeagueUnarchived(Guid leagueId);

    [LoggerMessage(Level = LogLevel.Information, Message = "League {LeagueId} ownership transferred to {NewOwnerId}")]
    private partial void LogLeagueOwnershipTransferred(Guid leagueId, Guid newOwnerId);

    [LoggerMessage(Level = LogLevel.Information, Message = "League {LeagueId} deleted")]
    private partial void LogLeagueDeleted(Guid leagueId);

    [LoggerMessage(Level = LogLevel.Information, Message = "Season {SeasonId} '{Name}' created for league {LeagueId}")]
    private partial void LogSeasonCreated(Guid seasonId, string name, Guid leagueId);

    [LoggerMessage(Level = LogLevel.Information, Message = "Season {SeasonId} activated")]
    private partial void LogSeasonActivated(Guid seasonId);

    [LoggerMessage(Level = LogLevel.Information, Message = "Season {SeasonId} closed")]
    private partial void LogSeasonClosed(Guid seasonId);

    [LoggerMessage(Level = LogLevel.Information, Message = "Season {SeasonId} cancelled")]
    private partial void LogSeasonCancelled(Guid seasonId);
}
