using System.Text.Json;
using TourneyHub.Application.Tenancy;
using TourneyHub.Infrastructure.Persistence;

namespace TourneyHub.Api.Middleware;

internal sealed class IdempotencyMiddleware
{
    private readonly RequestDelegate _next;

    private const string IdempotencyKeyHeader = "Idempotency-Key";

    private static readonly HashSet<string> IdempotentMethods = new(StringComparer.OrdinalIgnoreCase)
    {
        "POST",
    };

    public IdempotencyMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        if (!IdempotentMethods.Contains(context.Request.Method)
            || !context.Request.Headers.TryGetValue(IdempotencyKeyHeader, out var values))
        {
            await _next(context);
            return;
        }

        var key = values.FirstOrDefault();
        if (string.IsNullOrWhiteSpace(key))
        {
            await _next(context);
            return;
        }

        var tenantContext = context.RequestServices.GetRequiredService<ITenantContext>();
        if (!tenantContext.HasTenant)
        {
            await _next(context);
            return;
        }

        context.Request.EnableBuffering();
        var body = string.Empty;
        if (context.Request.ContentLength > 0)
        {
            using var reader = new StreamReader(context.Request.Body, leaveOpen: true);
            body = await reader.ReadToEndAsync();
            context.Request.Body.Position = 0;
        }

        var requestHash = IdempotencyService.ComputeRequestHash(context.Request.Method, context.Request.Path, body);

        var db = context.RequestServices.GetRequiredService<TourneyHubDbContext>();
        var service = new IdempotencyService(db);

        var result = await service.CheckAndStoreAsync(tenantContext.OrganizationId, key, requestHash, context.RequestAborted);

        if (result.IsReplay)
        {
            context.Response.StatusCode = result.ResponseStatusCode;
            context.Response.ContentType = result.ResponseContentType;
            await context.Response.Body.WriteAsync(result.ResponseBody, context.RequestAborted);
            return;
        }

        if (result.IsConflict)
        {
            context.Response.StatusCode = 422;
            context.Response.ContentType = "application/problem+json";
            var problem = JsonSerializer.Serialize(new
            {
                type = "https://tourneyhub.dev/errors/idempotency_key_conflict",
                title = "Unprocessable Entity",
                status = 422,
                detail = "An idempotency key was reused with a different request body.",
                code = "idempotency_key_conflict",
            });
            await context.Response.WriteAsync(problem, context.RequestAborted);
            return;
        }

        var originalBody = context.Response.Body;
        using var buffer = new MemoryStream();
        context.Response.Body = buffer;

        await _next(context);

        buffer.Position = 0;
        var responseBytes = buffer.ToArray();
        await originalBody.WriteAsync(responseBytes, context.RequestAborted);
        context.Response.Body = originalBody;

        await service.StoreResponseAsync(
            tenantContext.OrganizationId,
            key,
            requestHash,
            context.Response.StatusCode,
            context.Response.ContentType ?? "application/json",
            responseBytes,
            context.RequestAborted);
    }
}