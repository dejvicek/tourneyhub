namespace TourneyHub.Application.Organizations;

public sealed record CreateOrganizationCommand(string Name, string? Slug);
