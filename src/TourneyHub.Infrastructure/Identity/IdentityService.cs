using System.Text.Json;
using Microsoft.AspNetCore.Identity;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using TourneyHub.Application.Identity;
using TourneyHub.Domain.Common;
using TourneyHub.Domain.Identity;
using TourneyHub.Domain.Identity.Events;
using TourneyHub.Infrastructure.Persistence;

namespace TourneyHub.Infrastructure.Identity;

internal sealed partial class IdentityService : IIdentityService
{
    private readonly UserManager<User> _userManager;
    private readonly SignInManager<User> _signInManager;
    private readonly JwtTokenService _jwtTokenService;
    private readonly IConfiguration _configuration;
    private readonly TourneyHubDbContext _db;
    private readonly ILogger<IdentityService> _logger;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };

    public IdentityService(
        UserManager<User> userManager,
        SignInManager<User> signInManager,
        JwtTokenService jwtTokenService,
        IConfiguration configuration,
        TourneyHubDbContext db,
        ILogger<IdentityService> logger)
    {
        _userManager = userManager;
        _signInManager = signInManager;
        _jwtTokenService = jwtTokenService;
        _configuration = configuration;
        _db = db;
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

        var isFirstUser = !_userManager.Users.Any();
        var firstUserAdminEnabled = BootstrapService.IsFirstUserAdminEnabled(_configuration);

        await using var transaction = await _db.Database.BeginTransactionAsync(cancellationToken);

        try
        {
            var result = await _userManager.CreateAsync(user, command.Password);
            if (!result.Succeeded)
            {
                var errors = result.Errors.Select(e => e.Description);
                throw new IdentityOperationException(
                    string.Join("; ", errors), result.Errors.Select(e => e.Code));
            }

            if (isFirstUser && firstUserAdminEnabled)
            {
                var admins = await _userManager.GetUsersInRoleAsync("InstanceAdmin");
                if (admins.Count == 0)
                {
                    await _userManager.AddToRoleAsync(user, "InstanceAdmin");
                    LogFirstUserPromotedToAdmin(user.Id);
                }
            }

            var verificationToken = await _userManager.GenerateEmailConfirmationTokenAsync(user);
            var domainEvent = new UserRegisteredEvent(
                user.Id,
                user.Email!,
                user.DisplayName ?? user.Email!,
                verificationToken);

            var outboxMessage = new OutboxMessage(
                nameof(User),
                user.Id,
                0,
                domainEvent.GetType().FullName!,
                JsonSerializer.Serialize(domainEvent, domainEvent.GetType(), JsonOptions),
                domainEvent.OccurredAt);

            _db.OutboxMessages.Add(outboxMessage);
            await _db.SaveChangesAsync(cancellationToken);
            await transaction.CommitAsync(cancellationToken);
        }
        catch
        {
            await transaction.RollbackAsync(cancellationToken);
            throw;
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
        var domainEvent = new PasswordResetRequestedEvent(
            user.Id,
            user.Email!,
            token);

        var outboxMessage = new OutboxMessage(
            nameof(User),
            user.Id,
            0,
            domainEvent.GetType().FullName!,
            JsonSerializer.Serialize(domainEvent, domainEvent.GetType(), JsonOptions),
            domainEvent.OccurredAt);

        _db.OutboxMessages.Add(outboxMessage);
        await _db.SaveChangesAsync(cancellationToken);

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

    [LoggerMessage(EventId = 7, Level = LogLevel.Information,
        Message = "First-registered user {UserId} auto-promoted to InstanceAdmin (FR-009b)")]
    private partial void LogFirstUserPromotedToAdmin(Guid userId);
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
