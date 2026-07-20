using Microsoft.AspNetCore.Identity;
using Microsoft.Extensions.Logging;
using TourneyHub.Application.Identity;
using TourneyHub.Domain.Identity;

namespace TourneyHub.Infrastructure.Identity;

internal sealed partial class IdentityService : IIdentityService
{
    private readonly UserManager<User> _userManager;
    private readonly SignInManager<User> _signInManager;
    private readonly JwtTokenService _jwtTokenService;
    private readonly ILogger<IdentityService> _logger;

    public IdentityService(
        UserManager<User> userManager,
        SignInManager<User> signInManager,
        JwtTokenService jwtTokenService,
        ILogger<IdentityService> logger)
    {
        _userManager = userManager;
        _signInManager = signInManager;
        _jwtTokenService = jwtTokenService;
        _logger = logger;
    }

    public async Task<RegisterUserResult> RegisterAsync(
        RegisterUserCommand command, CancellationToken cancellationToken = default)
    {
        var user = new User
        {
            UserName = command.Email,
            Email = command.Email,
            DisplayName = command.DisplayName,
            State = AccountState.PendingVerification,
        };

        var result = await _userManager.CreateAsync(user, command.Password);
        if (!result.Succeeded)
        {
            var errors = result.Errors.Select(e => e.Description);
            throw new IdentityOperationException(
                string.Join("; ", errors), result.Errors.Select(e => e.Code));
        }

        LogUserRegistered(user.Id);

        return new RegisterUserResult(user.Id, user.State);
    }

    public async Task<TokenPairDto> LoginAsync(
        LoginUserCommand command, CancellationToken cancellationToken = default)
    {
        var user = await _userManager.FindByEmailAsync(command.Email);
        if (user is null)
        {
            throw new IdentityOperationException("Invalid credentials.", ["invalid_credentials"]);
        }

        if (user.State == AccountState.Suspended || user.State == AccountState.Banned)
        {
            throw new IdentityOperationException(
                $"Account is {user.State.ToString().ToLowerInvariant()}.",
                [user.State == AccountState.Suspended ? "account_suspended" : "account_banned"]);
        }

        var result = await _signInManager.CheckPasswordSignInAsync(user, command.Password, lockoutOnFailure: true);
        if (!result.Succeeded)
        {
            throw new IdentityOperationException("Invalid credentials.", ["invalid_credentials"]);
        }

        user.LastLoginAt = DateTime.UtcNow;
        await _userManager.UpdateAsync(user);

        LogUserLoggedIn(user.Id);

        return _jwtTokenService.GenerateTokenPair(user);
    }

    public async Task<bool> VerifyEmailAsync(
        string email, string token, CancellationToken cancellationToken = default)
    {
        var user = await _userManager.FindByEmailAsync(email);
        if (user is null)
        {
            return false;
        }

        var result = await _userManager.ConfirmEmailAsync(user, token);
        if (!result.Succeeded)
        {
            return false;
        }

        user.State = AccountState.Active;
        await _userManager.UpdateAsync(user);

        LogEmailVerified(user.Id);
        return true;
    }

    public async Task SendPasswordResetTokenAsync(
        string email, CancellationToken cancellationToken = default)
    {
        var user = await _userManager.FindByEmailAsync(email);
        if (user is null)
        {
            LogPasswordResetNonExistentEmail(email);
            return;
        }

        var token = await _userManager.GeneratePasswordResetTokenAsync(user);
        LogPasswordResetTokenGenerated(user.Id, token);
    }

    public async Task<bool> ResetPasswordAsync(
        string email, string token, string newPassword, CancellationToken cancellationToken = default)
    {
        var user = await _userManager.FindByEmailAsync(email);
        if (user is null)
        {
            return false;
        }

        var result = await _userManager.ResetPasswordAsync(user, token, newPassword);
        if (result.Succeeded)
        {
            LogPasswordReset(user.Id);
        }

        return result.Succeeded;
    }

    [LoggerMessage(EventId = 1, Level = LogLevel.Information, Message = "User {UserId} registered")]
    private partial void LogUserRegistered(Guid userId);

    [LoggerMessage(EventId = 2, Level = LogLevel.Information, Message = "User {UserId} logged in")]
    private partial void LogUserLoggedIn(Guid userId);

    [LoggerMessage(EventId = 3, Level = LogLevel.Information, Message = "User {UserId} verified email")]
    private partial void LogEmailVerified(Guid userId);

    [LoggerMessage(EventId = 4, Level = LogLevel.Information,
        Message = "Password reset requested for non-existent email: {Email}")]
    private partial void LogPasswordResetNonExistentEmail(string email);

    [LoggerMessage(EventId = 5, Level = LogLevel.Warning,
        Message = "Password reset token generated for user {UserId}: {Token}")]
    private partial void LogPasswordResetTokenGenerated(Guid userId, string token);

    [LoggerMessage(EventId = 6, Level = LogLevel.Information, Message = "User {UserId} reset password")]
    private partial void LogPasswordReset(Guid userId);
}

public class IdentityOperationException : Exception
{
    public IEnumerable<string> ErrorCodes { get; }

    public IdentityOperationException(string message, IEnumerable<string> errorCodes)
        : base(message)
    {
        ErrorCodes = errorCodes;
    }
}
