using TourneyHub.Domain.Competition;

namespace TourneyHub.Domain.Logic.Scoring;

public readonly record struct MatchResult(int HomeScore, int AwayScore, bool IsHomeForfeit = false, bool IsAwayForfeit = false, bool IsBye = false);

public static class ScoringCalculator
{
    public static (int homePoints, int awayPoints) CalculatePoints(MatchResult result, ScoringConfig config)
    {
        ArgumentNullException.ThrowIfNull(config);
        if (result.IsBye)
        {
            return (config.ByePoints, 0);
        }

        if (result.IsHomeForfeit && result.IsAwayForfeit)
        {
            throw new ScoringOperationException("double_forfeit", "Both participants cannot forfeit.");
        }

        if (result.IsHomeForfeit)
        {
            return (config.LossPoints, config.WinPoints);
        }

        if (result.IsAwayForfeit)
        {
            return (config.WinPoints, config.LossPoints);
        }

        if (result.HomeScore == result.AwayScore)
        {
            return (config.DrawPoints + config.ParticipationPoints, config.DrawPoints + config.ParticipationPoints);
        }

        if (result.HomeScore > result.AwayScore)
        {
            return (
                config.WinPoints + config.ParticipationPoints,
                config.LossPoints + config.ParticipationPoints);
        }

        return (
            config.LossPoints + config.ParticipationPoints,
            config.WinPoints + config.ParticipationPoints);
    }

    public static ScoringResultValidation ValidateResult(MatchResult result, ScoringConfig config)
    {
        ArgumentNullException.ThrowIfNull(config);
        if (result.IsBye)
        {
            return ScoringResultValidation.Valid;
        }

        if (result.IsHomeForfeit || result.IsAwayForfeit)
        {
            return ScoringResultValidation.Valid;
        }

        if (result.HomeScore < 0 || result.AwayScore < 0)
        {
            return ScoringResultValidation.Invalid("Scores cannot be negative.");
        }

        if (!config.AllowDraws && result.HomeScore == result.AwayScore)
        {
            return ScoringResultValidation.Invalid("Draws are not allowed by the scoring configuration.");
        }

        return ScoringResultValidation.Valid;
    }
}

public readonly record struct ScoringResultValidation
{
    public bool IsValid { get; }
    public string? ErrorMessage { get; }

    private ScoringResultValidation(bool isValid, string? errorMessage)
    {
        IsValid = isValid;
        ErrorMessage = errorMessage;
    }

    public static ScoringResultValidation Valid => new(true, null);

    public static ScoringResultValidation Invalid(string message) => new(false, message);
}

public class ScoringOperationException : Exception
{
    public string Code { get; }

    public ScoringOperationException(string code, string message) : base(message)
    {
        Code = code;
    }
}
