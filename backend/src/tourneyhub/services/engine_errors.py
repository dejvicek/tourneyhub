from tourneyhub.engine.errors import (
    DrawNotAllowedError,
    DypHalvesUnequalError,
    EngineError,
    GameScoreMismatchError,
    NotEnoughEntriesError,
    NotEnoughPlayersError,
    ResultDoesNotFitFormatError,
    ScoresRequiredError,
    TooManyLeftOutError,
)
from tourneyhub.errors import ErrorCode, RuleViolationError


def to_app_error(error: EngineError) -> RuleViolationError:  # noqa: PLR0911  (one case per error)
    """Translate an engine refusal into a 422 with the same fields (§4.4)."""
    match error:
        case NotEnoughPlayersError(minimum=minimum, given=given):
            return RuleViolationError(
                ErrorCode.NOT_ENOUGH_PLAYERS, minimum=minimum, given=given
            )
        case NotEnoughEntriesError(minimum=minimum, given=given):
            return RuleViolationError(
                ErrorCode.NOT_ENOUGH_ENTRIES, minimum=minimum, given=given
            )
        case DypHalvesUnequalError(top=top, bottom=bottom):
            return RuleViolationError(
                ErrorCode.DYP_HALVES_UNEQUAL, top=top, bottom=bottom
            )
        case TooManyLeftOutError(maximum=maximum, given=given):
            return RuleViolationError(
                ErrorCode.TOO_MANY_LEFT_OUT, maximum=maximum, given=given
            )
        case GameScoreMismatchError(game_no=game_no):
            return RuleViolationError(ErrorCode.GAME_SCORE_MISMATCH, game_no=game_no)
        case ScoresRequiredError(game_no=game_no):
            return RuleViolationError(ErrorCode.SCORES_REQUIRED, game_no=game_no)
        case DrawNotAllowedError():
            return RuleViolationError(ErrorCode.DRAWS_NOT_ALLOWED)
        case ResultDoesNotFitFormatError(match_format=match_format, games=games):
            return RuleViolationError(
                ErrorCode.RESULT_DOES_NOT_FIT_FORMAT, format=match_format, games=games
            )
        case _:
            msg = f"no error code for {type(error).__name__}"
            raise TypeError(msg) from error
