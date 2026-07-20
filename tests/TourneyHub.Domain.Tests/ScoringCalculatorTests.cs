using System.Text.Json;
using TourneyHub.Domain.Competition;
using TourneyHub.Domain.Logic.Scoring;
using Xunit;

namespace TourneyHub.Domain.Tests;

public class ScoringCalculatorTests
{
    [Fact]
    public void Football_win_awards_3_points_to_winner()
    {
        var config = ScoringPresets.Football;
        var result = new MatchResult(2, 1);

        var (homePoints, awayPoints) = ScoringCalculator.CalculatePoints(result, config);

        Assert.Equal(3, homePoints);
        Assert.Equal(0, awayPoints);
    }

    [Fact]
    public void Football_draw_awards_1_point_each()
    {
        var config = ScoringPresets.Football;
        var result = new MatchResult(1, 1);

        var (homePoints, awayPoints) = ScoringCalculator.CalculatePoints(result, config);

        Assert.Equal(1, homePoints);
        Assert.Equal(1, awayPoints);
    }

    [Fact]
    public void Football_loss_awards_0_points()
    {
        var config = ScoringPresets.Football;
        var result = new MatchResult(0, 3);

        var (homePoints, awayPoints) = ScoringCalculator.CalculatePoints(result, config);

        Assert.Equal(0, homePoints);
        Assert.Equal(3, awayPoints);
    }

    [Fact]
    public void Chess_win_awards_1_point()
    {
        var config = ScoringPresets.Chess;

        var (homePoints, awayPoints) = ScoringCalculator.CalculatePoints(new MatchResult(1, 0), config);

        Assert.Equal(1, homePoints);
        Assert.Equal(0, awayPoints);
    }

    [Fact]
    public void Chess_draw_awards_0_5_points_each()
    {
        var config = ScoringPresets.Chess;

        var (homePoints, awayPoints) = ScoringCalculator.CalculatePoints(new MatchResult(0, 0), config);

        Assert.Equal(0, homePoints);
        Assert.Equal(0, awayPoints);
    }

    [Fact]
    public void WinOnly_win_awards_1_point()
    {
        var config = ScoringPresets.WinOnly;

        var (homePoints, awayPoints) = ScoringCalculator.CalculatePoints(new MatchResult(5, 3), config);

        Assert.Equal(1, homePoints);
        Assert.Equal(0, awayPoints);
    }

    [Fact]
    public void WinOnly_loss_awards_0_points()
    {
        var config = ScoringPresets.WinOnly;

        var (homePoints, awayPoints) = ScoringCalculator.CalculatePoints(new MatchResult(1, 2), config);

        Assert.Equal(0, homePoints);
        Assert.Equal(1, awayPoints);
    }

    [Fact]
    public void Bye_awards_bye_points_to_home()
    {
        var config = ScoringPresets.Football;
        var result = new MatchResult(0, 0, IsBye: true);

        var (homePoints, awayPoints) = ScoringCalculator.CalculatePoints(result, config);

        Assert.Equal(config.ByePoints, homePoints);
        Assert.Equal(0, awayPoints);
    }

    [Fact]
    public void Home_forfeit_awards_win_to_away()
    {
        var config = ScoringPresets.Football;
        var result = new MatchResult(0, 0, IsHomeForfeit: true);

        var (homePoints, awayPoints) = ScoringCalculator.CalculatePoints(result, config);

        Assert.Equal(config.LossPoints, homePoints);
        Assert.Equal(config.WinPoints, awayPoints);
    }

    [Fact]
    public void Away_forfeit_awards_win_to_home()
    {
        var config = ScoringPresets.Football;
        var result = new MatchResult(0, 0, IsAwayForfeit: true);

        var (homePoints, awayPoints) = ScoringCalculator.CalculatePoints(result, config);

        Assert.Equal(config.WinPoints, homePoints);
        Assert.Equal(config.LossPoints, awayPoints);
    }

    [Fact]
    public void Double_forfeit_throws()
    {
        var config = ScoringPresets.Football;
        var result = new MatchResult(0, 0, IsHomeForfeit: true, IsAwayForfeit: true);

        var ex = Assert.Throws<ScoringOperationException>(() => ScoringCalculator.CalculatePoints(result, config));
        Assert.Equal("double_forfeit", ex.Code);
    }

    [Fact]
    public void Participation_points_are_added_to_both_sides()
    {
        var config = new ScoringConfig(
            winPoints: 3,
            drawPoints: 1,
            lossPoints: 0,
            byePoints: 0,
            participationPoints: 1,
            allowDraws: true,
            tieBreakers: Array.Empty<TieBreaker>());

        var (homePoints, awayPoints) = ScoringCalculator.CalculatePoints(new MatchResult(2, 1), config);

        Assert.Equal(4, homePoints);
        Assert.Equal(1, awayPoints);
    }

    [Fact]
    public void ValidateResult_allows_valid_score()
    {
        var config = ScoringPresets.Football;
        var result = new MatchResult(2, 1);

        var validation = ScoringCalculator.ValidateResult(result, config);

        Assert.True(validation.IsValid);
        Assert.Null(validation.ErrorMessage);
    }

