namespace TourneyHub.Domain.Common;

/// <summary>
/// Test entity for integration tests exercising the domain-event capture +
/// transactional-outbox path end-to-end. Not part of the production domain model.
/// Configured in <c>TourneyHubDbContext.OnModelCreating</c>.
/// </summary>
public class TestEntity : TenantEntity
{
    public string Name { get; private set; } = "test";

    private TestEntity() { }

    public TestEntity(string name)
    {
        Name = name;
    }

    public void RaiseTestEvent(string data)
    {
        RaiseDomainEvent(new TestEventRaised(data));
    }
}

/// <summary>
/// Test domain event for integration testing the outbox.
/// </summary>
public sealed record TestEventRaised(string Data) : DomainEvent;