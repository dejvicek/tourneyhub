namespace TourneyHub.Application;

/// <summary>
/// Assembly marker for DI/assembly scanning (e.g. MediatR/validators registration).
/// Ports (interfaces) such as INotificationChannel, IPaymentProvider, IEntitlementService,
/// and the tenant-scoping abstraction live in this layer.
/// </summary>
public interface IApplicationMarker { }
