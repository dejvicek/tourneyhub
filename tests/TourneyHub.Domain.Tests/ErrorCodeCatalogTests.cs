using System.Reflection;
using TourneyHub.Application.Common;
using Xunit;

namespace TourneyHub.Domain.Tests;

public sealed class ErrorCodeCatalogTests
{
    [Fact]
    public void All_error_codes_are_unique()
    {
        var fields = typeof(ErrorCodes).GetFields(BindingFlags.Public | BindingFlags.Static);
        var codes = fields.Where(f => f.IsLiteral && !f.IsInitOnly).Select(f => f.GetRawConstantValue()?.ToString()).ToList();

        var duplicate = codes.GroupBy(c => c).FirstOrDefault(g => g.Count() > 1);
        Assert.Null(duplicate);
    }

    [Fact]
    public void Error_codes_use_snake_case()
    {
        var fields = typeof(ErrorCodes).GetFields(BindingFlags.Public | BindingFlags.Static);
        var codes = fields.Where(f => f.IsLiteral && !f.IsInitOnly).Select(f => f.GetRawConstantValue()?.ToString()).ToList();

        foreach (var code in codes)
        {
            Assert.Matches("^[a-z0-9_]+$", code);
        }
    }

    [Fact]
    public void Error_codes_catalog_is_not_empty()
    {
        var fields = typeof(ErrorCodes).GetFields(BindingFlags.Public | BindingFlags.Static);
        var codes = fields.Where(f => f.IsLiteral && !f.IsInitOnly).Select(f => f.GetRawConstantValue()?.ToString()).ToList();

        Assert.NotEmpty(codes);
    }
}