    [Fact]
    public void ValidateResult_rejects_draw_when_allowDraws_is_false()
    {
        var config = ScoringPresets.WinOnly;
        var result = new MatchResult(1, 1);

        var validation = ScoringCalculator.ValidateResult(result, config);

        Assert.False(validation.IsValid);
        Assert.Contains("Draws are not allowed", validation.ErrorMessage);
    }

    [Fact]
    public void ValidateResult_allows_bye_regardless_of_allowDraws()
    {
        var config = ScoringPresets.WinOnly;
        var result = new MatchResult(0, 0, IsBye: true);

        var validation = ScoringCalculator.ValidateResult(result, config);

        Assert.True(validation.IsValid);
    }

    [Fact]
    public void ValidateResult_allows_forfeit_regardless_of_allowDraws()
    {
        var config = ScoringPresets.WinOnly;
        var result = new MatchResult(0, 0, IsHomeForfeit: true);

        var validation = ScoringCalculator.ValidateResult(result, config);

        Assert.True(validation.IsValid);
    }

    [Fact]
    public void ValidateResult_rejects_negative_score()
    {
        var config = ScoringPresets.Football;
        var result = new MatchResult(-1, 0);

        var validation = ScoringCalculator.ValidateResult(result, config);

        Assert.False(validation.IsValid);
        Assert.Contains("negative", validation.ErrorMessage);
    }

    [Fact]
    public void CalculatePoints_matches_tie_breaks_golden_vectors()
    {
        using var doc = JsonDocument.Parse(File.ReadAllText("tie-breaks.json"));
        var scoring = doc.RootElement.GetProperty("scoringSystem");

        var config = new ScoringConfig(
            winPoints: scoring.GetProperty("winPoints").GetInt32(),
            drawPoints: scoring.GetProperty("drawPoints").GetInt32(),
            lossPoints: scoring.GetProperty("lossPoints").GetInt32(),
            byePoints: scoring.GetProperty("byePoints").GetInt32(),
            participationPoints: 0,
            allowDraws: scoring.GetProperty("allowDraws").GetBoolean(),
            tieBreakers: scoring.GetProperty("tieBreakers")
                .EnumerateArray()
                .Select(e => Enum.Parse<TieBreaker>(e.GetString()!, ignoreCase: true))
                .ToArray());

        foreach (var testCase in doc.RootElement.GetProperty("cases").EnumerateArray())
        {
            var computedPoints = testCase.GetProperty("computedPoints");
            var matchResults = new Dictionary<string, int>();

            foreach (var match in testCase.GetProperty("matches").EnumerateArray())
            {
                var home = match.GetProperty("home").GetString()!;
                var away = match.GetProperty("away").GetString()!;
                var homeScore = match.GetProperty("homeScore").GetInt32();
                var awayScore = match.GetProperty("awayScore").GetInt32();

                var (hp, ap) = ScoringCalculator.CalculatePoints(new MatchResult(homeScore, awayScore), config);

                matchResults.TryGetValue(home, out var hTotal);
                matchResults[home] = hTotal + hp;

                matchResults.TryGetValue(away, out var aTotal);
                matchResults[away] = aTotal + ap;
            }

            foreach (var participant in testCase.GetProperty("participants").EnumerateArray())
            {
                var name = participant.GetString()!;
                var expectedPoints = computedPoints.GetProperty(name).GetInt32();
                var actualPoints = matchResults.GetValueOrDefault(name, 0);

                Assert.Equal(expectedPoints, actualPoints);
            }
        }
    }

    [Fact]
    public void Football_preset_has_correct_tie_breakers()
    {
        var config = ScoringPresets.Football;

        Assert.Equal(4, config.TieBreakers.Count);
        Assert.Equal(TieBreaker.HeadToHead, config.TieBreakers[0]);
        Assert.Equal(TieBreaker.PointsScored, config.TieBreakers[1]);
        Assert.Equal(TieBreaker.Wins, config.TieBreakers[2]);
        Assert.Equal(TieBreaker.Random, config.TieBreakers[3]);
    }

    [Fact]
    public void Chess_preset_has_correct_tie_breakers()
    {
        var config = ScoringPresets.Chess;

        Assert.Equal(3, config.TieBreakers.Count);
        Assert.Equal(TieBreaker.HeadToHead, config.TieBreakers[0]);
        Assert.Equal(TieBreaker.Wins, config.TieBreakers[1]);
        Assert.Equal(TieBreaker.Random, config.TieBreakers[2]);
    }

    [Fact]
    public void WinOnly_preset_has_correct_tie_breakers()
    {
        var config = ScoringPresets.WinOnly;

        Assert.Equal(4, config.TieBreakers.Count);
        Assert.Equal(TieBreaker.HeadToHead, config.TieBreakers[0]);
        Assert.Equal(TieBreaker.PointsScored, config.TieBreakers[1]);
        Assert.Equal(TieBreaker.PointsDifference, config.TieBreakers[2]);
        Assert.Equal(TieBreaker.Random, config.TieBreakers[3]);
    }

    [Fact]
    public void Null_config_throws_in_calculate_points()
    {
        Assert.Throws<ArgumentNullException>(() => ScoringCalculator.CalculatePoints(new MatchResult(1, 0), null!));
    }

    [Fact]
    public void Null_config_throws_in_validate_result()
    {
        Assert.Throws<ArgumentNullException>(() => ScoringCalculator.ValidateResult(new MatchResult(1, 0), null!));
    }
}
