import pytest

from tourneyhub.engine.errors import (
    DrawNotAllowedError,
    GameScoreMismatchError,
    ResultDoesNotFitFormatError,
    ScoresRequiredError,
)
from tourneyhub.engine.results import Game, match_outcome
from tourneyhub.engine.tournaments import MatchFormat, Outcome

S1, S2, DRAW = Outcome.SIDE_1, Outcome.SIDE_2, Outcome.DRAW


def games(*winners: Outcome) -> tuple[Game, ...]:
    return tuple(Game(winner=winner) for winner in winners)


def outcome(
    played: tuple[Game, ...],
    match_format: MatchFormat = MatchFormat.BO1,
    *,
    draws_allowed: bool = True,
    scores_required: bool = False,
) -> Outcome:
    return match_outcome(
        played,
        match_format=match_format,
        draws_allowed=draws_allowed,
        scores_required=scores_required,
    )


@pytest.mark.parametrize(
    ("played", "match_format", "expected"),
    [
        pytest.param(games(S1), MatchFormat.BO1, S1, id="BO1-win"),
        pytest.param(games(DRAW), MatchFormat.BO1, DRAW, id="BO1-draw"),
        pytest.param(games(S2, S2), MatchFormat.BO2, S2, id="BO2-2-0"),
        pytest.param(games(S1, S2), MatchFormat.BO2, DRAW, id="BO2-1-1"),
        pytest.param(games(S1, S1), MatchFormat.BO3, S1, id="BO3-2-0"),
        pytest.param(games(S1, S2, S2), MatchFormat.BO3, S2, id="BO3-1-2"),
        pytest.param(games(S2, S2, S2), MatchFormat.BO5, S2, id="BO5-0-3"),
        pytest.param(games(S1, S2, S1, S2, S1), MatchFormat.BO5, S1, id="BO5-3-2"),
    ],
)
def test_br121_the_games_make_the_outcome(
    played: tuple[Game, ...], match_format: MatchFormat, expected: Outcome
) -> None:
    result = outcome(played, match_format)

    assert result is expected


@pytest.mark.parametrize(
    ("played", "match_format"),
    [
        pytest.param((), MatchFormat.BO1, id="BO1-no-game"),
        pytest.param(games(S1, S1), MatchFormat.BO1, id="BO1-two-games"),
        pytest.param(games(S1), MatchFormat.BO2, id="BO2-one-game"),
        pytest.param(games(S1, S2, S1), MatchFormat.BO2, id="BO2-three-games"),
        pytest.param(games(DRAW, S1), MatchFormat.BO2, id="BO2-drawn-game"),
        pytest.param(games(S1), MatchFormat.BO3, id="BO3-undecided"),
        pytest.param((), MatchFormat.BO3, id="BO3-no-game"),
        pytest.param(games(S1, S1, S2), MatchFormat.BO3, id="BO3-game-after-decided"),
        pytest.param(games(S1, DRAW, S1), MatchFormat.BO3, id="BO3-drawn-game"),
        pytest.param(games(S1, S2, S1, S2), MatchFormat.BO5, id="BO5-undecided"),
    ],
)
def test_br121_games_that_do_not_fit_the_format_are_refused(
    played: tuple[Game, ...], match_format: MatchFormat
) -> None:
    with pytest.raises(ResultDoesNotFitFormatError) as raised:
        outcome(played, match_format)

    assert raised.value.match_format == match_format
    assert raised.value.games == len(played)


@pytest.mark.parametrize(
    ("played", "match_format"),
    [
        pytest.param(games(DRAW), MatchFormat.BO1, id="BO1"),
        pytest.param(games(S2, S1), MatchFormat.BO2, id="BO2"),
    ],
)
def test_br090_a_draw_needs_draws_allowed(
    played: tuple[Game, ...], match_format: MatchFormat
) -> None:
    with pytest.raises(DrawNotAllowedError):
        outcome(played, match_format, draws_allowed=False)


def test_br090_a_win_needs_no_draws_allowed() -> None:
    result = outcome(games(S2), draws_allowed=False)

    assert result is S2


@pytest.mark.parametrize(
    "game",
    [
        pytest.param(Game(winner=S1, score_1=10, score_2=None), id="one-score"),
        pytest.param(Game(winner=S1, score_1=None, score_2=3), id="other-score"),
        pytest.param(Game(winner=S1, score_1=3, score_2=10), id="side-1-lower"),
        pytest.param(Game(winner=S2, score_1=10, score_2=10), id="side-2-level"),
        pytest.param(Game(winner=DRAW, score_1=10, score_2=9), id="draw-unequal"),
    ],
)
def test_br092_a_score_must_agree_with_its_game(game: Game) -> None:
    with pytest.raises(GameScoreMismatchError) as raised:
        outcome((Game(winner=S1, score_1=10, score_2=4), game), MatchFormat.BO3)

    assert raised.value.game_no == 2


@pytest.mark.parametrize(
    "game",
    [
        pytest.param(Game(winner=S1, score_1=10, score_2=0), id="side-1"),
        pytest.param(Game(winner=S2, score_1=11, score_2=13), id="side-2-overtime"),
        pytest.param(Game(winner=DRAW, score_1=5, score_2=5), id="draw"),
    ],
)
def test_br123_any_whole_number_score_that_agrees_is_accepted(game: Game) -> None:
    result = outcome((game,))

    assert result is game.winner


def test_br092_swiss_and_monster_dyp_games_need_their_scores() -> None:
    with pytest.raises(ScoresRequiredError) as raised:
        outcome(
            (Game(winner=S1, score_1=10, score_2=2), Game(winner=S1)),
            MatchFormat.BO3,
            scores_required=True,
        )

    assert raised.value.game_no == 2


def test_fr051_scores_are_optional_where_not_required() -> None:
    result = outcome(
        (Game(winner=S1, score_1=10, score_2=2), Game(winner=S1)), MatchFormat.BO3
    )

    assert result is S1
