using MailKit.Net.Smtp;
using MailKit.Security;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Options;
using TourneyHub.Infrastructure.Notifications;

namespace TourneyHub.Api.Health;

internal sealed class SmtpHealthCheck : IHealthCheck
{
    private readonly EmailOptions _options;

    public SmtpHealthCheck(IOptions<EmailOptions> options)
    {
        _options = options.Value;
    }

    public async Task<HealthCheckResult> CheckHealthAsync(
        HealthCheckContext context, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(_options.SmtpHost))
        {
            return HealthCheckResult.Unhealthy("SMTP host is not configured.");
        }

        try
        {
            using var client = new SmtpClient();
            await client.ConnectAsync(
                _options.SmtpHost,
                _options.SmtpPort,
                _options.UseSsl ? SecureSocketOptions.SslOnConnect : SecureSocketOptions.StartTlsWhenAvailable,
                cancellationToken);

            await client.DisconnectAsync(true, cancellationToken);

            return HealthCheckResult.Healthy($"SMTP reachable at {_options.SmtpHost}:{_options.SmtpPort}");
        }
        catch (Exception ex)
        {
            return HealthCheckResult.Unhealthy(
                $"SMTP connectivity check failed: {ex.Message}",
                ex);
        }
    }
}
