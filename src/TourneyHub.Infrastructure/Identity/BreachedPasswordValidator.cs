using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Identity;
using Microsoft.Extensions.Logging;

namespace TourneyHub.Infrastructure.Identity;

internal sealed partial class BreachedPasswordValidator<TUser> : IPasswordValidator<TUser>
    where TUser : class
{
    private readonly HttpClient _httpClient;
    private readonly ILogger<BreachedPasswordValidator<TUser>> _logger;

    private const string HibpApiBase = "https://api.pwnedpasswords.com/range/";

    public BreachedPasswordValidator(HttpClient httpClient, ILogger<BreachedPasswordValidator<TUser>> logger)
    {
        _httpClient = httpClient;
        _logger = logger;
    }

    public async Task<IdentityResult> ValidateAsync(
        UserManager<TUser> manager, TUser user, string? password)
    {
        if (string.IsNullOrEmpty(password))
        {
            return IdentityResult.Failed(new IdentityError
            {
                Code = "PasswordRequired",
                Description = "Password is required.",
            });
        }

        if (password.Length < 12)
        {
            return IdentityResult.Failed(new IdentityError
            {
                Code = "PasswordTooShort",
                Description = "Password must be at least 12 characters.",
            });
        }

        if (await IsBreachedAsync(password))
        {
            LogBreachedPassword();
            return IdentityResult.Failed(new IdentityError
            {
                Code = "BreachedPassword",
                Description = "This password has appeared in known data breaches and cannot be used.",
            });
        }

        return IdentityResult.Success;
    }

    private async Task<bool> IsBreachedAsync(string password)
    {
#pragma warning disable CA5350 // SHA1 is required by HIBP k-anonymity protocol
        var sha1 = SHA1.HashData(Encoding.UTF8.GetBytes(password));
#pragma warning restore CA5350
        var hash = Convert.ToHexString(sha1);
        var prefix = hash[..5];
        var suffix = hash[5..];

        try
        {
            var response = await _httpClient.GetStringAsync($"{HibpApiBase}{prefix}");
            return response.Split('\n')
                .Any(line => line.StartsWith(suffix, StringComparison.OrdinalIgnoreCase));
        }
        catch (Exception ex)
        {
            LogHibpUnavailable(ex);
            return false;
        }
    }

    [LoggerMessage(EventId = 1, Level = LogLevel.Warning,
        Message = "User attempted to register with a breached password")]
    private partial void LogBreachedPassword();

    [LoggerMessage(EventId = 2, Level = LogLevel.Warning,
        Message = "HIBP API unavailable; breached password check skipped")]
    private partial void LogHibpUnavailable(Exception ex);
}
