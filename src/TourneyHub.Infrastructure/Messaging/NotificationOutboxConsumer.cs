using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using TourneyHub.Application.Abstractions;
using TourneyHub.Application.Notifications;
using TourneyHub.Domain.Common;
using TourneyHub.Domain.Platform;
using TourneyHub.Infrastructure.Persistence;

namespace TourneyHub.Infrastructure.Messaging;

internal sealed partial class NotificationOutboxConsumer : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly IEnumerable<INotificationChannel> _channels;
    private readonly ILogger<NotificationOutboxConsumer> _logger;
    private readonly TimeSpan _pollingInterval = TimeSpan.FromSeconds(5);
    private readonly TimeSpan _delayOnEmpty = TimeSpan.FromSeconds(15);
    private const int MaxRetries = 3;

    private static readonly HashSet<string> NotifiableEventTypes =
    [
        "TourneyHub.Domain.Identity.Events.UserRegisteredEvent",
        "TourneyHub.Domain.Identity.Events.PasswordResetRequestedEvent",
        "TourneyHub.Domain.Identity.Events.InvitationCreatedEvent",
    ];

    public NotificationOutboxConsumer(
        IServiceScopeFactory scopeFactory,
        IEnumerable<INotificationChannel> channels,
        ILogger<NotificationOutboxConsumer> logger)
    {
        _scopeFactory = scopeFactory;
        _channels = channels;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        LogStarted(_pollingInterval.TotalSeconds);

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var processed = await ProcessPendingMessagesAsync(stoppingToken);
                var delay = processed == 0 ? _delayOnEmpty : _pollingInterval;
                await Task.Delay(delay, stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                LogPollingError(ex);
                await Task.Delay(_pollingInterval, stoppingToken);
            }
        }

        LogStopped();
    }

    private async Task<int> ProcessPendingMessagesAsync(CancellationToken cancellationToken)
    {
        await using var scope = _scopeFactory.CreateAsyncScope();
        var db = scope.ServiceProvider.GetRequiredService<TourneyHubDbContext>();
        var templateRenderer = scope.ServiceProvider.GetRequiredService<Notifications.LiquidTemplateRenderer>();

        var messages = await db.Set<OutboxMessage>()
            .Where(m => m.PublishedAt == null && m.RetryCount < MaxRetries)
            .OrderBy(m => m.OccurredAt)
            .Take(50)
            .ToListAsync(cancellationToken);

        if (messages.Count == 0) return 0;

        var notifiable = messages.Where(m => NotifiableEventTypes.Contains(m.EventType)).ToList();
        if (notifiable.Count == 0)
        {
            foreach (var m in messages) m.MarkPublished();
            await db.SaveChangesAsync(cancellationToken);
            return messages.Count;
        }

        var processed = 0;
        foreach (var message in notifiable)
        {
            if (await TryDispatchAsync(message, db, templateRenderer, cancellationToken))
            {
                processed++;
            }
        }

        if (processed > 0)
        {
            await db.SaveChangesAsync(cancellationToken);
        }

        return processed;
    }

    private async Task<bool> TryDispatchAsync(
        OutboxMessage message,
        TourneyHubDbContext db,
        Notifications.LiquidTemplateRenderer renderer,
        CancellationToken ct)
    {
        try
        {
            var notification = await MapToNotificationAsync(message, renderer, ct);
            if (notification is null)
            {
                message.MarkPublished();
                return true;
            }

            var alreadySent = await db.Set<SentNotification>()
                .AnyAsync(s => s.OutboxMessageId == message.Id && s.Recipient == notification.Recipient, ct);

            if (alreadySent)
            {
                LogIdempotentSkip(message.Id, notification.Recipient, message.EventType);
                message.MarkPublished();
                return true;
            }

            var sent = false;
            foreach (var channel in _channels)
            {
                await channel.SendAsync(notification, ct);
                sent = true;
            }

            if (sent)
            {
                db.Set<SentNotification>().Add(new SentNotification(
                    message.Id, notification.Recipient, notification.Subject));
                message.MarkPublished();
                LogPublished(message.Id, message.EventType);
            }

            return sent;
        }
        catch (Exception ex)
        {
            message.IncrementRetry();
            LogDispatchFailed(ex, message.Id, message.EventType, message.RetryCount, MaxRetries);
            return false;
        }
    }

    private static async Task<Notification?> MapToNotificationAsync(
        OutboxMessage message,
        Notifications.LiquidTemplateRenderer renderer,
        CancellationToken ct)
    {
        return message.EventType switch
        {
            "TourneyHub.Domain.Identity.Events.UserRegisteredEvent" =>
                await MapUserRegistered(message, renderer, ct),
            "TourneyHub.Domain.Identity.Events.PasswordResetRequestedEvent" =>
                await MapPasswordReset(message, renderer, ct),
            "TourneyHub.Domain.Identity.Events.InvitationCreatedEvent" =>
                await MapInvitationCreated(message, renderer, ct),
            _ => null,
        };
    }

    private static async Task<Notification?> MapUserRegistered(
        OutboxMessage message, Notifications.LiquidTemplateRenderer renderer, CancellationToken ct)
    {
        using var doc = JsonDocument.Parse(message.Payload);
        var root = doc.RootElement;
        var email = root.GetProperty("email").GetString()!;
        var displayName = root.GetProperty("displayName").GetString() ?? email;
        var token = root.GetProperty("verificationToken").GetString()!;

        var model = new { DisplayName = displayName, VerificationLink = $"https://tourneyhub.dev/verify-email?email={Uri.EscapeDataString(email)}&token={Uri.EscapeDataString(token)}" };
        var body = await renderer.RenderAsync("UserRegistered", model, ct);

        return new Notification
        {
            OrganizationId = Guid.Empty,
            Recipient = email,
            Subject = "Verify your email — TourneyHub",
            Body = body,
            Category = NotificationCategory.Transactional,
        };
    }

    private static async Task<Notification?> MapPasswordReset(
        OutboxMessage message, Notifications.LiquidTemplateRenderer renderer, CancellationToken ct)
    {
        using var doc = JsonDocument.Parse(message.Payload);
        var root = doc.RootElement;
        var email = root.GetProperty("email").GetString()!;
        var token = root.GetProperty("resetToken").GetString()!;

        var model = new { ResetLink = $"https://tourneyhub.dev/reset-password?email={Uri.EscapeDataString(email)}&token={Uri.EscapeDataString(token)}" };
        var body = await renderer.RenderAsync("PasswordReset", model, ct);

        return new Notification
        {
            OrganizationId = Guid.Empty,
            Recipient = email,
            Subject = "Password reset — TourneyHub",
            Body = body,
            Category = NotificationCategory.Transactional,
        };
    }

    private static async Task<Notification?> MapInvitationCreated(
        OutboxMessage message, Notifications.LiquidTemplateRenderer renderer, CancellationToken ct)
    {
        using var doc = JsonDocument.Parse(message.Payload);
        var root = doc.RootElement;
        var email = root.GetProperty("email").GetString()!;
        var scopeType = root.GetProperty("scopeType").GetString()!;
        var role = root.GetProperty("role").GetString()!;

        var model = new
        {
            ScopeType = scopeType,
            ScopeName = root.GetProperty("scopeId").GetString() ?? scopeType,
            Role = role,
            InvitationLink = $"https://tourneyhub.dev/invitations/{root.GetProperty("invitationId").GetString()}",
        };
        var body = await renderer.RenderAsync("InvitationCreated", model, ct);

        return new Notification
        {
            OrganizationId = Guid.Empty,
            Recipient = email,
            Subject = $"You have been invited to a {scopeType} — TourneyHub",
            Body = body,
            Category = NotificationCategory.Transactional,
        };
    }

    [LoggerMessage(EventId = 1, Level = LogLevel.Information, Message = "NotificationOutboxConsumer started. Polling every {Interval}s")]
    private partial void LogStarted(double interval);

    [LoggerMessage(EventId = 2, Level = LogLevel.Information, Message = "NotificationOutboxConsumer stopped")]
    private partial void LogStopped();

    [LoggerMessage(EventId = 3, Level = LogLevel.Error, Message = "NotificationOutboxConsumer error during polling cycle")]
    private partial void LogPollingError(Exception ex);

    [LoggerMessage(EventId = 4, Level = LogLevel.Information, Message = "Outbox message {Id} ({EventType}) already sent to {Recipient} — idempotent skip")]
    private partial void LogIdempotentSkip(Guid id, string recipient, string eventType);

    [LoggerMessage(EventId = 5, Level = LogLevel.Debug, Message = "Outbox message {Id} ({EventType}) published successfully")]
    private partial void LogPublished(Guid id, string eventType);

    [LoggerMessage(EventId = 6, Level = LogLevel.Warning, Message = "Failed to dispatch outbox message {Id} ({EventType}) — attempt {Attempt}/{Max}")]
    private partial void LogDispatchFailed(Exception ex, Guid id, string eventType, int attempt, int max);
}
