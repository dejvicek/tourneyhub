using System.Text.Json;
using TourneyHub.Domain.Logic.Formats;
using Xunit;

namespace TourneyHub.Domain.Tests;

public class SingleEliminationGeneratorTests
{
    [Fact]
    public void Golden_vectors_test()
    {
        using var doc = JsonDocument.Parse(File.ReadAllText("single-elimination.json"));
        var cases = doc.RootElement.GetProperty("cases");

        foreach (var testCase in cases.EnumerateArray())
        {
            var name = testCase.GetProperty("name").GetString()!;
            var participants = testCase.GetProperty("participants").GetInt32();
            var expectedBracketSize = testCase.GetProperty("bracketSize").GetInt32();
            var expectedByeCount = testCase.GetProperty("byeCount").GetInt32();
            var expectedByeSeeds = testCase.GetProperty("byeSeeds").EnumerateArray().Select(e => e.GetInt32()).ToList();
            var expectedRealMatchCount = testCase.GetProperty("realMatchCount").GetInt32();
            var bracketSize = expectedBracketSize;

            var bracket = SingleEliminationGenerator.Generate(participants, "test-seed");

            Assert.Equal(expectedBracketSize, bracket.BracketSize);
            Assert.Equal(expectedByeCount, bracket.ByeCount);
            Assert.Equal(expectedRealMatchCount, SingleEliminationGenerator.RealMatchCount(participants));
            Assert.Equal(bracketSize - 1, bracket.Matches.Count);

            var byeSeeds = SingleEliminationGenerator.GetByeSeeds(participants);
            Assert.Equal(expectedByeSeeds, byeSeeds);

            foreach (var round in testCase.GetProperty("rounds").EnumerateArray())
            {
                var roundNum = round.GetProperty("round").GetInt32();
                var roundMatches = round.GetProperty("matches");

                foreach (var expectedMatch in roundMatches.EnumerateArray())
                {
                    var slot = expectedMatch.GetProperty("slot").GetInt32();
                    var matchId = expectedMatch.GetProperty("id").GetString()!;

                    var bracketMatch = bracket.Matches.First(m =>
                        m.RoundNumber == roundNum && m.PositionInRound == slot);

                    Assert.NotNull(bracketMatch);

                    var a = expectedMatch.GetProperty("a");
                    AssertSide(name, matchId, "A", a, bracketMatch.SeedA);

                    var b = expectedMatch.GetProperty("b");
                    AssertSide(name, matchId, "B", b, bracketMatch.SeedB);

                    bool expectedWalkover = GetExpectedWalkover(expectedMatch);
                    Assert.Equal(expectedWalkover, bracketMatch.IsByeMatch);
                }
            }
        }
    }

    private static bool GetExpectedWalkover(JsonElement expectedMatch)
    {
        if (expectedMatch.TryGetProperty("walkover", out var walkover) && walkover.ValueKind == JsonValueKind.True)
            return true;
        return false;
    }

    private static void AssertSide(string caseName, string matchId, string sideLabel, JsonElement side, int? actualSeed)
    {
        if (side.ValueKind == JsonValueKind.Number)
        {
            Assert.True(actualSeed.HasValue,
                $"[{caseName}] {matchId} side {sideLabel}: expected seed {side.GetInt32()}, got null");
            Assert.Equal(side.GetInt32(), actualSeed!.Value);
        }
        else
        {
            Assert.Null(actualSeed);
        }
    }

    [Theory]
    [InlineData(2, 2)]
    [InlineData(3, 4)]
    [InlineData(4, 4)]
    [InlineData(5, 8)]
    [InlineData(7, 8)]
    [InlineData(8, 8)]
    [InlineData(9, 16)]
    [InlineData(16, 16)]
    public void NextPowerOfTwo_returns_correct_value(int input, int expected)
    {
        Assert.Equal(expected, SingleEliminationGenerator.NextPowerOfTwo(input));
    }

    [Theory]
    [InlineData(2)]
    [InlineData(4)]
    [InlineData(8)]
    [InlineData(16)]
    public void BuildSlotOrder_creates_valid_bracket(int size)
    {
        var order = SingleEliminationGenerator.BuildSlotOrder(size);

        Assert.Equal(size, order.Count);
        Assert.Equal(Enumerable.Range(1, size).OrderBy(x => x), order.OrderBy(x => x));

        for (int i = 0; i < size / 2; i++)
        {
            Assert.Equal(size + 1, order[i * 2] + order[i * 2 + 1]);
        }
    }

    [Fact]
    public void N3_1_bye_to_seed_1()
    {
        var bracket = SingleEliminationGenerator.Generate(3, "test");

        Assert.Equal(4, bracket.BracketSize);
        Assert.Equal(1, bracket.ByeCount);
        Assert.Equal(3, bracket.Matches.Count);

        var byeSeeds = SingleEliminationGenerator.GetByeSeeds(3);
        Assert.Equal([1], byeSeeds);

        var byeMatch = bracket.Matches.First(m => m.RoundNumber == 1 && m.PositionInRound == 1);
        Assert.True(byeMatch.IsByeMatch);
        Assert.Equal(1, byeMatch.SeedA);
        Assert.Null(byeMatch.SeedB);

        var finalMatch = bracket.Matches.First(m => m.RoundNumber == 2 && m.PositionInRound == 1);
        Assert.Equal(1, finalMatch.SeedA);
        Assert.Null(finalMatch.SeedB);
    }

