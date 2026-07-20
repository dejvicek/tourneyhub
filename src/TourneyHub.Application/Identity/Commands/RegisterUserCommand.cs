namespace TourneyHub.Application.Identity;

public sealed record RegisterUserCommand(
    string Email,
    string Password,
    string? DisplayName,
    string ConsentPolicyVersion);
