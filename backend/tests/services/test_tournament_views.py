from datetime import UTC, datetime
from uuid import UUID, uuid7

import pytest

from tourneyhub.db.models.matches import Match, MatchSide, MatchSidePlayer, Round
from tourneyhub.db.models.tournaments import Tournament, TournamentPhase
from tourneyhub.engine.ids import PlayerId
from tourneyhub.engine.tournaments import (
    KnockoutMatchFormat,
    MatchFormat,
    MatchKind,
    PhaseKind,
)
from tourneyhub.services.tournaments import (
    SideView,
    _match_format,
    _match_slots,
    _match_view,
)

NOW = datetime(2026, 11, 12, tzinfo=UTC)


def _side(
    side: int,
    *,
    entry_id: UUID | None = None,
    players: tuple[UUID, ...] = (),
    is_bye: bool = False,
) -> MatchSide:
    match_id = uuid7()
    return MatchSide(
        match_id=match_id,
        side=side,
        entry_id=entry_id,
        is_bye=is_bye,
        created_at=NOW,
        players=[
            MatchSidePlayer(match_id=match_id, side=side, player_id=p, created_at=NOW)
            for p in players
        ],
    )


def _match(*sides: MatchSide) -> Match:
    return Match(
        id=uuid7(),
        round_id=uuid7(),
        position=1,
        kind=MatchKind.STANDARD,
        is_walkover=False,
        created_at=NOW,
        sides=list(sides),
        games=[],
    )


def _tournament(match: Match) -> Tournament:
    round_ = Round(id=uuid7(), round_no=2, created_at=NOW, matches=[match])
    phase = TournamentPhase(id=uuid7(), position=1, rounds=[round_])
    return Tournament(id=uuid7(), phases=[phase])


def test_d4_a_knockout_match_without_stored_sides_has_no_players_yet() -> None:
    match = _match()

    assert _match_slots(_tournament(match))[0].player_ids is None
    assert _match_view(match, {}).sides == (
        SideView(entry_id=None, player_ids=(), is_bye=False),
        SideView(entry_id=None, player_ids=(), is_bye=False),
    )


def test_d4_a_side_without_entry_or_players_leaves_the_players_unknown() -> None:
    entry, player = uuid7(), uuid7()
    match = _match(
        _side(1, entry_id=entry, players=(player,)),
        _side(2),
    )

    assert _match_slots(_tournament(match))[0].player_ids is None
    view = _match_view(match, {entry: (player,)})
    assert view.sides[0] == SideView(entry_id=entry, player_ids=(player,), is_bye=False)
    assert view.sides[1] == SideView(entry_id=None, player_ids=(), is_bye=False)


def test_d4_a_missing_second_side_is_shown_empty() -> None:
    entry, player = uuid7(), uuid7()
    match = _match(_side(1, entry_id=entry, players=(player,)))

    assert _match_view(match, {entry: (player,)}).sides[1] == SideView(
        entry_id=None, player_ids=(), is_bye=False
    )


def test_d2_a_bye_and_a_team_without_an_entry_are_known_sides() -> None:
    one, two = uuid7(), uuid7()
    team = _match(_side(1, players=(one, two)), _side(2, is_bye=True))
    other = uuid7()
    played = _match(_side(1, players=(one,)), _side(2, players=(other,)))

    assert _match_slots(_tournament(team))[0].player_ids == frozenset(
        {PlayerId(one), PlayerId(two)}
    )
    assert _match_slots(_tournament(played))[0].player_ids == frozenset(
        {PlayerId(one), PlayerId(other)}
    )


def _knockout(final_format: KnockoutMatchFormat | None) -> TournamentPhase:
    rounds = [
        Round(
            id=uuid7(),
            round_no=round_no,
            created_at=NOW,
            matches=[
                Match(id=uuid7(), position=1, kind=kind, created_at=NOW)
                for kind in kinds
            ],
        )
        for round_no, kinds in (
            (1, (MatchKind.STANDARD, MatchKind.STANDARD)),
            (2, (MatchKind.STANDARD, MatchKind.THIRD_PLACE)),
        )
    ]
    return TournamentPhase(
        id=uuid7(),
        position=1,
        kind=PhaseKind.KNOCKOUT,
        match_format=MatchFormat.BO3,
        final_match_format=final_format,
        rounds=rounds,
    )


@pytest.mark.parametrize(
    ("final_format", "round_no", "kind", "expected"),
    [
        pytest.param(
            KnockoutMatchFormat.BO5, 2, MatchKind.STANDARD, MatchFormat.BO5, id="final"
        ),
        pytest.param(
            KnockoutMatchFormat.BO5,
            2,
            MatchKind.THIRD_PLACE,
            MatchFormat.BO3,
            id="third-place",
        ),
        pytest.param(
            KnockoutMatchFormat.BO5, 1, MatchKind.STANDARD, MatchFormat.BO3, id="semi"
        ),
        pytest.param(None, 2, MatchKind.STANDARD, MatchFormat.BO3, id="no-own"),
    ],
)
def test_br120_the_final_plays_its_own_format(
    final_format: KnockoutMatchFormat | None,
    round_no: int,
    kind: MatchKind,
    expected: MatchFormat,
) -> None:
    phase = _knockout(final_format)
    round_ = phase.rounds[round_no - 1]
    match = next(m for m in round_.matches if m.kind is kind)

    assert _match_format(phase, round_, match) is expected
