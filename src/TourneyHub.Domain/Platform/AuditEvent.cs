namespace TourneyHub.Domain.Platform;

using Common;

/// <summary>
/// Append-only audit entry for security, finance, and administrative events
/// (FR-120, FR-121, NFR-017). Rows are NEVER updated or deleted — enforced by
/// application logic and verified by architecture tests.
/// Tenant-scoped: carries <see cref="OrganizationId"/> for isolation (NFR-024).
/// </summary>
public class AuditEvent : TenantEntity
{
    /// <summary>ID of the actor who performed the action (user or system).</summary>
    public string ActorId { get; private set; } = null!;

    /// <summary>Descriptive action name (e.g. "result_edit", "league_created").</summary>
    public string Action { get; private set; } = null!;

    /// <summary>Type of the affected resource (e.g. "Tournament", "League").</summary>
    public string TargetType { get; private set; } = null!;

    /// <summary>ID of the affected resource.</summary>
    public string TargetId { get; private set; } = null!;

    /// <summary>JSON snapshot of the resource state before the change. Null for creates.</summary>
    public string? Before { get; private set; }

    /// <summary>JSON snapshot of the resource state after the change. Null for deletes.</summary>
    public string? After { get; private set; }

    /// <summary>Client IP address at the time of the action.</summary>
    public string? IpAddress { get; private set; }

    /// <summary>User-Agent header value at the time of the action.</summary>
    public string? UserAgent { get; private set; }

    /// <summary>UTC timestamp when the action occurred.</summary>
    public DateTime OccurredAt { get; private set; }

    private AuditEvent() { }

    public AuditEvent(
        string actorId,
        string action,
        string targetType,
        string targetId,
        string? before,
        string? after,
        string? ipAddress,
        string? userAgent)
    {
        ActorId = actorId;
        Action = action;
        TargetType = targetType;
        TargetId = targetId;
        Before = before;
        After = after;
        IpAddress = ipAddress;
        UserAgent = userAgent;
        OccurredAt = DateTime.UtcNow;
    }
}