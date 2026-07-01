using System.Text.Json;
using TourneyHub.Domain.Finance;
using Xunit;

namespace TourneyHub.Domain.Tests;

/// <summary>
/// Locks <see cref="PayoutSplitter"/> against the golden oracle
/// <c>spec/test-vectors/payout-split.json</c> (FR-075a, BR-008).
/// </summary>
public class PayoutSplitterTests
{
    [Fact]
    public void SplitTeamPayout_matches_golden_vectors()
    {
        using var doc = JsonDocument.Parse(File.ReadAllText("payout-split.json"));

        foreach (var vector in doc.RootElement.GetProperty("teamSplit").EnumerateArray())
        {
            var amount = vector.GetProperty("payoutMinor").GetInt64();
            var teamSize = vector.GetProperty("teamSize").GetInt32();
            var expected = vector.GetProperty("expectedSharesMinor")
                .EnumerateArray()
                .Select(e => e.GetInt64())
                .ToArray();

            var actual = PayoutSplitter.SplitTeamPayout(amount, teamSize);

            Assert.Equal(expected, actual);
            Assert.Equal(amount, actual.Sum()); // shares sum exactly to the payout
        }
    }

    [Theory]
    [InlineData(10000, 3, new long[] { 3334, 3333, 3333 })]
    [InlineData(7, 2, new long[] { 4, 3 })]
    [InlineData(5000, 1, new long[] { 5000 })]
    public void SplitTeamPayout_sends_remainder_to_captain(long amount, int teamSize, long[] expected)
    {
        Assert.Equal(expected, PayoutSplitter.SplitTeamPayout(amount, teamSize));
    }
}
