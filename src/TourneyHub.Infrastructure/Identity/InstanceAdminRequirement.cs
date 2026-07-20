using Microsoft.AspNetCore.Authorization;

namespace TourneyHub.Infrastructure.Identity;

public sealed class InstanceAdminRequirement : IAuthorizationRequirement
{
    public const string PolicyName = "InstanceAdmin";
}
