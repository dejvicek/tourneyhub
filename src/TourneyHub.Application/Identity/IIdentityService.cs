using TourneyHub.Domain.Identity;

namespace TourneyHub.Application.Identity;

public interface IIdentityService
{
    Task<RegisterUserResult> RegisterAsync(RegisterUserCommand command, CancellationToken cancellationToken = default);

    Task<TokenPairDto> LoginAsync(LoginUserCommand command, CancellationToken cancellationToken = default);

    Task<bool> VerifyEmailAsync(string email, string token, CancellationToken cancellationToken = default);

    Task SendPasswordResetTokenAsync(string email, CancellationToken cancellationToken = default);

    Task<bool> ResetPasswordAsync(string email, string token, string newPassword, CancellationToken cancellationToken = default);
}
