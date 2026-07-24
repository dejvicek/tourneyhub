using System.Net.Mime;
using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Routing;
using TourneyHub.Application.Common;
using TourneyHub.Application.Identity;
using TourneyHub.Infrastructure.Identity;

namespace TourneyHub.Api.Extensions;

internal static class AuthEndpoints
{
    public static RouteGroupBuilder MapAuthEndpoints(this IEndpointRouteBuilder app)
    {
        var auth = app.MapGroup("/api/v1/auth");

        auth.MapPost("/register", RegisterAsync)
            .RequireRateLimiting("auth")
            .WithOpenApi();

        auth.MapPost("/login", LoginAsync)
            .RequireRateLimiting("auth")
            .WithOpenApi();

        auth.MapPost("/verify-email", VerifyEmailAsync)
            .RequireRateLimiting("auth")
            .WithOpenApi();

        auth.MapPost("/password-reset", PasswordResetAsync)
            .RequireRateLimiting("auth")
            .WithOpenApi();

        return auth;
    }

    private static async Task<IResult> RegisterAsync(
        [FromBody] RegisterUserCommand command,
        IIdentityService identityService,
        CancellationToken ct)
    {
        try
        {
            var result = await identityService.RegisterAsync(command, ct);
            return ResultHelper.JsonCreated($"/auth/users/{result.UserId}",
                new RegistrationResponse(result.UserId, result.State.ToString()));
        }
        catch (IdentityOperationException ex)
        {
            var codes = ex.ErrorCodes.ToList();
            if (codes.Contains("DuplicateEmail") || codes.Contains("DuplicateUserName"))
            {
                return WriteProblem(409, ErrorCodes.EmailAlreadyRegistered, "Email is already registered.");
            }

            return WriteProblem(422, ErrorCodes.ValidationFailed, ex.Message);
        }
    }

    private static async Task<IResult> LoginAsync(
        [FromBody] LoginUserCommand command,
        IIdentityService identityService,
        CancellationToken ct)
    {
        try
        {
            var tokenPair = await identityService.LoginAsync(command, ct);
            return ResultHelper.Json(tokenPair, MediaTypeNames.Application.Json, 200);
        }
        catch (IdentityOperationException ex)
        {
            var codes = ex.ErrorCodes.ToList();
            if (codes.Contains("account_suspended") || codes.Contains("account_banned"))
            {
                return WriteProblem(403, codes[0], ex.Message);
            }

            return WriteProblem(401, ErrorCodes.InvalidCredentials, ex.Message);
        }
    }

    private static async Task<IResult> VerifyEmailAsync(
        [FromBody] VerifyEmailRequest request,
        IIdentityService identityService,
        CancellationToken ct)
    {
        var result = await identityService.VerifyEmailAsync(request.Email, request.Token, ct);
        if (!result)
        {
            return WriteProblem(410, ErrorCodes.TokenExpired, "Verification token is invalid or expired.");
        }

        return Results.NoContent();
    }

    private static async Task<IResult> PasswordResetAsync(
        [FromBody] PasswordResetRequestDto request,
        IIdentityService identityService,
        CancellationToken ct)
    {
        var isResetPhase = !string.IsNullOrEmpty(request.Token) && !string.IsNullOrEmpty(request.NewPassword);

        if (isResetPhase)
        {
            await identityService.ResetPasswordAsync(request.Email!, request.Token!, request.NewPassword!, ct);
        }
        else if (!string.IsNullOrEmpty(request.Email))
        {
            await identityService.SendPasswordResetTokenAsync(request.Email, ct);
        }

        return Results.Accepted();
    }

    private static IResult WriteProblem(int status, string code, string detail)
    {
        var problem = new ProblemResponse(
            Type: $"https://tourneyhub.dev/errors/{code}",
            Title: status switch
            {
                401 => "Unauthorized",
                403 => "Forbidden",
                409 => "Conflict",
                410 => "Gone",
                422 => "Unprocessable Entity",
                _ => "Error",
            },
            Status: status,
            Detail: detail,
            Code: code);

        return ResultHelper.Json(problem, "application/problem+json", status);
    }
}

internal sealed record VerifyEmailRequest(string Email, string Token);

internal sealed record PasswordResetRequestDto(string? Email, string? Token, string? NewPassword);

internal sealed record RegistrationResponse(Guid UserId, string State);

internal sealed record ProblemResponse(string Type, string Title, int Status, string Detail, string Code);

internal static class ResultHelper
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };

    internal static IResult Json(object? value, string contentType, int statusCode) => Results.Text(
        JsonSerializer.Serialize(value, JsonOptions),
        contentType,
        statusCode: statusCode);

    internal static IResult JsonCreated(string uri, object? value) => Results.Text(
        JsonSerializer.Serialize(value, JsonOptions),
        MediaTypeNames.Application.Json,
        statusCode: 201);
}