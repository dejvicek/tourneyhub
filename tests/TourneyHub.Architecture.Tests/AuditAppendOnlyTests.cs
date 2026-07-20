using System.Reflection;
using TourneyHub.Domain.Platform;
using Xunit;

namespace TourneyHub.Architecture.Tests;

/// <summary>
/// Verifies that <see cref="AuditEvent"/> is append-only (FR-121):
/// no public setters on properties and no public update/delete methods.
/// Tamper-evidence is enforced at the type-system level.
/// </summary>
public class AuditAppendOnlyTests
{
    [Fact]
    public void AuditEvent_has_no_public_setters()
    {
        var type = typeof(AuditEvent);
        var publicInstanceProperties = type.GetProperties(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly);

        foreach (var prop in publicInstanceProperties)
        {
            var setter = prop.GetSetMethod(nonPublic: false);
            Assert.Null(setter);
        }
    }

    [Fact]
    public void AuditEvent_has_no_public_mutating_methods()
    {
        var type = typeof(AuditEvent);
        var publicMethods = type.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly);

        var mutatingMethods = publicMethods.Where(m =>
            m.Name.StartsWith("Set", StringComparison.Ordinal) ||
            m.Name.StartsWith("Update", StringComparison.Ordinal) ||
            m.Name.StartsWith("Delete", StringComparison.Ordinal) ||
            m.Name.StartsWith("Modify", StringComparison.Ordinal));

        Assert.Empty(mutatingMethods);
    }
}