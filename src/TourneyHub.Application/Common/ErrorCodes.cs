namespace TourneyHub.Application.Common;

public static class ErrorCodes
{
    // ── Generic ──────────────────────────────────────────────────
    public const string UnknownError = "unknown_error";
    public const string ValidationFailed = "validation_failed";
    public const string NotSupported = "not_supported";

    // ── Tenancy ──────────────────────────────────────────────────
    public const string NoTenantResolved = "no_tenant_resolved";
    public const string CrossTenantAccess = "cross_tenant_access";

    // ── Auth ─────────────────────────────────────────────────────
    public const string Unauthorized = "unauthorized";
    public const string Forbidden = "forbidden";
    public const string EmailAlreadyRegistered = "email_already_registered";
    public const string EmailNotVerified = "email_not_verified";
    public const string InvalidCredentials = "invalid_credentials";
    public const string TokenExpired = "token_expired";

    // ── Resource ─────────────────────────────────────────────────
    public const string NotFound = "not_found";
    public const string AlreadyExists = "already_exists";
    public const string SlugAlreadyTaken = "slug_already_taken";

    // ── Concurrency ──────────────────────────────────────────────
    public const string ConcurrencyConflict = "concurrency_conflict";
    public const string PreconditionRequired = "precondition_required";

    // ── Idempotency ──────────────────────────────────────────────
    public const string IdempotencyReplay = "idempotency_replay";

    // ── Rate Limiting ────────────────────────────────────────────
    public const string RateLimited = "rate_limited";

    // ── Competition ──────────────────────────────────────────────
    public const string InvalidTournamentState = "invalid_tournament_state";
    public const string RegistrationClosed = "registration_closed";
    public const string RegistrationFull = "registration_full";
    public const string ParticipantAlreadyRegistered = "participant_already_registered";
    public const string DuplicatePlayerInTournament = "duplicate_player_in_tournament";
    public const string InvalidResult = "invalid_result";
    public const string BracketAlreadyGenerated = "bracket_already_generated";
    public const string InsufficientParticipants = "insufficient_participants";
    public const string SeasonAlreadyActive = "season_already_active";

    // ── Finance ──────────────────────────────────────────────────
    public const string InvalidCurrency = "invalid_currency";
    public const string PaymentAlreadyRecorded = "payment_already_recorded";
    public const string PayoutAlreadyPaid = "payout_already_paid";
    public const string InsufficientFunds = "insufficient_funds";
    public const string InvalidMoneyOperation = "invalid_money_operation";

    // ── Organization ─────────────────────────────────────────────
    public const string OrganizationSuspended = "organization_suspended";
    public const string SoleOwnerCannotLeave = "sole_owner_cannot_leave";

    // ── Invitations ──────────────────────────────────────────────
    public const string InvitationExpired = "invitation_expired";
    public const string InvitationAlreadyAccepted = "invitation_already_accepted";
}