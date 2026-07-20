using Microsoft.AspNetCore.Identity;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using TourneyHub.Domain.Identity;

namespace TourneyHub.Infrastructure.Identity;

internal sealed partial class BootstrapService : IHostedService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly IConfiguration _configuration;
    private readonly ILogger<BootstrapService> _logger;

    private const string AdminEmailKey = "TOURNEYHUB_ADMIN_EMAIL";
    private const string AdminBootstrapTokenKey = "TOURNEYHUB_ADMIN_BOOTSTRAP_TOKEN";
    private const string AllowFirstUserAdminKey = "TOURNEYHUB_ALLOW_FIRST_USER_ADMIN";

    public BootstrapService(
        IServiceProvider serviceProvider,
        IConfiguration configuration,
        ILogger<BootstrapService> logger)
    {
        _serviceProvider = serviceProvider;
        _configuration = configuration;
        _logger = logger;
    }

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        using var scope = _serviceProvider.CreateScope();

        try
        {
            var roleManager = scope.ServiceProvider.GetRequiredService<RoleManager<IdentityRole<Guid>>>();
            var userManager = scope.ServiceProvider.GetRequiredService<UserManager<User>>();

            await SeedInstanceAdminRole(roleManager);

            var adminEmail = _configuration[AdminEmailKey];
            var bootstrapToken = _configuration[AdminBootstrapTokenKey];

            if (string.IsNullOrWhiteSpace(adminEmail) && string.IsNullOrWhiteSpace(bootstrapToken))
            {
                LogBootstrapSkipped();
                return;
            }

            var existingAdmins = await userManager.GetUsersInRoleAsync("InstanceAdmin");
            if (existingAdmins.Count > 0)
            {
                LogAdminAlreadyExists();
                return;
            }

            if (!string.IsNullOrWhiteSpace(adminEmail))
            {
                await BootstrapFromEmail(userManager, adminEmail);
            }
        }
        catch (Exception ex) when (ex is not OperationCanceledException && ex is not TaskCanceledException)
        {
            LogBootstrapTempFailure("startup", ex.Message);
        }
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;

    private async Task SeedInstanceAdminRole(RoleManager<IdentityRole<Guid>> roleManager)
    {
        if (!await roleManager.RoleExistsAsync("InstanceAdmin"))
        {
            await roleManager.CreateAsync(new IdentityRole<Guid>("InstanceAdmin"));
            LogRoleCreated();
        }
    }

    private async Task BootstrapFromEmail(UserManager<User> userManager, string email)
    {
        var user = await userManager.FindByEmailAsync(email);
        if (user is null)
        {
            user = new User
            {
                UserName = email,
                Email = email,
                DisplayName = "Instance Admin",
                State = AccountState.PendingVerification,
            };

            var result = await userManager.CreateAsync(user);
            if (!result.Succeeded)
            {
                LogBootstrapCreateFailed(email, result.Errors);
                return;
            }
        }

        var roleResult = await userManager.AddToRoleAsync(user, "InstanceAdmin");
        if (roleResult.Succeeded)
        {
            LogBootstrapSucceeded(email, user.Id);
        }
        else
        {
            LogBootstrapRoleFailed(email, roleResult.Errors);
        }
    }

    public static bool IsFirstUserAdminEnabled(IConfiguration configuration)
    {
        var value = configuration[AllowFirstUserAdminKey];
        return string.Equals(value, "true", StringComparison.OrdinalIgnoreCase);
    }

    [LoggerMessage(EventId = 100, Level = LogLevel.Information,
        Message = "Bootstrap skipped: no admin email or token configured")]
    private partial void LogBootstrapSkipped();

    [LoggerMessage(EventId = 101, Level = LogLevel.Information,
        Message = "InstanceAdmin role does not exist and will be created")]
    private partial void LogRoleCreated();

    [LoggerMessage(EventId = 102, Level = LogLevel.Information,
        Message = "InstanceAdmin already exists; bootstrap is one-shot (FR-009c)")]
    private partial void LogAdminAlreadyExists();

    [LoggerMessage(EventId = 103, Level = LogLevel.Information,
        Message = "Bootstrap succeeded: elevated {Email} (UserId={UserId}) to InstanceAdmin")]
    private partial void LogBootstrapSucceeded(string email, Guid userId);

    [LoggerMessage(EventId = 104, Level = LogLevel.Error,
        Message = "Bootstrap user creation failed for {Email}: {Errors}")]
    private partial void LogBootstrapCreateFailed(string email, IEnumerable<IdentityError> errors);

    [LoggerMessage(EventId = 105, Level = LogLevel.Error,
        Message = "Bootstrap role assignment failed for {Email}: {Errors}")]
    private partial void LogBootstrapRoleFailed(string email, IEnumerable<IdentityError> errors);

    [LoggerMessage(EventId = 106, Level = LogLevel.Warning,
        Message = "Bootstrap {Phase} temporarily unavailable (will retry on next restart): {Reason}")]
    private partial void LogBootstrapTempFailure(string phase, string reason);
}
