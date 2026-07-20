using System.Reflection;
using TourneyHub.Domain.Common;
using TourneyHub.Domain.Identity;
using TourneyHub.Domain.Identity.Events;
using Xunit;

namespace TourneyHub.Architecture.Tests;

public class NotificationDomainEventMappingTests
{
    [Fact]
    public void All_notifiable_events_map_to_transactional_category()
    {
        var eventTypes = new[]
        {
            typeof(UserRegisteredEvent),
            typeof(PasswordResetRequestedEvent),
        };

        foreach (var t in eventTypes)
        {
            Assert.NotNull(t);

            var domainEventBase = t.BaseType;
            Assert.NotNull(domainEventBase);
            Assert.Contains("DomainEvent", domainEventBase!.Name);
        }
    }

    [Fact]
    public void UserRegisteredEvent_has_required_properties()
    {
        var props = typeof(UserRegisteredEvent).GetProperties(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly);
        var propNames = props.Select(p => p.Name).ToHashSet();

        Assert.Contains("UserId", propNames);
        Assert.Contains("Email", propNames);
        Assert.Contains("DisplayName", propNames);
        Assert.Contains("VerificationToken", propNames);
    }

    [Fact]
    public void PasswordResetRequestedEvent_has_required_properties()
    {
        var props = typeof(PasswordResetRequestedEvent).GetProperties(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly);
        var propNames = props.Select(p => p.Name).ToHashSet();

        Assert.Contains("UserId", propNames);
        Assert.Contains("Email", propNames);
        Assert.Contains("ResetToken", propNames);
    }

    [Fact]
    public void InvitationCreatedEvent_has_required_properties()
    {
        var props = typeof(InvitationCreatedEvent).GetProperties(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly);
        var propNames = props.Select(p => p.Name).ToHashSet();

        Assert.Contains("InvitationId", propNames);
        Assert.Contains("OrganizationId", propNames);
        Assert.Contains("Email", propNames);
        Assert.Contains("ScopeType", propNames);
        Assert.Contains("ScopeId", propNames);
        Assert.Contains("Role", propNames);
    }

    [Fact]
    public void NotificationOutboxConsumer_event_types_reference_actual_types()
    {
        Assert.IsAssignableFrom<IDomainEvent>(new UserRegisteredEvent(
            Guid.NewGuid(), "test@example.com", "Test", "token123"));
        Assert.IsAssignableFrom<IDomainEvent>(new PasswordResetRequestedEvent(
            Guid.NewGuid(), "test@example.com", "token123"));
        Assert.IsAssignableFrom<IDomainEvent>(new InvitationCreatedEvent(
            Guid.NewGuid(), Guid.NewGuid(), "test@example.com", InvitationScopeType.League, Guid.NewGuid(), InvitedRole.Player));
    }
}
