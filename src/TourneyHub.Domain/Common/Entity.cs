namespace TourneyHub.Domain.Common;

/// <summary>
/// Base entity: identity + an optimistic-concurrency version (NFR-023).
/// Mutable competition/finance entities increment <see cref="Version"/> on change.
/// Entities may raise <see cref="IDomainEvent"/>s that are captured by the persistence
/// layer and written to the transactional outbox in the same DB transaction.
/// </summary>
public abstract class Entity
{
    private readonly List<IDomainEvent> _domainEvents = [];

    public Guid Id { get; protected set; } = Guid.NewGuid();

    /// <summary>Optimistic-locking token (ETag / If-Match maps to this). NFR-023.</summary>
    public int Version { get; protected set; }

    public void IncrementVersion() => Version++;

    public IReadOnlyCollection<IDomainEvent> DomainEvents => _domainEvents.AsReadOnly();

    protected void RaiseDomainEvent(IDomainEvent domainEvent) => _domainEvents.Add(domainEvent);

    public void ClearDomainEvents() => _domainEvents.Clear();
}
