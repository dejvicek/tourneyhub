using System.Text.Json;
using TourneyHub.Domain.Logic.Formats;
using Xunit;

namespace TourneyHub.Domain.Tests;

public class RoundRobinGeneratorTests
{
    [Fact]
    public void Golden_vectors_test()
    {
        using var doc = JsonDocument.Parse(File.ReadAllText("round-robin.json"));
        var cases = doc.RootElement.GetProperty("cases");

        foreach (var testCase in cases.EnumerateArray())
        {
            var name = testCase.GetProperty("name").GetString()!;
            var participants = testCase.GetProperty("participants").GetInt32();
            var expectedRounds = testCase.GetProperty("rounds").GetInt32();
            var expectedMatchCount = testCase.GetProperty("singleRoundMatchCount").GetInt32();
            var expectedSchedule = testCase.GetProperty("schedule");
            var expectedPairs = testCase.GetProperty("allPairs");

            var schedule = RoundRobinGenerator.Generate(participants);

            Assert.Equal(expectedRounds, schedule.TotalRounds);
            Assert.Equal(expectedMatchCount, schedule.TotalMatches);
            Assert.Equal(expectedRounds, schedule.Rounds.Count);

            var allMatchPairs = new List<(int, int)>();
            foreach (var round in schedule.Rounds)
            {
                foreach (var pairing in round.Pairings)
                {
                    int a = pairing.SeedA;
                    int b = pairing.SeedB;
                    if (a > b) (a, b) = (b, a);
                    allMatchPairs.Add((a, b));
                }
            }

            Assert.Equal(expectedMatchCount, allMatchPairs.Count);

            var expectedPairsList = expectedPairs.EnumerateArray()
                .Select(p => (p[0].GetInt32(), p[1].GetInt32()))
                .OrderBy(p => p.Item1).ThenBy(p => p.Item2)
                .ToList();

            var actualPairsList = allMatchPairs
                .OrderBy(p => p.Item1).ThenBy(p => p.Item2)
                .ToList();

            Assert.Equal(expectedPairsList, actualPairsList);

            foreach (var expectedRound in expectedSchedule.EnumerateArray())
            {
                var roundNum = expectedRound.GetProperty("round").GetInt32();
                var round = schedule.Rounds.First(r => r.RoundNumber == roundNum);

                var expectedByes = expectedRound.GetProperty("byes").EnumerateArray()
                    .Select(e => e.GetInt32()).ToList();
                var expectedMatches = expectedRound.GetProperty("matches").EnumerateArray()
                    .Select(m => (m[0].GetInt32(), m[1].GetInt32()))
                    .ToList();

                Assert.Equal(expectedByes, round.Byes.OrderBy(b => b));

                var actualMatchPairs = round.Pairings
                    .Select(p => p.SeedA < p.SeedB ? (p.SeedA, p.SeedB) : (p.SeedB, p.SeedA))
                    .ToList();

                var normalizedExpected = expectedMatches
                    .Select(m => m.Item1 < m.Item2 ? (m.Item1, m.Item2) : (m.Item2, m.Item1))
                    .ToList();

                Assert.Equal(normalizedExpected, actualMatchPairs);
            }

            foreach (var gamePerParticipant in testCase.GetProperty("gamesPerParticipant").EnumerateObject())
            {
                int seed = int.Parse(gamePerParticipant.Name);
                int expectedGames = gamePerParticipant.Value.GetInt32();

                int actualGames = schedule.Rounds.Sum(r =>
                    r.Pairings.Count(p => p.SeedA == seed || p.SeedB == seed));

                Assert.Equal(expectedGames, actualGames);
            }
        }
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    public void Throws_for_insufficient_participants(int count)
    {
        var ex = Assert.Throws<RoundRobinGeneratorException>(() => RoundRobinGenerator.Generate(count));
        Assert.Equal("insufficient_participants", ex.Code);
    }

    [Theory]
    [InlineData(4)]
    [InlineData(5)]
    [InlineData(6)]
    [InlineData(8)]
    public void No_participant_plays_twice_per_round(int participantCount)
    {
        var schedule = RoundRobinGenerator.Generate(participantCount);

        foreach (var round in schedule.Rounds)
        {
            var participantsInRound = new HashSet<int>();

            foreach (var pairing in round.Pairings)
            {
                Assert.True(participantsInRound.Add(pairing.SeedA),
                    $"Seed {pairing.SeedA} appears twice in round {round.RoundNumber}");
                Assert.True(participantsInRound.Add(pairing.SeedB),
                    $"Seed {pairing.SeedB} appears twice in round {round.RoundNumber}");
            }

            foreach (var bye in round.Byes)
            {
                Assert.True(participantsInRound.Add(bye),
                    $"Seed {bye} has bye and also plays in round {round.RoundNumber}");
            }
        }
    }

    [Theory]
    [InlineData(4)]
    [InlineData(5)]
    [InlineData(6)]
    [InlineData(8)]
    public void Every_unordered_pair_appears_exactly_once(int participantCount)
    {
        var schedule = RoundRobinGenerator.Generate(participantCount);

        var allPairs = new HashSet<(int, int)>();

        foreach (var round in schedule.Rounds)
        {
            foreach (var pairing in round.Pairings)
            {
                int a = pairing.SeedA;
                int b = pairing.SeedB;
                if (a > b) (a, b) = (b, a);
                Assert.True(allPairs.Add((a, b)),
                    $"Pair ({a},{b}) appears more than once");
            }
        }

        int expectedPairCount = participantCount * (participantCount - 1) / 2;
        Assert.Equal(expectedPairCount, allPairs.Count);
    }

    [Fact]
    public void Odd_participant_count_has_one_bye_per_round_per_participant()
    {
        const int n = 5;
        var schedule = RoundRobinGenerator.Generate(n);

        Assert.Equal(n, schedule.TotalRounds);

        var byeCountPerParticipant = new Dictionary<int, int>();
        for (int i = 1; i <= n; i++) byeCountPerParticipant[i] = 0;

        foreach (var round in schedule.Rounds)
        {
            Assert.Single(round.Byes);
            byeCountPerParticipant[round.Byes[0]]++;
        }

        foreach (var kvp in byeCountPerParticipant)
        {
            Assert.Equal(1, kvp.Value);
        }
    }

    [Fact]
    public void Even_participant_count_has_no_byes()
    {
        const int n = 4;
        var schedule = RoundRobinGenerator.Generate(n);

        Assert.Equal(n - 1, schedule.TotalRounds);

        foreach (var round in schedule.Rounds)
        {
            Assert.Empty(round.Byes);
        }
    }

    [Fact]
    public void ShuffleParticipants_is_deterministic()
    {
        var result1 = RoundRobinGenerator.ShuffleParticipants(8, "test-seed-123");
        var result2 = RoundRobinGenerator.ShuffleParticipants(8, "test-seed-123");

        Assert.Equal(result1, result2);
    }

    [Fact]
    public void ShuffleParticipants_different_seeds_produce_different_order()
    {
        var result1 = RoundRobinGenerator.ShuffleParticipants(20, "seed-A");
        var result2 = RoundRobinGenerator.ShuffleParticipants(20, "seed-B");

        Assert.NotEqual(result1, result2);
    }

    [Fact]
    public void ShuffleParticipants_contains_all_seeds()
    {
        var result = RoundRobinGenerator.ShuffleParticipants(8, "seed");
        var sorted = result.OrderBy(x => x).ToList();
        Assert.Equal(Enumerable.Range(1, 8).ToList(), sorted);
    }

    [Fact]
    public void Generate_is_deterministic()
    {
        var schedule1 = RoundRobinGenerator.Generate(6);
        var schedule2 = RoundRobinGenerator.Generate(6);

        Assert.Equal(schedule1.TotalRounds, schedule2.TotalRounds);
        Assert.Equal(schedule1.TotalMatches, schedule2.TotalMatches);

        for (int i = 0; i < schedule1.Rounds.Count; i++)
        {
            Assert.Equal(schedule1.Rounds[i].RoundNumber, schedule2.Rounds[i].RoundNumber);
            Assert.Equal(schedule1.Rounds[i].Byes, schedule2.Rounds[i].Byes);

            var pairs1 = schedule1.Rounds[i].Pairings.Select(p => (p.SeedA, p.SeedB)).ToList();
            var pairs2 = schedule2.Rounds[i].Pairings.Select(p => (p.SeedA, p.SeedB)).ToList();
            Assert.Equal(pairs1, pairs2);
        }
    }
}