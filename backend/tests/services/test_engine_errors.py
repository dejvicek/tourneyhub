import pytest

from tourneyhub.engine.errors import (
    DypHalvesUnequalError,
    EngineError,
    NotEnoughEntriesError,
    NotEnoughPlayersError,
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
    ],
)
def test_an_engine_refusal_becomes_a_rule_violation_with_its_fields(
    error: EngineError, code: ErrorCode, detail: dict[str, int]
) -> None:
    translated = to_app_error(error)

    assert translated.code is code
    assert translated.detail == detail


def test_an_engine_refusal_without_a_code_is_a_bug() -> None:
    with pytest.raises(TypeError, match="no error code"):
        to_app_error(EngineError())
