from tourneyhub.engine.errors import (
    DypHalvesUnequalError,
    EngineError,
    NotEnoughPlayersError,
    TooManyLeftOutError,
)
from tourneyhub.errors import ErrorCode, RuleViolationError


def to_app_error(error: EngineError) -> RuleViolationError:
    """Translate an engine refusal into a 422 with the same fields (§4.4)."""
    match error:
        case NotEnoughPlayersError(minimum=minimum, given=given):
            return RuleViolationError(
                ErrorCode.NOT_ENOUGH_PLAYERS, minimum=minimum, given=given
            )
        case DypHalvesUnequalError(top=top, bottom=bottom):
            return RuleViolationError(
                ErrorCode.DYP_HALVES_UNEQUAL, top=top, bottom=bottom
            )
        case TooManyLeftOutError(maximum=maximum, given=given):
            return RuleViolationError(
                ErrorCode.TOO_MANY_LEFT_OUT, maximum=maximum, given=given
            )
        case _:
            msg = f"no error code for {type(error).__name__}"
            raise TypeError(msg) from error