    [Fact]
    public void N7_1_bye_to_seed_1()
    {
        var bracket = SingleEliminationGenerator.Generate(7, "test");

        Assert.Equal(8, bracket.BracketSize);
        Assert.Equal(1, bracket.ByeCount);
        Assert.Equal(7, bracket.Matches.Count);

        var byeSeeds = SingleEliminationGenerator.GetByeSeeds(7);
        Assert.Equal([1], byeSeeds);

        var byeMatch = bracket.Matches.First(m => m.RoundNumber == 1 && m.PositionInRound == 1);
        Assert.True(byeMatch.IsByeMatch);
        Assert.Equal(1, byeMatch.SeedA);
        Assert.Null(byeMatch.SeedB);
    }

    [Fact]
    public void N16_no_byes()
    {
        var bracket = SingleEliminationGenerator.Generate(16, "test");

        Assert.Equal(16, bracket.BracketSize);
        Assert.Equal(0, bracket.ByeCount);
        Assert.Equal(15, bracket.Matches.Count);

        var byeSeeds = SingleEliminationGenerator.GetByeSeeds(16);
        Assert.Empty(byeSeeds);
    }

    [Fact]
    public void N5_3_byes_to_seeds_1_2_3()
    {
        var bracket = SingleEliminationGenerator.Generate(5, "test");

        Assert.Equal(8, bracket.BracketSize);
        Assert.Equal(3, bracket.ByeCount);
        Assert.Equal(7, bracket.Matches.Count);

        var byeSeeds = SingleEliminationGenerator.GetByeSeeds(5);
        Assert.Equal([1, 2, 3], byeSeeds);

        var byeMatches = bracket.Matches.Where(m => m.IsByeMatch).ToList();
        Assert.Equal(3, byeMatches.Count);

        var finalMatch = bracket.Matches.First(m => m.RoundNumber == 3 && m.PositionInRound == 1);
        Assert.Null(finalMatch.SeedA);
        Assert.Null(finalMatch.SeedB);
    }

    [Fact]
    public void Determinism_same_seed_produces_same_bracket()
    {
        var bracket1 = SingleEliminationGenerator.Generate(7, "fixed-seed");
        var bracket2 = SingleEliminationGenerator.Generate(7, "fixed-seed");

        Assert.Equal(bracket1.BracketSize, bracket2.BracketSize);
        Assert.Equal(bracket1.Matches.Count, bracket2.Matches.Count);

        for (int i = 0; i < bracket1.Matches.Count; i++)
        {
            var m1 = bracket1.Matches[i];
            var m2 = bracket2.Matches[i];

            Assert.Equal(m1.RoundNumber, m2.RoundNumber);
            Assert.Equal(m1.PositionInRound, m2.PositionInRound);
            Assert.Equal(m1.SeedA, m2.SeedA);
            Assert.Equal(m1.SeedB, m2.SeedB);
            Assert.Equal(m1.IsByeMatch, m2.IsByeMatch);
        }
    }

    [Fact]
    public void ShuffleSeeds_deterministic()
    {
        var seeds1 = SingleEliminationGenerator.ShuffleSeeds(8, "deterministic-seed");
        var seeds2 = SingleEliminationGenerator.ShuffleSeeds(8, "deterministic-seed");

        Assert.Equal(seeds1, seeds2);
    }

    [Fact]
    public void RealMatchCount_equals_participants_minus_1()
    {
        for (int n = 2; n <= 64; n++)
        {
            Assert.Equal(n - 1, SingleEliminationGenerator.RealMatchCount(n));
        }
    }

    [Fact]
    public void No_match_has_bye_on_both_sides()
    {
        for (int n = 3; n <= 32; n++)
        {
            var bracket = SingleEliminationGenerator.Generate(n, $"test-{n}");

            foreach (var match in bracket.Matches.Where(m => m.RoundNumber == 1))
            {
                Assert.False(match.SeedA is null && match.SeedB is null,
                    $"Round 1 match position {match.PositionInRound} for N={n} has BYE on both sides");
            }
        }
    }

    [Fact]
    public void Seed_1_and_seed_2_only_meet_in_final()
    {
        for (int n = 2; n <= 16; n++)
        {
            var bracket = SingleEliminationGenerator.Generate(n, $"test-{n}");

            int? meetRound = null;
            foreach (var match in bracket.Matches)
            {
                if ((match.SeedA == 1 && match.SeedB == 2) || (match.SeedA == 2 && match.SeedB == 1))
                {
                    meetRound = match.RoundNumber;
                    break;
                }
            }

            if (meetRound.HasValue)
            {
                Assert.Equal(bracket.TotalRounds, meetRound.Value);
            }
        }
    }

    [Fact]
    public void Throws_for_less_than_2_participants()
    {
        Assert.Throws<BracketGeneratorException>(() => SingleEliminationGenerator.Generate(1, "seed"));
        Assert.Throws<BracketGeneratorException>(() => SingleEliminationGenerator.Generate(0, "seed"));
    }

    [Fact]
    public void ShuffleSeeds_throws_for_null_rngSeed()
    {
        Assert.Throws<ArgumentNullException>(() => SingleEliminationGenerator.ShuffleSeeds(4, null!));
    }
}