namespace TourneyHub.Domain.Common;

/// <summary>
/// Base entity: identity + an optimistic-concurrency version (NFR-023).
/// Mutable competition/finance entities increment <see cref="Version"/> on change.
/// </summary>
public abstract class Entity
{
    public Guid Id { get; protected set; } = Guid.NewGuid();

    /// <summary>Optimistic-locking token (ETag / If-Match maps to this). NFR-023.</summary>
    public int Version { get; protected set; }

    public void IncrementVersion() => Version++;
}
