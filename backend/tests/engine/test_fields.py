from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tourneyhub.engine.fields import (
    FieldSlot,
    MatchSlot,
    Placement,
    fill_fields,
    waiting_order,
)
from tourneyhub.engine.ids import FieldId, MatchId, PlayerId
from tourneyhub.engine.tournaments import MatchKind

T0 = datetime(2026, 11, 11, 18, 0, tzinfo=UTC)


def mid(n: int) -> MatchId:
    return MatchId(UUID(int=n))


def fid(number: int) -> FieldId:
    return FieldId(UUID(int=1000 + number))


def players(*numbers: int) -> frozenset[PlayerId]:
    return frozenset(PlayerId(UUID(int=10_000 + n)) for n in numbers)


def match(
    n: int,
    *,
    round_no: int = 1,
    position: int | None = None,
    on: frozenset[PlayerId] | None = None,
    phase_position: int = 1,
    kind: MatchKind = MatchKind.STANDARD,
    has_bye: bool = False,
    has_result: bool = False,
    requeued_at: datetime | None = None,
    side_unknown: bool = False,
) -> MatchSlot:
    return MatchSlot(
        match_id=mid(n),
        phase_position=phase_position,
        round_no=round_no,
        kind=kind,
        position=n if position is None else position,
        player_ids=None
        if side_unknown
        else (players(2 * n, 2 * n + 1) if on is None else on),
        has_bye=has_bye,
        has_result=has_result,
        requeued_at=requeued_at,
    )


def field(number: int, match_id: MatchId | None = None) -> FieldSlot:
    return FieldSlot(field_id=fid(number), number=number, match_id=match_id)


def ids(slots: tuple[MatchSlot, ...]) -> list[int]:
    return [slot.match_id.int for slot in slots]


# ---------------------------------------------------------------- waiting order


def test_br130_matches_wait_by_phase_round_and_position() -> None:
    matches = [
        match(1, round_no=2, position=1),
        match(2, round_no=1, position=2),
        match(3, round_no=1, position=1),
        match(4, phase_position=2, round_no=1, position=1),
        match(5, round_no=1, position=1, kind=MatchKind.THIRD_PLACE),
    ]

    order = waiting_order(matches=matches, fields=[])

    assert ids(order) == [3, 2, 5, 1, 4]


def test_br132_requeued_matches_wait_first_earliest_first() -> None:
    matches = [
        match(1),
        match(2, requeued_at=T0 + timedelta(minutes=5)),
        match(3, requeued_at=T0),
    ]

    order = waiting_order(matches=matches, fields=[])

    assert ids(order) == [3, 2, 1]


@pytest.mark.parametrize(
    "slot",
    [
        pytest.param(match(1, has_result=True), id="FR-094-result"),
        pytest.param(match(1, has_bye=True), id="BR-041-bye"),
        pytest.param(match(1, side_unknown=True), id="D4-side-unknown"),
    ],
)
def test_fr092_matches_that_cannot_be_played_do_not_wait(slot: MatchSlot) -> None:
    assert waiting_order(matches=[slot], fields=[]) == ()


def test_fr092_a_match_on_a_field_does_not_wait() -> None:
    order = waiting_order(matches=[match(1), match(2)], fields=[field(1, mid(1))])

    assert ids(order) == [2]


@pytest.mark.parametrize(
    ("matches", "fields", "problem"),
    [
        pytest.param([match(1), match(1)], [], "given twice", id="match-twice"),
        pytest.param([], [field(1), field(1)], "given twice", id="field-twice"),
        pytest.param(
            [match(1)],
            [field(1, mid(1)), field(2, mid(1))],
            "given twice",
            id="one-match-two-fields",
        ),
        pytest.param([], [field(1, mid(9))], "unknown match", id="unknown-match"),
    ],
)
def test_adr009_inconsistent_fields_are_a_caller_bug(
    matches: list[MatchSlot], fields: list[FieldSlot], problem: str
) -> None:
    with pytest.raises(ValueError, match=problem):
        waiting_order(matches=matches, fields=fields)


