using Microsoft.AspNetCore.Identity;

namespace TourneyHub.Domain.Identity;

public class User : IdentityUser<Guid>
{
    public AccountState State { get; set; } = AccountState.PendingVerification;

    public string? DisplayName { get; set; }

    public string? AvatarUrl { get; set; }

    public string? Locale { get; set; }

    public string? Timezone { get; set; }

    public DateTime? LastLoginAt { get; set; }
}
