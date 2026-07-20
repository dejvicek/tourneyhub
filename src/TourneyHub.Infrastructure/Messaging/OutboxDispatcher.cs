using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using TourneyHub.Application.Abstractions;
using TourneyHub.Application.Notifications;
using TourneyHub.Domain.Common;
using TourneyHub.Infrastructure.Persistence;

namespace TourneyHub.Infrastructure.Messaging;

/// <summary>
/// Background service that polls the <c>outbox_messages</c> table for unpublished
/// domain events and dispatches them to registered <see cref="INotificationChannel"/>s.
/// At-least-once delivery per ADR-0001 §3; consumers must deduplicate.
/// </summary>
internal sealed partial class OutboxDispatcher : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly IEnumerable<INotificationChannel> _channels;
    private readonly ILogger<OutboxDispatcher> _logger;
    private readonly TimeSpan _pollingInterval = TimeSpan.FromSeconds(5);
    private readonly TimeSpan _delayOnEmpty = TimeSpan.FromSeconds(15);
    private const int MaxRetries = 3;

    public OutboxDispatcher(
        IServiceScopeFactory scopeFactory,
        IEnumerable<INotificationChannel> channels,
        ILogger<OutboxDispatcher> logger)
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

        var messages = await db.Set<OutboxMessage>()
            .Where(m => m.PublishedAt == null && m.RetryCount < MaxRetries)
            .OrderBy(m => m.OccurredAt)
            .Take(50)
            .ToListAsync(cancellationToken);

        if (messages.Count == 0)
        {
            return 0;
        }

        var processed = 0;
        foreach (var message in messages)
        {
            if (await TryDispatchAsync(message, cancellationToken))
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

    private async Task<bool> TryDispatchAsync(OutboxMessage message, CancellationToken cancellationToken)
    {
        try
        {
            var notification = DeserializeNotification(message);
            if (notification is null)
            {
                message.MarkPublished();
                LogCannotDeserialize(message.Id, message.EventType);
                return true;
            }

            var sent = false;
            foreach (var channel in _channels)
            {
                await channel.SendAsync(notification, cancellationToken);
                sent = true;
            }

            if (sent)
            {
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

    private static Notification? DeserializeNotification(OutboxMessage message)
    {
        try
        {
            return JsonSerializer.Deserialize<Notification>(message.Payload);
        }
        catch
        {
            return null;
        }
    }

    [LoggerMessage(EventId = 1, Level = LogLevel.Information, Message = "OutboxDispatcher started. Polling every {Interval}s")]
    private partial void LogStarted(double interval);

    [LoggerMessage(EventId = 2, Level = LogLevel.Information, Message = "OutboxDispatcher stopped")]
    private partial void LogStopped();

    [LoggerMessage(EventId = 3, Level = LogLevel.Error, Message = "OutboxDispatcher error during polling cycle")]
    private partial void LogPollingError(Exception ex);

    [LoggerMessage(EventId = 4, Level = LogLevel.Warning, Message = "Outbox message {Id} ({EventType}) could not be deserialized to Notification. Marking published anyway.")]
    private partial void LogCannotDeserialize(Guid id, string eventType);

    [LoggerMessage(EventId = 5, Level = LogLevel.Debug, Message = "Outbox message {Id} ({EventType}) published successfully")]
    private partial void LogPublished(Guid id, string eventType);

    [LoggerMessage(EventId = 6, Level = LogLevel.Warning, Message = "Failed to dispatch outbox message {Id} ({EventType}) — attempt {Attempt}/{Max}")]
    private partial void LogDispatchFailed(Exception ex, Guid id, string eventType, int attempt, int max);
}