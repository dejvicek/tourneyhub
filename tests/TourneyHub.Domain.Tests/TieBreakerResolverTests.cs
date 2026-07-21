using System.Text.Json;
using TourneyHub.Domain.Competition;
using TourneyHub.Domain.Logic.Scoring;
using Xunit;

namespace TourneyHub.Domain.Tests;

public class TieBreakerResolverTests
{
    private static readonly Dictionary<string, Guid> ParticipantIds = new()
    {
        ["A"] = Guid.Parse("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        ["B"] = Guid.Parse("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        ["C"] = Guid.Parse("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        ["D"] = Guid.Parse("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        ["E"] = Guid.Parse("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        ["F"] = Guid.Parse("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        ["G"] = Guid.Parse("aeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
    };

    [Fact]
    public void Golden_vectors_test()
    {
        using var doc = JsonDocument.Parse(File.ReadAllText("tie-breaks.json"));
        var cases = doc.RootElement.GetProperty("cases");

        foreach (var testCase in cases.EnumerateArray())
        {
            var name = testCase.GetProperty("name").GetString()!;

            var participantNames = testCase.GetProperty("participants").EnumerateArray()
                .Select(e => e.GetString()!).ToList();
            var participantIds = participantNames.Select(n => ParticipantIds[n]).ToList();

            var matches = new List<StandingsMatchInput>();
            foreach (var matchElem in testCase.GetProperty("matches").EnumerateArray())
            {
                var home = matchElem.GetProperty("home").GetString()!;
                var away = matchElem.GetProperty("away").GetString()!;
                var homeScore = matchElem.GetProperty("homeScore").GetInt32();
                var awayScore = matchElem.GetProperty("awayScore").GetInt32();
                var winner = matchElem.GetProperty("winner").GetString()!;

                matches.Add(new StandingsMatchInput(
                    ParticipantIds[home],
                    ParticipantIds[away],
                    homeScore,
                    awayScore,
                    ParticipantIds[winner],
                    IsBye: false));
            }

            var scoringConfig = ScoringPresets.Football;
            var standings = TieBreakerResolver.ComputeStandings(
                participantIds, matches, scoringConfig, "test-rng-seed-42");

            var expectedStandings = testCase.GetProperty("expectedStandings");

            Assert.Equal(expectedStandings.GetArrayLength(), standings.Count);

            int index = 0;
            foreach (var expected in expectedStandings.EnumerateArray())
            {
                var expectedRank = expected.GetProperty("rank").GetInt32();
                var expectedParticipant = expected.GetProperty("participant").GetString()!;
                var expectedPoints = expected.GetProperty("points").GetInt32();

                var entry = standings[index];

                Assert.Equal(expectedRank, entry.Rank);
                Assert.Equal(ParticipantIds[expectedParticipant], entry.ParticipantId);
                Assert.Equal(expectedPoints, entry.Points);

                if (expected.TryGetProperty("pointsScored", out var ps))
                {
                    Assert.Equal(ps.GetInt32(), entry.PointsScored);
                }

                index++;
            }

            if (testCase.TryGetProperty("computedPoints", out var computedPoints))
            {
                foreach (var kvp in computedPoints.EnumerateObject())
                {
                    var entry = standings.First(s => s.ParticipantId == ParticipantIds[kvp.Name]);
                    Assert.Equal(kvp.Value.GetInt32(), entry.Points);
                }
            }
        }
    }

    [Fact]
    public void Deterministic_standings_on_recompute()
    {
        var participants = new List<Guid> { ParticipantIds["A"], ParticipantIds["B"], ParticipantIds["C"], ParticipantIds["D"] };

        var matches = new List<StandingsMatchInput>
        {
            new(ParticipantIds["A"], ParticipantIds["B"], 21, 15, ParticipantIds["A"]),
            new(ParticipantIds["B"], ParticipantIds["C"], 21, 10, ParticipantIds["B"]),
            new(ParticipantIds["C"], ParticipantIds["A"], 21, 18, ParticipantIds["C"]),
            new(ParticipantIds["A"], ParticipantIds["D"], 21, 5, ParticipantIds["A"]),
            new(ParticipantIds["B"], ParticipantIds["D"], 21, 8, ParticipantIds["B"]),
            new(ParticipantIds["C"], ParticipantIds["D"], 21, 12, ParticipantIds["C"]),
        };

        var standings1 = TieBreakerResolver.ComputeStandings(
            participants, matches, ScoringPresets.Football, "stable-seed-1");
        var standings2 = TieBreakerResolver.ComputeStandings(
            participants, matches, ScoringPresets.Football, "stable-seed-1");

        Assert.Equal(standings1.Count, standings2.Count);
        for (int i = 0; i < standings1.Count; i++)
        {
            Assert.Equal(standings1[i].ParticipantId, standings2[i].ParticipantId);
            Assert.Equal(standings1[i].Points, standings2[i].Points);
            Assert.Equal(standings1[i].Rank, standings2[i].Rank);
            Assert.Equal(standings1[i].PointsScored, standings2[i].PointsScored);
        }
    }

    [Fact]
    public void With_bye_match()
    {
        var participants = new List<Guid> { ParticipantIds["A"], ParticipantIds["B"], ParticipantIds["C"] };

        var matches = new List<StandingsMatchInput>
        {
            new(ParticipantIds["A"], ParticipantIds["B"], 10, 5, ParticipantIds["A"]),
            new(ParticipantIds["B"], ParticipantIds["C"], 7, 7, null),
            new(ParticipantIds["C"], ParticipantIds["A"], 8, 12, ParticipantIds["A"]),
            new(ParticipantIds["A"], Guid.Empty, 0, 0, null, IsBye: true),
            new(ParticipantIds["B"], Guid.Empty, 0, 0, null, IsBye: true),
            new(ParticipantIds["C"], Guid.Empty, 0, 0, null, IsBye: true),
        };

        var config = new ScoringConfig
        {
            WinPoints = 3, DrawPoints = 1, LossPoints = 0, ByePoints = 3,
            ParticipationPoints = 0, AllowDraws = true,
            TieBreakers = new[] { TieBreaker.HeadToHead, TieBreaker.PointsScored, TieBreaker.Random },
        };

        var standings = TieBreakerResolver.ComputeStandings(
            participants, matches, config, "bye-test-seed");

        Assert.Equal(3, standings.Count);
        Assert.Equal(1, standings[0].Rank);
        Assert.Equal(ParticipantIds["A"], standings[0].ParticipantId);
        Assert.Equal(9, standings[0].Points);

        Assert.Equal(2, standings[1].Rank);
        Assert.Equal(ParticipantIds["C"], standings[1].ParticipantId);
        Assert.Equal(4, standings[1].Points);

        Assert.Equal(3, standings[2].Rank);
        Assert.Equal(ParticipantIds["B"], standings[2].ParticipantId);
        Assert.Equal(4, standings[2].Points);
    }

    [Fact]
    public void Head_to_head_resolves_simple_tie()
    {
        var participants = new List<Guid> { ParticipantIds["E"], ParticipantIds["F"], ParticipantIds["G"] };

        var matches = new List<StandingsMatchInput>
        {
            new(ParticipantIds["E"], ParticipantIds["F"], 10, 20, ParticipantIds["F"]),
            new(ParticipantIds["E"], ParticipantIds["G"], 21, 9, ParticipantIds["E"]),
            new(ParticipantIds["F"], ParticipantIds["G"], 21, 9, ParticipantIds["F"]),
        };

        var standings = TieBreakerResolver.ComputeStandings(
            participants, matches, ScoringPresets.Football, "h2h-seed");

        Assert.Equal(3, standings.Count);
        Assert.Equal(ParticipantIds["F"], standings[0].ParticipantId);
        Assert.Equal(6, standings[0].Points);
        Assert.Equal(ParticipantIds["E"], standings[1].ParticipantId);
        Assert.Equal(3, standings[1].Points);
        Assert.Equal(ParticipantIds["G"], standings[2].ParticipantId);
        Assert.Equal(0, standings[2].Points);
    }

    [Fact]
    public void Random_tiebreaker_is_deterministic()
    {
        var participants = new List<Guid> { ParticipantIds["A"], ParticipantIds["B"] };

        var matches = new List<StandingsMatchInput>
        {
            new(ParticipantIds["A"], ParticipantIds["B"], 5, 5, null),
        };

        var config = new ScoringConfig
        {
            WinPoints = 3, DrawPoints = 1, LossPoints = 0, ByePoints = 0,
            ParticipationPoints = 0, AllowDraws = true,
            TieBreakers = new[] { TieBreaker.Random },
        };

        var standings1 = TieBreakerResolver.ComputeStandings(
            participants, matches, config, "rng-seed-999");
        var standings2 = TieBreakerResolver.ComputeStandings(
            participants, matches, config, "rng-seed-999");

        Assert.Equal(standings1[0].ParticipantId, standings2[0].ParticipantId);
        Assert.Equal(standings1[1].ParticipantId, standings2[1].ParticipantId);
    }

    [Fact]
    public void Empty_participants_returns_empty()
    {
        var standings = TieBreakerResolver.ComputeStandings(
            Array.Empty<Guid>(),
            Array.Empty<StandingsMatchInput>(),
            ScoringPresets.Football,
            "empty-seed");

        Assert.Empty(standings);
    }

    [Fact]
    public void Single_participant_ranks_first()
    {
        var participants = new List<Guid> { ParticipantIds["A"] };
        var matches = new List<StandingsMatchInput>();

        var standings = TieBreakerResolver.ComputeStandings(
            participants, matches, ScoringPresets.Football, "single-seed");

        Assert.Single(standings);
        Assert.Equal(1, standings[0].Rank);
        Assert.Equal(0, standings[0].Points);
    }

    [Fact]
    public void Points_difference_tiebreaker()
    {
        var participants = new List<Guid>
        {
            Guid.Parse("11111111-1111-1111-1111-111111111111"),
            Guid.Parse("22222222-2222-2222-2222-222222222222"),
            Guid.Parse("33333333-3333-3333-3333-333333333333"),
        };

        var p1 = participants[0];
        var p2 = participants[1];
        var p3 = participants[2];

        var matches = new List<StandingsMatchInput>
        {
            new(p1, p2, 10, 20, p2),
            new(p1, p3, 25, 15, p1),
            new(p2, p3, 5, 0, p2),
        };

        var config = new ScoringConfig
        {
            WinPoints = 3, DrawPoints = 1, LossPoints = 0, ByePoints = 0,
            ParticipationPoints = 0, AllowDraws = true,
            TieBreakers = new[] { TieBreaker.PointsDifference, TieBreaker.Random },
        };

        var standings = TieBreakerResolver.ComputeStandings(
            participants, matches, config, "pd-seed");

        Assert.Equal(3, standings.Count);
        Assert.Equal(6, standings[0].Points);
        Assert.Equal(p2, standings[0].ParticipantId);
        Assert.Equal(3, standings[1].Points);
        Assert.Equal(p1, standings[1].ParticipantId);
        Assert.Equal(0, standings[2].Points);
        Assert.Equal(p3, standings[2].ParticipantId);
    }
}