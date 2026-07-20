using Microsoft.AspNetCore.Http;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using TourneyHub.Domain.Organizations;
using TourneyHub.Infrastructure.Persistence;

namespace TourneyHub.Api.Middleware;

internal sealed class SuspensionGuardMiddleware
{
    private static readonly HashSet<string> WriteMethods = new(StringComparer.OrdinalIgnoreCase)
    {
        "POST", "PUT", "PATCH", "DELETE",
    };

    private readonly RequestDelegate _next;

    public SuspensionGuardMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        if (!WriteMethods.Contains(context.Request.Method))
        {
            await _next(context);
            return;
        }

        var tenantHeader = context.Request.Headers["X-Organization-Id"].FirstOrDefault();
        if (string.IsNullOrWhiteSpace(tenantHeader) || !Guid.TryParse(tenantHeader, out var orgId))
        {
            await _next(context);
            return;
        }

        var db = context.RequestServices.GetRequiredService<TourneyHubDbContext>();

        var org = await db.Organizations
            .AsNoTracking()
            .FirstOrDefaultAsync(o => o.Id == orgId);

        if (org is not null && org.State == OrganizationState.Suspended)
        {
            context.Response.StatusCode = StatusCodes.Status403Forbidden;
            context.Response.ContentType = "application/problem+json";
            var problem = System.Text.Json.JsonSerializer.Serialize(new
            {
                type = "https://tourneyhub.dev/errors/organization_suspended",
                title = "Forbidden",
                status = 403,
                detail = "This organization is suspended. All write operations are blocked (BR-014).",
                code = "organization_suspended",
            });
            await context.Response.WriteAsync(problem);
            return;
        }

        await _next(context);
    }
}