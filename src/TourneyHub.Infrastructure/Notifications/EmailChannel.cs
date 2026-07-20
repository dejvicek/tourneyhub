using MailKit.Net.Smtp;
using MailKit.Security;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using MimeKit;
using TourneyHub.Application.Abstractions;
using TourneyHub.Application.Notifications;

namespace TourneyHub.Infrastructure.Notifications;

/// <summary>
/// SMTP-backed <see cref="INotificationChannel"/> for transactional email delivery.
/// For development: sends to Mailpit at localhost:1025 (no auth).
/// For production: configurable SMTP host/port/credentials (FR-142).
/// </summary>
internal sealed partial class EmailChannel : INotificationChannel
{
    private readonly EmailOptions _options;
    private readonly ILogger<EmailChannel> _logger;

    public string ChannelName => "email";

    public EmailChannel(IOptions<EmailOptions> options, ILogger<EmailChannel> logger)
    {
        _options = options.Value;
        _logger = logger;
    }

    public async Task SendAsync(Notification notification, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(notification);

        if (string.IsNullOrWhiteSpace(_options.SmtpHost))
        {
            LogNotConfigured(notification.Recipient, notification.Subject);
            return;
        }

        using var message = new MimeMessage();
        message.From.Add(new MailboxAddress(_options.SenderName, _options.SenderAddress));
        message.To.Add(new MailboxAddress(notification.Recipient, notification.Recipient));
        message.Subject = notification.Subject;
        message.Body = new TextPart("plain") { Text = notification.Body };

        using var client = new SmtpClient();
        try
        {
            await client.ConnectAsync(_options.SmtpHost, _options.SmtpPort,
                _options.UseSsl ? SecureSocketOptions.SslOnConnect : SecureSocketOptions.StartTlsWhenAvailable,
                cancellationToken);

            if (!string.IsNullOrWhiteSpace(_options.Username))
            {
                await client.AuthenticateAsync(_options.Username, _options.Password ?? string.Empty, cancellationToken);
            }

            await client.SendAsync(message, cancellationToken);
            await client.DisconnectAsync(true, cancellationToken);

            LogSent(notification.Recipient, notification.Subject, _options.SmtpHost, _options.SmtpPort);
        }
        catch (Exception ex)
        {
            LogSendFailed(ex, notification.Recipient, notification.Subject);
            throw;
        }
    }

    [LoggerMessage(EventId = 1, Level = LogLevel.Warning, Message = "EmailChannel not configured (missing SmtpHost). Skipping send to {Recipient} with subject \"{Subject}\"")]
    private partial void LogNotConfigured(string recipient, string subject);

    [LoggerMessage(EventId = 2, Level = LogLevel.Information, Message = "Email sent to {Recipient} with subject \"{Subject}\" via {Host}:{Port}")]
    private partial void LogSent(string recipient, string subject, string host, int port);

    [LoggerMessage(EventId = 3, Level = LogLevel.Error, Message = "Failed to send email to {Recipient} with subject \"{Subject}\"")]
    private partial void LogSendFailed(Exception ex, string recipient, string subject);
}

/// <summary>
/// Configuration for the SMTP email channel.
/// For dev: SmtpHost=localhost, SmtpPort=1025, no auth (Mailpit).
/// </summary>
public sealed class EmailOptions
{
    public const string Section = "Email";

    public string SmtpHost { get; set; } = "localhost";
    public int SmtpPort { get; set; } = 1025;
    public bool UseSsl { get; set; }
    public string SenderName { get; set; } = "TourneyHub";
    public string SenderAddress { get; set; } = "noreply@tourneyhub.local";
    public string? Username { get; set; }
    public string? Password { get; set; }
}