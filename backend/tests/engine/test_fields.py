from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tourneyhub.engine.errors import PlayerOnAnotherFieldError
from tourneyhub.engine.fields import (
    FieldSlot,
    HandPlacement,
    MatchSlot,
    Placement,
    fill_fields,
    next_field_number,
    place_by_hand,
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


# ---------------------------------------------------------------- adding a field


@pytest.mark.parametrize(
    ("numbers", "expected"),
    [
        pytest.param([1, 2, 3], 4, id="after-the-last"),
        pytest.param([1, 3, 4], 2, id="a-gap-first"),
        pytest.param([2, 3], 1, id="field-1-removed"),
        pytest.param(range(1, 33), None, id="all-32-taken"),
    ],
)
def test_br132_a_new_field_takes_the_lowest_free_number(
    numbers: list[int], expected: int | None
) -> None:
    assert next_field_number(numbers) == expected


# ---------------------------------------------------------------- by hand


def on_fields(fields: tuple[FieldSlot, ...]) -> dict[int, int | None]:
    return {f.number: None if f.match_id is None else f.match_id.int for f in fields}


def test_fr093_a_waiting_match_goes_on_a_free_field() -> None:
    matches = [match(1), match(2), match(3)]

    placed = place_by_hand(
        matches=matches,
        fields=[field(1, mid(1)), field(2)],
        placements=[HandPlacement(match_id=mid(3), field_id=fid(2))],
    )

    assert on_fields(placed) == {1: 1, 2: 3}


def test_fr093_a_moved_match_frees_its_field_for_the_next_waiting_one() -> None:
    matches = [match(1), match(2), match(3)]

    placed = place_by_hand(
        matches=matches,
        fields=[field(1, mid(1)), field(2)],
        placements=[HandPlacement(match_id=mid(1), field_id=fid(2))],
    )

    assert on_fields(placed) == {1: 2, 2: 1}


def test_fr093_a_swap_exchanges_two_matches_and_a_repeat_changes_nothing() -> None:
    matches = [match(1), match(2), match(3)]
    swap = [
        HandPlacement(match_id=mid(1), field_id=fid(2)),
        HandPlacement(match_id=mid(2), field_id=fid(1)),
    ]

    once = place_by_hand(
        matches=matches, fields=[field(1, mid(1)), field(2, mid(2))], placements=swap
    )
    twice = place_by_hand(matches=matches, fields=once, placements=swap)

    assert on_fields(once) == {1: 2, 2: 1}
    assert twice == once


def test_fr093_a_match_sent_back_waits_and_its_field_takes_the_next_one() -> None:
    matches = [match(1), match(2), match(3)]

    placed = place_by_hand(
        matches=matches,
        fields=[field(1, mid(1)), field(2, mid(2))],
        placements=[HandPlacement(match_id=mid(1), field_id=None)],
    )

    assert on_fields(placed) == {1: 3, 2: 2}
    assert ids(waiting_order(matches=matches, fields=placed)) == [1]


def test_fr093_a_match_sent_back_does_not_take_a_field_in_the_same_request() -> None:
    # Field 2 is free: match 2 waits for Field 1's players. Sending match 1 back
    # frees them, and match 2 takes a field; match 1 itself does not.
    matches = [match(1, on=players(1, 2)), match(2, on=players(1, 3))]

    placed = place_by_hand(
        matches=matches,
        fields=[field(1, mid(1)), field(2)],
        placements=[HandPlacement(match_id=mid(1), field_id=None)],
    )

    assert on_fields(placed) == {1: 2, 2: None}


def test_br133_a_placement_by_hand_ahead_of_the_order_holds() -> None:
    matches = [match(1), match(2), match(3, round_no=4)]

    placed = place_by_hand(
        matches=matches,
        fields=[field(1)],
        placements=[HandPlacement(match_id=mid(3), field_id=fid(1))],
    )
    refilled = fill_fields(matches=matches, fields=placed)

    assert on_fields(placed) == {1: 3}
    assert refilled == ()


def test_br131_a_placement_that_puts_a_player_on_two_fields_is_refused() -> None:
    matches = [match(1, on=players(1, 2)), match(2, on=players(2, 3))]

    with pytest.raises(PlayerOnAnotherFieldError) as raised:
        place_by_hand(
            matches=matches,
            fields=[field(2), field(1, mid(1))],
            placements=[HandPlacement(match_id=mid(2), field_id=fid(2))],
        )

    assert raised.value.player_ids == (PlayerId(UUID(int=10_002)),)
    assert raised.value.field_ids == (fid(1), fid(2))


@pytest.mark.parametrize(
    ("placements", "problem"),
    [
        pytest.param(
            [
                HandPlacement(match_id=mid(2), field_id=fid(2)),
                HandPlacement(match_id=mid(2), field_id=None),
            ],
            "given twice",
            id="match-twice",
        ),
        pytest.param(
            [
                HandPlacement(match_id=mid(2), field_id=fid(2)),
                HandPlacement(match_id=mid(3), field_id=fid(2)),
            ],
            "given twice",
            id="field-twice",
        ),
        pytest.param(
            [HandPlacement(match_id=mid(9), field_id=fid(2))],
            "unknown match",
            id="unknown-match",
        ),
        pytest.param(
            [HandPlacement(match_id=mid(2), field_id=fid(9))],
            "unknown field",
            id="unknown-field",
        ),
        pytest.param(
            [HandPlacement(match_id=mid(4), field_id=fid(2))],
            "cannot be played",
            id="result",
        ),
        pytest.param(
            [HandPlacement(match_id=mid(2), field_id=fid(1))],
            "keeps match",
            id="field-taken",
        ),
    ],
)
def test_adr009_impossible_placements_are_a_caller_bug(
    placements: list[HandPlacement], problem: str
) -> None:
    matches = [match(1), match(2), match(3), match(4, has_result=True)]

    with pytest.raises(ValueError, match=problem):
        place_by_hand(
            matches=matches, fields=[field(1, mid(1)), field(2)], placements=placements
        )


# ---------------------------------------------------------------- an evening


class Evening:
    """Fields and matches changed the way the service changes them (DATA-MODEL §4.6).

    `sent_back` holds the matches the last write sent back to waiting: only
    they may wait while a field is free and their players are not on one.
    `named` holds the matches the last write placed by hand: only they move.
    """

    def __init__(self, matches: list[MatchSlot], field_count: int) -> None:
        self.matches = {m.match_id: m for m in matches}
        self.fields: tuple[FieldSlot, ...] = tuple(
            field(n) for n in range(1, field_count + 1)
        )
        self.sent_back: frozenset[MatchId] = frozenset()
        self.named: frozenset[MatchId] = frozenset()
        self.clock = T0
        self.fill()

    def store(self, fields: tuple[FieldSlot, ...]) -> None:
        before = {f.field_id: f.match_id for f in self.fields}
        for f in fields:
            if f.match_id is not None and before.get(f.field_id) != f.match_id:
                slot = self.matches[f.match_id]
                self.matches[f.match_id] = replace(slot, requeued_at=None)
        self.fields = fields

    def fill(self) -> None:
        placed = {
            p.field_id: p.match_id
            for p in fill_fields(matches=self.matches.values(), fields=self.fields)
        }
        self.store(
            tuple(
                replace(f, match_id=placed.get(f.field_id, f.match_id))
                for f in self.fields
            )
        )
        self.sent_back = frozenset()
        self.named = frozenset()

    def add_field(self) -> None:
        number = next_field_number(f.number for f in self.fields)
        if number is not None:
            self.fields = (*self.fields, field(number))
            self.fill()

    def remove_field(self, number: int) -> None:
        if len(self.fields) == 1:
            return
        removed = next(f for f in self.fields if f.number == number)
        if removed.match_id is not None:
            self.clock += timedelta(minutes=1)
            slot = self.matches[removed.match_id]
            self.matches[removed.match_id] = replace(slot, requeued_at=self.clock)
        self.fields = tuple(f for f in self.fields if f is not removed)
        self.fill()

    def enter_result(self, match_id: MatchId) -> None:
        slot = self.matches[match_id]
        self.matches[match_id] = replace(slot, has_result=True, requeued_at=None)
        self.fields = tuple(
            replace(f, match_id=None) if f.match_id == match_id else f
            for f in self.fields
        )
        self.fill()

    def clear_result(self, match_id: MatchId) -> None:
        self.matches[match_id] = replace(self.matches[match_id], has_result=False)
        self.fill()

    def place(self, placements: list[HandPlacement]) -> None:
        named = {p.match_id for p in placements}
        held = {f.field_id: f.match_id for f in self.fields}
        if any(
            held.get(p.field_id) not in {None, *named}
            for p in placements
            if p.field_id is not None
        ):
            return  # 409 field_not_free in the service
        try:
            placed = place_by_hand(
                matches=self.matches.values(), fields=self.fields, placements=placements
            )
        except PlayerOnAnotherFieldError:
            return
        self.store(placed)
        self.sent_back = frozenset(p.match_id for p in placements if p.field_id is None)
        self.named = frozenset(named)


@st.composite
def evenings(draw: st.DrawFn) -> list[MatchSlot]:
    """A schedule over 8 players, with a few matches whose sides are not known."""
    count = draw(st.integers(min_value=1, max_value=14))
    return [
        match(
            n,
            round_no=draw(st.integers(min_value=1, max_value=4)),
            on=frozenset(
                draw(
                    st.sets(
                        st.integers(min_value=1, max_value=8), min_size=2, max_size=4
                    ).map(lambda numbers: players(*numbers))
                )
            ),
            side_unknown=draw(st.integers(min_value=0, max_value=9)) == 0,
            has_bye=draw(st.integers(min_value=0, max_value=9)) == 0,
        )
        for n in range(1, count + 1)
    ]


def _step(data: st.DataObject, evening: Evening) -> None:
    draw = data.draw
    playable = sorted(
        (
            m.match_id
            for m in evening.matches.values()
            if not m.has_result and not m.has_bye and m.player_ids is not None
        ),
        key=lambda match_id: match_id.int,
    )
    played = sorted(
        (m.match_id for m in evening.matches.values() if m.has_result),
        key=lambda match_id: match_id.int,
    )
    numbers = [f.number for f in evening.fields]
    match draw(st.sampled_from(["add", "remove", "result", "clear", "place"])):
        case "add":
            evening.add_field()
        case "remove":
            evening.remove_field(draw(st.sampled_from(numbers)))
        case "result" if playable:
            evening.enter_result(draw(st.sampled_from(playable)))
        case "clear" if played:
            evening.clear_result(draw(st.sampled_from(played)))
        case "place" if playable:
            chosen = draw(
                st.lists(st.sampled_from(playable), min_size=1, max_size=2, unique=True)
            )
            targets = draw(
                st.lists(
                    st.one_of(
                        st.none(), st.sampled_from([f.field_id for f in evening.fields])
                    ),
                    min_size=len(chosen),
                    max_size=len(chosen),
                ).filter(lambda t: len([f for f in t if f]) == len({f for f in t if f}))
            )
            evening.place(
                [
                    HandPlacement(match_id=m, field_id=f)
                    for m, f in zip(chosen, targets, strict=True)
                ]
            )
        case _:
            pass


def _check_evening(evening: Evening, before: dict[MatchId, FieldId]) -> None:
    on = [evening.matches[f.match_id] for f in evening.fields if f.match_id is not None]
    seen = [player for m in on for player in m.player_ids or ()]
    assert len(seen) == len(set(seen)), "BR-131: a player on two fields"
    assert all(not m.has_result and not m.has_bye and m.player_ids for m in on)
    assert all(m.requeued_at is None for m in on)
    numbers = [f.number for f in evening.fields]
    assert numbers
    assert len(numbers) == len(set(numbers))
    if any(f.match_id is None for f in evening.fields):
        busy = set(seen)
        playable = [
            m.match_id
            for m in waiting_order(
                matches=evening.matches.values(), fields=evening.fields
            )
            if busy.isdisjoint(m.player_ids or ())
        ]
        assert set(playable) <= evening.sent_back, "BR-130: a free field left idle"
    # BR-133: only a placement by hand or a removed field moves a match on a field.
    now = {f.match_id: f.field_id for f in evening.fields if f.match_id is not None}
    kept = {f.field_id for f in evening.fields}
    for match_id, field_id in before.items():
        if match_id in now and field_id in kept and match_id not in evening.named:
            assert now[match_id] == field_id


@settings(max_examples=300)
@given(evenings(), st.integers(min_value=1, max_value=4), st.data())
def test_br130_to_br134_hold_through_any_evening(
    matches: list[MatchSlot], field_count: int, data: st.DataObject
) -> None:
    evening = Evening(matches, field_count)

    for _ in range(data.draw(st.integers(min_value=1, max_value=25))):
        before = {
            f.match_id: f.field_id for f in evening.fields if f.match_id is not None
        }
        _step(data, evening)

        _check_evening(evening, before)


# ---------------------------------------------------------------- knockout sides (D4)


def test_br130_a_match_whose_side_is_no_longer_known_leaves_its_field() -> None:
    # A semifinal result was cleared, so the final on field 1 has a side to come.
    final = match(1, round_no=2, side_unknown=True)

    placements = fill_fields(matches=[final], fields=[field(1, final.match_id)])

    assert placements == (Placement(field_id=fid(1), match_id=None),)


def test_br130_the_field_it_leaves_takes_the_next_waiting_match() -> None:
    final = match(1, round_no=2, side_unknown=True)
    semifinal = match(2, round_no=1)

    placements = fill_fields(
        matches=[final, semifinal], fields=[field(1, final.match_id), field(2)]
    )

    assert placements == (Placement(field_id=fid(1), match_id=semifinal.match_id),)


def test_br133_a_match_whose_sides_changed_but_are_known_keeps_its_field() -> None:
    final = match(1, round_no=2, on=players(1, 7))

    assert fill_fields(matches=[final], fields=[field(1, final.match_id)]) == ()
