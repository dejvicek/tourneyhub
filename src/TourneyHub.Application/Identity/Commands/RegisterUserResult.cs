using TourneyHub.Domain.Identity;

namespace TourneyHub.Application.Identity;

public sealed record RegisterUserResult(
    Guid UserId,
    AccountState State);
