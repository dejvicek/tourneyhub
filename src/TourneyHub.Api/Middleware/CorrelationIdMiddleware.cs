namespace TourneyHub.Api.Middleware;

internal sealed class CorrelationIdMiddleware
{
    private readonly RequestDelegate _next;

    private const string CorrelationIdHeader = "X-Correlation-Id";

    public CorrelationIdMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        if (!context.Request.Headers.TryGetValue(CorrelationIdHeader, out var values))
        {
            context.Request.Headers[CorrelationIdHeader] = Guid.NewGuid().ToString("N");
        }

        var correlationId = context.Request.Headers[CorrelationIdHeader].FirstOrDefault()!;

        context.Response.OnStarting(() =>
        {
            context.Response.Headers[CorrelationIdHeader] = correlationId;
            return Task.CompletedTask;
        });

        context.Items["CorrelationId"] = correlationId;

        await _next(context);
    }
}