from enum import StrEnum

from pydantic import JsonValue


class ErrorCode(StrEnum):
    """Every stable error code of the API (ADR-008)."""

    # Framework errors
    VALIDATION_FAILED = "validation_failed"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    BAD_REQUEST = "bad_request"
    INTERNAL_ERROR = "internal_error"
    # Authentication
    TOKEN_EXPIRED = "token_expired"
    NOT_AUTHENTICATED = "not_authenticated"
    PASSWORD_CHANGE_REQUIRED = "password_change_required"
    FORBIDDEN = "forbidden"
    TOO_MANY_ATTEMPTS = "too_many_attempts"
    INVALID_SIGNUP_CODE = "invalid_signup_code"  # wrong, or sign-up is closed
    EMAIL_TAKEN = "email_taken"
    WRONG_PASSWORD = "wrong_password"  # the current password of a change
    PASSWORD_UNCHANGED = "password_unchanged"
    # Admin
    USER_NOT_FOUND = "user_not_found"
    OWN_ACCOUNT = "own_account"  # an admin resets their own password
    ADMIN_TARGET = "admin_target"  # the account to reset is an admin's: the CLI
    # Leagues
    LEAGUE_NOT_FOUND = "league_not_found"
    LEAGUE_ID_TAKEN = "league_id_taken"
    # Share link: an unknown token, the same for every public route (FR-071)
    SHARE_LINK_NOT_FOUND = "share_link_not_found"
    # Seasons
    SEASON_NOT_FOUND = "season_not_found"
    SEASON_CLOSED = "season_closed"
    SEASON_NUMBER_CHANGED = "season_number_changed"
    # Players
    PLAYER_NOT_FOUND = "player_not_found"
    # Also a removed player's name (BR-001, FR-012).
    PLAYER_NAME_TAKEN = "player_name_taken"
    # BR-006: 1000 active players (#48 follow-up); today 500, removed included.
    PLAYER_LIMIT_REACHED = "player_limit_reached"
    PLAYER_IN_UNFINISHED_TOURNAMENT = "player_in_unfinished_tournament"  # BR-002
    # Tournaments
    TOURNAMENT_NOT_FOUND = "tournament_not_found"
    TOURNAMENT_ID_TAKEN = "tournament_id_taken"
    TOURNAMENT_NOT_IN_SETUP = "tournament_not_in_setup"
    TOURNAMENT_TYPE_CHANGED = "tournament_type_changed"
    SEASON_HAS_UNFINISHED_TOURNAMENTS = "season_has_unfinished_tournaments"  # BR-010
    # BO2 in a league without draws (BR-121), a drawn result there or in a knockout
    DRAWS_NOT_ALLOWED = "draws_not_allowed"
    # Setup
    PLAYER_REMOVED = "player_removed"  # a removed player cannot be picked (BR-002)
    PLAYER_NOT_PICKED = "player_not_picked"
    DRAW_COUNTER_CHANGED = "draw_counter_changed"
    SEEDING_METHOD_CHANGED = "seeding_method_changed"
    SEED_ORDER_CHANGED = "seed_order_changed"
    DYP_HALVES_INCOMPLETE = "dyp_halves_incomplete"
    NOTHING_TO_PAIR = "nothing_to_pair"  # "pair the rest" with fewer than 2 left
    # A number of points for sitting out in a round robin (BR-071)
    SIT_OUT_POINTS_NOT_APPLICABLE = "sit_out_points_not_applicable"
    # Start and back to setup
    TOURNAMENT_NOT_IN_PROGRESS = "tournament_not_in_progress"
    TOURNAMENT_HAS_RESULTS = "tournament_has_results"  # FR-036
    FORMAT_NOT_SUPPORTED = "format_not_supported"  # until its rounds are served
    PLAYERS_WITHOUT_PARTNER = "players_without_partner"  # Doubles (BR-030)
    # FR-032: 64 entries today, 16 after the #48 follow-up (issue to open after
    # approval).
    TOO_MANY_ENTRIES_FOR_ROUND_ROBIN = "too_many_entries_for_round_robin"
    TOO_MANY_ENTRIES_FOR_KNOCKOUT = "too_many_entries_for_knockout"  # 256
    # Results, standings and finishing
    MATCH_NOT_FOUND = "match_not_found"
    MATCH_SIDES_UNKNOWN = "match_sides_unknown"  # BR-091
    MATCH_SIDES_CHANGED = (
        "match_sides_changed"  # the derived sides are not the ones seen
    )
    EXPECTED_SIDES_REQUIRED = "expected_sides_required"  # a derived match needs them
    GROUP_PHASE_NOT_DONE = "group_phase_not_done"  # FR-040
    GROUP_PHASE_LOCKED = "group_phase_locked"  # the knockout is drawn (BR-053)
    RESULT_LOCKED = "result_locked"  # a later knockout match has a result (BR-094)
    CURRENT_PHASE_CHANGED = "current_phase_changed"  # the knockout was drawn (FR-045)
    QUALIFIERS_OUT_OF_RANGE = "qualifiers_out_of_range"  # BR-080
    QUALIFIERS_CHANGED = "qualifiers_changed"  # the cut is not the one previewed
    PHASE_NOT_FOUND = "phase_not_found"
    PHASE_NOT_DELETABLE = "phase_not_deletable"  # only a knockout after a group phase
    KNOCKOUT_NOT_FOUND = "knockout_not_found"  # the tournament has no knockout
    KNOCKOUT_MODE_NOT_APPLICABLE = "knockout_mode_not_applicable"  # Monster DYP only
    # Fields (FR-090 to FR-094)
    FIELD_NOT_FOUND = "field_not_found"
    FIELD_NUMBER_CHANGED = "field_number_changed"  # the expected new number is stale
    FIELD_NOT_FREE = "field_not_free"  # another match is on it now
    # A match placed by hand has a result now (409), or the final whose format
    # changes has one (422, FR-054, BR-096)
    MATCH_HAS_RESULT = "match_has_result"
    PLACEMENT_CHANGED = "placement_changed"  # a match is not where the screen saw it
    PLACEMENT_NOT_ALLOWED = "placement_not_allowed"  # not one of the FR-093 operations
    LAST_FIELD = "last_field"  # the last field cannot be removed (BR-132)
    PLAYER_ON_ANOTHER_FIELD = "player_on_another_field"  # BR-131
    # Engine rules (engine/errors.py)
    NOT_ENOUGH_PLAYERS = "not_enough_players"
    NOT_ENOUGH_ENTRIES = "not_enough_entries"  # FR-032
    DYP_HALVES_UNEQUAL = "dyp_halves_unequal"
    TOO_MANY_LEFT_OUT = "too_many_left_out"
    GAME_SCORE_MISMATCH = "game_score_mismatch"  # BR-092
    SCORES_REQUIRED = "scores_required"  # BR-092: Swiss and Monster DYP
    RESULT_DOES_NOT_FIT_FORMAT = "result_does_not_fit_format"  # BR-121


class AppError(Exception):
    """An error the API reports as {"code": ..., "detail": ...} (ADR-008)."""

    def __init__(self, code: ErrorCode, **detail: JsonValue) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


class NotAuthenticatedError(AppError):
    """No valid access token (HTTP 401)."""


class ForbiddenError(AppError):
    """Not allowed (HTTP 403)."""


class NotFoundError(AppError):
    """Unknown id, or one from another organizer's league (HTTP 404)."""


class ConflictError(AppError):
    """The expected state did not match, or a client id is taken (HTTP 409)."""


class RuleViolationError(AppError):
    """A business rule refused the request (HTTP 422)."""


class TooManyAttemptsError(AppError):
    """Too many failed logins; try again after `retry_after` seconds (HTTP 429).

    The response carries the seconds in `detail` and in `Retry-After` (ADR-006).
    """

    def __init__(self, *, retry_after: int) -> None:
        super().__init__(ErrorCode.TOO_MANY_ATTEMPTS, retry_after=retry_after)
        self.retry_after = retry_after
