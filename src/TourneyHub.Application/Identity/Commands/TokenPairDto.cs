namespace TourneyHub.Application.Identity;

public sealed record TokenPairDto(
    string AccessToken,
    string RefreshToken,
    int ExpiresIn);
