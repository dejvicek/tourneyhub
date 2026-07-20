using System.Reflection;
using Fluid;
using Microsoft.Extensions.Logging;

namespace TourneyHub.Infrastructure.Notifications;

internal sealed partial class LiquidTemplateRenderer
{
    private static readonly Assembly Assembly = typeof(LiquidTemplateRenderer).Assembly;
    private const string TemplateNamespace = "TourneyHub.Infrastructure.Notifications.EmailTemplates";
    private readonly FluidParser _parser = new();
    private readonly ILogger<LiquidTemplateRenderer> _logger;

    public LiquidTemplateRenderer(ILogger<LiquidTemplateRenderer> logger)
    {
        _logger = logger;
    }

    public async Task<string> RenderAsync(string templateName, object model, CancellationToken ct = default)
    {
        var source = await LoadTemplateAsync(templateName, ct);
        if (source is null)
        {
            LogTemplateNotFound(templateName);
            return string.Empty;
        }

        if (!_parser.TryParse(source, out var template, out var error))
        {
            LogTemplateParseError(templateName, error);
            return source;
        }

        var context = new TemplateContext(model);
        return await template.RenderAsync(context);
    }

    private static Task<string?> LoadTemplateAsync(string templateName, CancellationToken ct)
    {
        var resourceName = $"{TemplateNamespace}.{templateName}.liquid";
        using var stream = Assembly.GetManifestResourceStream(resourceName);
        if (stream is null)
        {
            return Task.FromResult<string?>(null);
        }

        using var reader = new StreamReader(stream);
        return reader.ReadToEndAsync(ct)!;
    }

    [LoggerMessage(EventId = 1, Level = LogLevel.Warning, Message = "Email template '{TemplateName}' not found")]
    private partial void LogTemplateNotFound(string templateName);

    [LoggerMessage(EventId = 2, Level = LogLevel.Error, Message = "Failed to parse email template '{TemplateName}': {Error}")]
    private partial void LogTemplateParseError(string templateName, string error);
}
