import pytest

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
from tourneyhub.errors import ErrorCode
from tourneyhub.services.engine_errors import to_app_error


@pytest.mark.parametrize(
    ("error", "code", "detail"),
    [
        pytest.param(
            NotEnoughPlayersError(minimum=4, given=3),
            ErrorCode.NOT_ENOUGH_PLAYERS,
            {"minimum": 4, "given": 3},
            id="BR-031",
        ),
        pytest.param(
            NotEnoughEntriesError(minimum=2, given=1),
            ErrorCode.NOT_ENOUGH_ENTRIES,
            {"minimum": 2, "given": 1},
            id="FR-032",
        ),
        pytest.param(
            DypHalvesUnequalError(top=3, bottom=2),
            ErrorCode.DYP_HALVES_UNEQUAL,
            {"top": 3, "bottom": 2},
            id="BR-032-unequal",
        ),
        pytest.param(
            TooManyLeftOutError(maximum=1, given=2),
            ErrorCode.TOO_MANY_LEFT_OUT,
            {"maximum": 1, "given": 2},
            id="BR-032-left-out",
        ),
        pytest.param(
            GameScoreMismatchError(game_no=2),
            ErrorCode.GAME_SCORE_MISMATCH,
            {"game_no": 2},
            id="BR-092-mismatch",
        ),
        pytest.param(
            ScoresRequiredError(game_no=1),
            ErrorCode.SCORES_REQUIRED,
            {"game_no": 1},
            id="BR-092-required",
        ),
        pytest.param(
            DrawNotAllowedError(), ErrorCode.DRAWS_NOT_ALLOWED, {}, id="BR-090"
        ),
        pytest.param(
            ResultDoesNotFitFormatError(match_format="bo3", games=1),
            ErrorCode.RESULT_DOES_NOT_FIT_FORMAT,
            {"format": "bo3", "games": 1},
            id="BR-121",
        ),
    ],
)
def test_an_engine_refusal_becomes_a_rule_violation_with_its_fields(
    error: EngineError, code: ErrorCode, detail: dict[str, int | str]
) -> None:
    translated = to_app_error(error)

    assert translated.code is code
    assert translated.detail == detail


def test_an_engine_refusal_without_a_code_is_a_bug() -> None:
    with pytest.raises(TypeError, match="no error code"):
        to_app_error(EngineError())
