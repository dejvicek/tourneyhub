using System.Reflection;
using NetArchTest.Rules;
using TourneyHub.Application;
using TourneyHub.Domain.Common;
using TourneyHub.Infrastructure.Persistence;
using Xunit;

namespace TourneyHub.Architecture.Tests;

/// <summary>
/// Enforces clean-architecture module boundaries (NFR-001) as failing tests, so an agent
/// cannot quietly collapse the layering by adding a convenient inward dependency.
/// Dependencies must point INWARD: Api → Infrastructure → Application → Domain.
/// </summary>
public class ModuleBoundaryTests
{
    private static readonly Assembly DomainAssembly = typeof(Entity).Assembly;
    private static readonly Assembly ApplicationAssembly = typeof(IApplicationMarker).Assembly;
    private static readonly Assembly InfrastructureAssembly = typeof(TourneyHubDbContext).Assembly;

    [Fact]
    public void Domain_has_no_framework_or_outward_dependencies()
    {
        var result = Types.InAssembly(DomainAssembly)
            .ShouldNot()
            .HaveDependencyOnAny(
                "Microsoft.EntityFrameworkCore",
                "Microsoft.AspNetCore",
                "Npgsql",
                "StackExchange.Redis",
                "TourneyHub.Application",
                "TourneyHub.Infrastructure",
                "TourneyHub.Api")
            .GetResult();

        Assert.True(result.IsSuccessful, Describe("Domain", result));
    }

    [Fact]
    public void Application_depends_only_on_domain()
    {
        var result = Types.InAssembly(ApplicationAssembly)
            .ShouldNot()
            .HaveDependencyOnAny(
                "Microsoft.EntityFrameworkCore",
                "Microsoft.AspNetCore",
                "Npgsql",
                "StackExchange.Redis",
                "TourneyHub.Infrastructure",
                "TourneyHub.Api")
            .GetResult();

        Assert.True(result.IsSuccessful, Describe("Application", result));
    }

    [Fact]
    public void Infrastructure_does_not_depend_on_the_api_host()
    {
        var result = Types.InAssembly(InfrastructureAssembly)
            .ShouldNot()
            .HaveDependencyOn("TourneyHub.Api")
            .GetResult();

        Assert.True(result.IsSuccessful, Describe("Infrastructure", result));
    }

    private static string Describe(string layer, TestResult result)
        => result.IsSuccessful
            ? "OK"
            : $"{layer} boundary violation in: " + string.Join(", ", result.FailingTypeNames ?? Enumerable.Empty<string>());
}