# ---------------------------------------------------------------- filling


def test_br130_free_fields_take_the_first_matches_lowest_number_first() -> None:
    matches = [match(1), match(2), match(3)]

    placements = fill_fields(matches=matches, fields=[field(2), field(1)])

    assert placements == (
        Placement(field_id=fid(1), match_id=mid(1)),
        Placement(field_id=fid(2), match_id=mid(2)),
    )


def test_br131_a_match_whose_player_is_on_a_field_lets_the_next_one_go() -> None:
    matches = [
        match(1, on=players(1, 2)),
        match(2, on=players(2, 3)),
        match(3, on=players(4, 5)),
    ]

    placements = fill_fields(matches=matches, fields=[field(1, mid(1)), field(2)])

    assert placements == (Placement(field_id=fid(2), match_id=mid(3)),)


def test_br131_a_field_stays_free_when_no_waiting_match_can_be_played() -> None:
    matches = [match(1, on=players(1, 2)), match(2, on=players(1, 3))]

    placements = fill_fields(matches=matches, fields=[field(1), field(2)])

    assert placements == (Placement(field_id=fid(1), match_id=mid(1)),)


@st.composite
def queues(draw: st.DrawFn) -> tuple[list[MatchSlot], list[FieldSlot]]:
    """Matches over a small pool of players, some of them already on fields."""
    count = draw(st.integers(min_value=0, max_value=12))
    matches = [
        match(
            n,
            round_no=draw(st.integers(min_value=1, max_value=3)),
            on=frozenset(
                draw(
                    st.sets(
                        st.integers(min_value=1, max_value=10), min_size=2, max_size=4
                    ).map(lambda numbers: players(*numbers))
                )
            ),
            has_result=draw(st.booleans()),
        )
        for n in range(1, count + 1)
    ]
    field_count = draw(st.integers(min_value=1, max_value=6))
    fields: list[FieldSlot] = []
    busy: set[PlayerId] = set()
    for number in range(1, field_count + 1):
        candidates = [
            m
            for m in matches
            if not m.has_result
            and m.player_ids is not None
            and busy.isdisjoint(m.player_ids)
            and all(f.match_id != m.match_id for f in fields)
        ]
        taken = draw(st.sampled_from([None, *candidates]))
        if taken is not None and taken.player_ids is not None:
            busy |= taken.player_ids
        fields.append(field(number, None if taken is None else taken.match_id))
    return matches, fields


@given(queues())
def test_br131_nobody_plays_on_two_fields_after_filling(
    queue: tuple[list[MatchSlot], list[FieldSlot]],
) -> None:
    matches, fields = queue

    placements = fill_fields(matches=matches, fields=fields)

    placed = {p.field_id: p.match_id for p in placements}
    occupied = [placed.get(f.field_id, f.match_id) for f in fields]
    by_id = {m.match_id: m for m in matches}
    on_fields = [by_id[m] for m in occupied if m is not None]
    seen = [player for m in on_fields for player in m.player_ids or ()]
    assert len(seen) == len(set(seen))
    assert all(not m.has_result for m in on_fields if m.match_id in placed.values())
    assert all(
        f.match_id is None for f in fields if f.field_id in placed
    )  # only free fields are filled


@given(queues())
def test_br130_no_free_field_is_left_while_a_waiting_match_could_take_it(
    queue: tuple[list[MatchSlot], list[FieldSlot]],
) -> None:
    matches, fields = queue

    placements = fill_fields(matches=matches, fields=fields)

    placed = {p.field_id: p.match_id for p in placements}
    still_free = [f for f in fields if f.match_id is None and f.field_id not in placed]
    if still_free:
        by_id = {m.match_id: m for m in matches}
        busy = {
            player
            for match_id in [placed.get(f.field_id, f.match_id) for f in fields]
            if match_id is not None
            for player in by_id[match_id].player_ids or ()
        }
        left = [
            m
            for m in waiting_order(matches=matches, fields=fields)
            if m.match_id not in placed.values()
        ]
        assert all(not busy.isdisjoint(m.player_ids or ()) for m in left)
