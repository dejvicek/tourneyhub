using TourneyHub.Domain.Common;

namespace TourneyHub.Domain.Competition;

public enum TournamentState { Draft, RegistrationOpen, RegistrationClosed, Seeded, InProgress, Completed, Cancelled }

public enum ResultModel { Winner, Score }

public enum FormatType { SingleElimination, RoundRobin }

public enum ResultEntryMode { Organizer, PlayerSelfReport }

public sealed record TournamentScoreConfig
{
    public int? MinScore { get; init; }
    public int? MaxScore { get; init; }
    public bool AllowDraws { get; init; }
}

public class Tournament : TenantEntity
{
    public Guid? LeagueId { get; private set; }
    public Guid? SeasonId { get; private set; }
    public string DisciplineName { get; private set; }
    public ResultModel ResultModel { get; private set; }
    public TournamentScoreConfig? ScoreConfig { get; private set; }
    public int TeamSize { get; private set; }
    public FormatType FormatType { get; private set; }
    public ResultEntryMode ResultEntryMode { get; private set; }
    public int? BestOf { get; private set; }
    public TournamentState State { get; private set; }
    public string? RngSeed { get; private set; }
    public string? Currency { get; private set; }
    public long? EntryFeeAmountMinor { get; private set; }
    public DateTime? RegOpenAt { get; private set; }
    public DateTime? RegCloseAt { get; private set; }
    public int? MaxParticipants { get; private set; }

    private Tournament()
    {
        DisciplineName = string.Empty;
    }

    public Tournament(
        string disciplineName,
        ResultModel resultModel,
        int teamSize,
        FormatType formatType,
        ResultEntryMode resultEntryMode,
        Guid? leagueId = null,
        Guid? seasonId = null,
        TournamentScoreConfig? scoreConfig = null,
        int? bestOf = null,
        string? currency = null,
        long? entryFeeAmountMinor = null,
        DateTime? regOpenAt = null,
        DateTime? regCloseAt = null,
        int? maxParticipants = null)
    {
        if (string.IsNullOrWhiteSpace(disciplineName))
            throw new TournamentOperationException("invalid_discipline", "Discipline name is required.");
        if (teamSize is < 1 or > 10)
            throw new TournamentOperationException("invalid_team_size", "Team size must be between 1 and 10.");
        if (scoreConfig is not null && resultModel != ResultModel.Score)
            throw new TournamentOperationException("score_config_not_allowed", "Score config is only valid with result model 'score'.");

        DisciplineName = disciplineName.Trim();
        ResultModel = resultModel;
        TeamSize = teamSize;
        FormatType = formatType;
        ResultEntryMode = resultEntryMode;
        LeagueId = leagueId;
        SeasonId = seasonId;
        ScoreConfig = scoreConfig;
        BestOf = bestOf;
        Currency = currency;
        EntryFeeAmountMinor = entryFeeAmountMinor;
        RegOpenAt = regOpenAt;
        RegCloseAt = regCloseAt;
        MaxParticipants = maxParticipants;
        State = TournamentState.Draft;
    }

    public void OpenRegistration()
    {
        EnsureNotCancelled();
        if (State != TournamentState.Draft)
            throw new TournamentOperationException("invalid_tournament_state", "Registration can only be opened from Draft state.");
        State = TournamentState.RegistrationOpen;
    }

    public void CloseRegistration()
    {
        EnsureNotCancelled();
        if (State != TournamentState.RegistrationOpen)
            throw new TournamentOperationException("invalid_tournament_state", "Registration can only be closed from RegistrationOpen state.");
        State = TournamentState.RegistrationClosed;
    }

    public void Seed()
    {
        EnsureNotCancelled();
        if (State != TournamentState.RegistrationClosed)
            throw new TournamentOperationException("invalid_tournament_state", "Can only seed from RegistrationClosed state.");
        State = TournamentState.Seeded;
    }

    public void StartInProgress()
    {
        EnsureNotCancelled();
        if (State != TournamentState.Seeded)
            throw new TournamentOperationException("invalid_tournament_state", "Tournament can only start from Seeded state.");
        State = TournamentState.InProgress;
    }

    public void Complete()
    {
        if (State != TournamentState.InProgress)
            throw new TournamentOperationException("invalid_tournament_state", "Only InProgress tournaments can be completed.");
        State = TournamentState.Completed;
    }

    public void Reopen()
    {
        if (State != TournamentState.Completed)
            throw new TournamentOperationException("invalid_tournament_state", "Only Completed tournaments can be reopened.");
        State = TournamentState.InProgress;
    }

    public void Cancel()
    {
        if (State is TournamentState.Completed or TournamentState.Cancelled)
            throw new TournamentOperationException("invalid_tournament_state", "Cannot cancel a Completed or already Cancelled tournament.");
        State = TournamentState.Cancelled;
    }

    public void SetRngSeed(string seed)
    {
        RngSeed = seed;
    }

    public bool IsRegistrationOpen()
    {
        return State == TournamentState.RegistrationOpen;
    }

    private void EnsureNotCancelled()
    {
        if (State == TournamentState.Cancelled)
            throw new TournamentOperationException("tournament_cancelled", "Cannot modify a cancelled tournament.");
    }
}

public class TournamentOperationException : Exception
{
    public string Code { get; }
    public TournamentOperationException(string code, string message) : base(message) { Code = code; }
}
