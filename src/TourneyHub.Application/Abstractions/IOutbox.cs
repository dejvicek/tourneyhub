namespace TourneyHub.Application.Abstractions;

using TourneyHub.Domain.Common;

/// <summary>
/// Port for enqueuing domain events into the transactional outbox.
/// The implementation MUST write to the outbox table in the same DB transaction
/// as the state change that produced the events (no dual-write).
/// </summary>
public interface IOutbox
{
    /// <summary>
    /// Enqueue a batch of domain events with their aggregate metadata.
    /// The caller is responsible for providing the correct aggregate type, ID, and version.
    /// </summary>
    Task EnqueueAsync(
        string aggregateType,
        Guid aggregateId,
        int aggregateVersion,
        IReadOnlyCollection<IDomainEvent> events,
        CancellationToken cancellationToken = default);
}