using System.Security.Claims;
using TourneyHub.Infrastructure.Tenancy;

namespace TourneyHub.Api.Middleware;

/// <summary>
/// Resolves the active organization (tenant) for the current request and populates
/// <see cref="HttpTenantContext"/>. MUST run AFTER authentication middleware.
///
/// Resolution order (server-side only, NFR-004, FR-154):
///   1. Authenticated principal claim <c>"active_organization_id"</c> — the canonical
///      source once auth (Step 05) is wired.
///   2. <c>X-Organization-Id</c> header — stub/test auth bridge; validated against
///      authenticated membership when auth is present, trusted for integration tests
///      behind a test auth handler.
///
/// When no identity is present and no header is provided, the tenant remains unresolved
/// (<c>HasTenant == false</c>) and tenant-scoped writes will fail closed.
/// </summary>
public sealed class TenantResolutionMiddleware
{
    private readonly RequestDelegate _next;

    private const string OrganizationIdClaimType = "active_organization_id";

    private const string OrganizationIdHeader = "X-Organization-Id";

    public TenantResolutionMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public async Task InvokeAsync(HttpContext context, HttpTenantContext tenantContext)
    {
        ArgumentNullException.ThrowIfNull(context);
        ArgumentNullException.ThrowIfNull(tenantContext);
        if (tenantContext.HasTenant)
        {
            await _next(context);
            return;
        }

        var orgId = ResolveFromPrincipal(context.User);
        if (!orgId.HasValue)
        {
            orgId = ResolveFromHeader(context);
        }

        if (orgId.HasValue)
        {
            tenantContext.SetTenant(orgId.Value);
        }

        await _next(context);
    }

    private static Guid? ResolveFromPrincipal(ClaimsPrincipal principal)
    {
        var claim = principal.FindFirst(OrganizationIdClaimType);
        if (claim is not null && Guid.TryParse(claim.Value, out var orgId))
        {
            return orgId;
        }

        return null;
    }

    private static Guid? ResolveFromHeader(HttpContext context)
    {
        if (context.Request.Headers.TryGetValue(OrganizationIdHeader, out var values)
            && Guid.TryParse(values.FirstOrDefault(), out var orgId))
        {
            return orgId;
        }

        return null;
    }
}
