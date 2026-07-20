namespace TourneyHub.Domain.Identity;

/// <summary>
/// Record of a user accepting a specific privacy-policy version (FR-122, FR-132).
/// Captured at registration and on policy-update re-acceptance.
/// Not tenant-scoped — consent belongs to the user, not the organization.
/// </summary>
public class ConsentRecord
{
    public Guid Id { get; private set; } = Guid.NewGuid();

    /// <summary>User who accepted the policy.</summary>
    public Guid UserId { get; private set; }

    /// <summary>Policy version identifier (e.g. "v1.0", "2026-07-20").</summary>
    public string PolicyVersion { get; private set; } = null!;

    /// <summary>UTC timestamp when the user accepted.</summary>
    public DateTime AcceptedAt { get; private set; }

    private ConsentRecord() { }

    public ConsentRecord(Guid userId, string policyVersion)
    {
        UserId = userId;
        PolicyVersion = policyVersion;
        AcceptedAt = DateTime.UtcNow;
    }
}