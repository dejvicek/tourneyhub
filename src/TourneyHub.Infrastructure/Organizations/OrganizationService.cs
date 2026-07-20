using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using TourneyHub.Application.Organizations;
using TourneyHub.Domain.Organizations;
using TourneyHub.Infrastructure.Persistence;

namespace TourneyHub.Infrastructure.Organizations;

internal sealed partial class OrganizationService : IOrganizationService
{
    private readonly TourneyHubDbContext _db;
    private readonly ILogger<OrganizationService> _logger;

    public OrganizationService(TourneyHubDbContext db, ILogger<OrganizationService> logger)
    {
        _db = db;
        _logger = logger;
    }

    public async Task<Organization> CreateAsync(
        CreateOrganizationCommand command, Guid ownerUserId, CancellationToken cancellationToken = default)
    {
        var slug = string.IsNullOrWhiteSpace(command.Slug)
            ? GenerateSlug(command.Name)
            : command.Slug.Trim().ToLowerInvariant();

        if (await _db.Organizations.AnyAsync(o => o.Slug == slug, cancellationToken))
        {
            throw new OrganizationOperationException("slug_already_taken", $"The slug '{slug}' is already taken.");
        }

        var org = new Organization(command.Name.Trim(), slug);
        _db.Organizations.Add(org);

        var membership = new Membership(ownerUserId, org.Id, MembershipRole.OrgOwner);
        _db.Set<Membership>().Add(membership);

        await _db.SaveChangesAsync(cancellationToken);
        return org;
    }

    public async Task<IReadOnlyList<Organization>> ListUserOrganizationsAsync(
        Guid userId, CancellationToken cancellationToken = default)
    {
        var orgIds = await _db.Set<Membership>()
            .Where(m => m.UserId == userId && m.State == MembershipState.Active)
            .Select(m => m.OrganizationId)
            .ToListAsync(cancellationToken);

        return await _db.Organizations
            .Where(o => orgIds.Contains(o.Id))
            .ToListAsync(cancellationToken);
    }

    public async Task<Organization?> GetByIdAsync(
        Guid organizationId, CancellationToken cancellationToken = default)
    {
        return await _db.Organizations
            .FirstOrDefaultAsync(o => o.Id == organizationId, cancellationToken);
    }

    public async Task TransferOwnershipAsync(
        Guid organizationId, Guid currentOwnerId, Guid newOwnerUserId, CancellationToken cancellationToken = default)
    {
        var memberships = await _db.Set<Membership>()
            .Where(m => m.OrganizationId == organizationId
                        && m.State == MembershipState.Active
                        && (m.UserId == currentOwnerId || m.UserId == newOwnerUserId))
            .ToListAsync(cancellationToken);

        var currentOwner = memberships.FirstOrDefault(m => m.UserId == currentOwnerId && m.Role == MembershipRole.OrgOwner);
        if (currentOwner is null)
        {
            throw new OrganizationOperationException("forbidden", "Only an OrgOwner can transfer ownership.");
        }

        var newOwner = memberships.FirstOrDefault(m => m.UserId == newOwnerUserId);
        if (newOwner is null)
        {
            throw new OrganizationOperationException("not_found", "The new owner must be an active member of the organization.");
        }

        var ownerCount = await _db.Set<Membership>()
            .CountAsync(m => m.OrganizationId == organizationId
                             && m.Role == MembershipRole.OrgOwner
                             && m.State == MembershipState.Active, cancellationToken);

        if (ownerCount <= 1 && currentOwnerId == newOwnerUserId)
        {
            throw new OrganizationOperationException("sole_owner_cannot_leave", "Cannot remove the last OrgOwner (BR-013).");
        }

        currentOwner.ChangeRole(MembershipRole.Organizer);
        newOwner.ChangeRole(MembershipRole.OrgOwner);

        await _db.SaveChangesAsync(cancellationToken);
    }

    public async Task SetSuspensionAsync(
        Guid organizationId, bool suspended, string? reason, Guid actorId, CancellationToken cancellationToken = default)
    {
        var org = await _db.Organizations.FirstOrDefaultAsync(o => o.Id == organizationId, cancellationToken);
        if (org is null)
        {
            throw new OrganizationOperationException("not_found", $"Organization '{organizationId}' not found.");
        }

        if (suspended)
        {
            org.Suspend();
        }
        else
        {
            org.Reactivate();
        }

        await _db.SaveChangesAsync(cancellationToken);

        LogSuspensionChanged(org.Id, suspended, reason, actorId);
    }

    [LoggerMessage(EventId = 10, Level = LogLevel.Warning,
        Message = "Organization {OrgId} suspended={Suspended} by {ActorId}. Reason: {Reason}")]
    private partial void LogSuspensionChanged(Guid orgId, bool suspended, string? reason, Guid actorId);

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
            clean = "org";
        }

        while (clean.Contains("--"))
        {
            clean = clean.Replace("--", "-");
        }

        return clean.Trim('-');
    }
}

public class OrganizationOperationException : Exception
{
    public string Code { get; }

    public OrganizationOperationException(string code, string message)
        : base(message)
    {
        Code = code;
    }
}