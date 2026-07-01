using System.Reflection;
using TourneyHub.Domain.Common;
using Xunit;

namespace TourneyHub.Architecture.Tests;

/// <summary>
/// Money guardrail (BR-008, FR-081): money is integer MINOR units. No domain type may
/// expose a binary floating-point member (double/float), which would corrupt money math.
/// (decimal is permitted for computation per PRD §11 and is intentionally NOT flagged.)
/// This turns "never use double/float for money" from prose into a failing test.
/// </summary>
public class MoneyTypeGuardTests
{
    private const BindingFlags Members =
        BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;

    [Fact]
    public void Domain_exposes_no_binary_floating_point_members()
    {
        var offenders = new List<string>();

        foreach (var type in typeof(Entity).Assembly.GetTypes())
        {
            foreach (var property in type.GetProperties(Members))
            {
                if (IsBinaryFloat(property.PropertyType))
                {
                    offenders.Add($"{type.FullName}.{property.Name} : {property.PropertyType.Name}");
                }
            }

            foreach (var field in type.GetFields(Members))
            {
                if (field.Name.Contains("BackingField", StringComparison.Ordinal))
                {
                    continue; // auto-property backing field — already covered via the property
                }

                if (IsBinaryFloat(field.FieldType))
                {
                    offenders.Add($"{type.FullName}.{field.Name} : {field.FieldType.Name}");
                }
            }
        }

        Assert.True(
            offenders.Count == 0,
            "Binary floating-point money is forbidden (BR-008/FR-081). Offending members:\n  " +
            string.Join("\n  ", offenders));
    }

    private static bool IsBinaryFloat(Type type)
    {
        var underlying = Nullable.GetUnderlyingType(type) ?? type;
        return underlying == typeof(double) || underlying == typeof(float);
    }
}
