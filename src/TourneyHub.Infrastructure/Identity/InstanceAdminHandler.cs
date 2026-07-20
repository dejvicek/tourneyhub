using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Identity;
using Microsoft.Extensions.DependencyInjection;
using TourneyHub.Domain.Identity;

namespace TourneyHub.Infrastructure.Identity;

internal sealed class InstanceAdminHandler : AuthorizationHandler<InstanceAdminRequirement>
{
    private readonly IServiceScopeFactory _scopeFactory;

    public InstanceAdminHandler(IServiceScopeFactory scopeFactory)
    {
        _scopeFactory = scopeFactory;
    }

    protected override async Task HandleRequirementAsync(
        AuthorizationHandlerContext context,
        InstanceAdminRequirement requirement)
    {
        if (context.User.Identity?.IsAuthenticated != true)
        {
            return;
        }

        using var scope = _scopeFactory.CreateScope();
        var userManager = scope.ServiceProvider.GetRequiredService<UserManager<User>>();

        var user = await userManager.GetUserAsync(context.User);
        if (user is null)
        {
            return;
        }

        if (await userManager.IsInRoleAsync(user, "InstanceAdmin"))
        {
            context.Succeed(requirement);
        }
    }
}