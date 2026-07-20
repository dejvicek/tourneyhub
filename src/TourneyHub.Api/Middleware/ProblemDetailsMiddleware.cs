using System.Net.Mime;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using TourneyHub.Application.Common;

namespace TourneyHub.Api.Middleware;

internal sealed partial class ProblemDetailsMiddleware
{
    private readonly RequestDelegate _next;
    private readonly ILogger<ProblemDetailsMiddleware> _logger;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };

    public ProblemDetailsMiddleware(RequestDelegate next, ILogger<ProblemDetailsMiddleware> logger)
    {
        _next = next;
        _logger = logger;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        try
        {
            await _next(context);
        }
        catch (DbUpdateConcurrencyException ex)
        {
            LogProblem(ex, ErrorCodes.ConcurrencyConflict, 409, "The resource was modified by another request.");
            await WriteProblem(context, 409, ErrorCodes.ConcurrencyConflict,
                "The resource was modified by another request. Reload the latest version and retry.");
        }
        catch (InvalidOperationException ex) when (IsNoTenantError(ex))
        {
            LogProblem(ex, ErrorCodes.NoTenantResolved, 400, "No organization resolved.");
            await WriteProblem(context, 400, ErrorCodes.NoTenantResolved,
                "No organization resolved for the current scope.");
        }
        catch (InvalidOperationException ex) when (IsCrossTenantError(ex))
        {
            LogProblem(ex, ErrorCodes.CrossTenantAccess, 403, "Cross-tenant access blocked.");
            await WriteProblem(context, 403, ErrorCodes.CrossTenantAccess,
                "Access to another organization's resources is forbidden.");
        }
        catch (Exception ex)
        {
            LogProblem(ex, ErrorCodes.UnknownError, 500, "An unexpected error occurred.");
            await WriteProblem(context, 500, ErrorCodes.UnknownError,
                "An unexpected error occurred.");
        }
    }

    [LoggerMessage(EventId = 1, Level = LogLevel.Error, Message = "Problem {Code} ({Status}): {Detail}")]
    private partial void LogProblem(Exception ex, string code, int status, string detail);

    private static Task WriteProblem(HttpContext context, int status, string code, string detail)
    {
        context.Response.StatusCode = status;
        context.Response.ContentType = MediaTypeNames.Application.ProblemJson;

        var problem = new
        {
            type = $"https://tourneyhub.dev/errors/{code}",
            title = GetTitleForStatus(status),
            status,
            detail,
            code,
            instance = context.Request.Path,
            traceId = context.TraceIdentifier,
        };

        return context.Response.WriteAsync(JsonSerializer.Serialize(problem, JsonOptions));
    }

    private static string GetTitleForStatus(int status) => status switch
    {
        400 => "Bad Request",
        401 => "Unauthorized",
        403 => "Forbidden",
        404 => "Not Found",
        409 => "Conflict",
        410 => "Gone",
        422 => "Unprocessable Entity",
        428 => "Precondition Required",
        429 => "Too Many Requests",
        500 => "Internal Server Error",
        501 => "Not Implemented",
        _ => "Error",
    };

    private static bool IsNoTenantError(InvalidOperationException ex) =>
        ex.Message.Contains("no organization resolved", StringComparison.OrdinalIgnoreCase);

    private static bool IsCrossTenantError(InvalidOperationException ex) =>
        ex.Message.Contains("different organization", StringComparison.OrdinalIgnoreCase);
}