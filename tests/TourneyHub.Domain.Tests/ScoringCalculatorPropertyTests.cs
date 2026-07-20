using FsCheck;
using FsCheck.Xunit;
using TourneyHub.Domain.Competition;
using TourneyHub.Domain.Logic.Scoring;
using Xunit;

namespace TourneyHub.Domain.Tests;

public class ScoringCalculatorPropertyTests
{
    [Property]
    public Property CalculatePoints_returns_non_negative_for_any_result(
        int homeScore, int awayScore)
    {
        homeScore = Math.Abs(homeScore);
        awayScore = Math.Abs(awayScore);
        var config = ScoringPresets.Football;
        var result = new MatchResult(homeScore, awayScore);

        var (hp, ap) = ScoringCalculator.CalculatePoints(result, config);

        return (hp >= 0 && ap >= 0).ToProperty();
    }

    [Property]
    public Property AllowDraws_false_never_produces_draw_in_validation(
        int homeScore, int awayScore)
    {
        homeScore = Math.Abs(homeScore) % 1000;
        awayScore = Math.Abs(awayScore) % 1000;
        var config = ScoringPresets.WinOnly;
        var result = new MatchResult(homeScore, awayScore);

        var validation = ScoringCalculator.ValidateResult(result, config);

        if (homeScore == awayScore)
        {
            return (!validation.IsValid).ToProperty();
        }

        return validation.IsValid.ToProperty();
    }

    [Property]
    public Property CalculatePoints_is_deterministic(
        int homeScore, int awayScore)
    {
        homeScore = Math.Abs(homeScore) % 1000;
        awayScore = Math.Abs(awayScore) % 1000;
        var config = ScoringPresets.Football;
        var result = new MatchResult(homeScore, awayScore);

        var (hp1, ap1) = ScoringCalculator.CalculatePoints(result, config);
        var (hp2, ap2) = ScoringCalculator.CalculatePoints(result, config);

        return (hp1 == hp2 && ap1 == ap2).ToProperty();
    }

    [Property]
    public Property Winner_always_gets_more_points_than_loser(
        int homeScore, int awayScore)
    {
        homeScore = Math.Abs(homeScore) % 1000;
        awayScore = Math.Abs(awayScore) % 1000;
        var config = ScoringPresets.Football;
        var result = new MatchResult(homeScore, awayScore);

        var (hp, ap) = ScoringCalculator.CalculatePoints(result, config);

        if (homeScore > awayScore)
        {
            return (hp > ap).ToProperty();
        }

        if (awayScore > homeScore)
        {
            return (ap > hp).ToProperty();
        }

        return (hp == ap).ToProperty();
    }

    [Property]
    public Property NoDrawConfig_validate_rejects_all_draws(
        int score)
    {
        score = Math.Abs(score) % 1000;
        var config = ScoringPresets.WinOnly;
        var result = new MatchResult(score, score);

        var validation = ScoringCalculator.ValidateResult(result, config);

        return (!validation.IsValid).ToProperty();
    }

    [Property]
    public Property NoDrawConfig_validate_accepts_all_non_draws(
        int homeScore, int awayScore)
    {
        homeScore = Math.Abs(homeScore) % 1000;
        awayScore = Math.Abs(awayScore) % 1000;

        if (homeScore == awayScore)
        {
            return true.ToProperty();
        }

        var config = ScoringPresets.WinOnly;
        var result = new MatchResult(homeScore, awayScore);

        var validation = ScoringCalculator.ValidateResult(result, config);

        return validation.IsValid.ToProperty();
    }
}
