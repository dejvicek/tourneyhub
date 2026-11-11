from collections import Counter
from collections.abc import Sequence
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tourneyhub.engine.errors import QualifierCountError
from tourneyhub.engine.ids import EntryId, PlayerId
from tourneyhub.engine.knockout import (
    KNOCKOUT_SEEDING_PURPOSE,
    Bracket,
    BracketMatch,
    FirstRoundMatch,
    MatchKey,
    RoundName,
    Side,
    bracket_of,
    bracket_size,
    cut_standing,
    draw_bracket,
    feeds,
    is_complete,
    knockout_results,
    locked_by,
    match_key,
    play_bracket,
    round_name,
    seed_slots,
)
from tourneyhub.engine.lots import order_by_lot
from tourneyhub.engine.places import PlacingEntry, place_entries
from tourneyhub.engine.tournaments import MatchKind, Outcome

SEED = bytes(range(16))


def eid(n: int) -> EntryId:
    return EntryId(UUID(int=n))


def seeds(count: int) -> list[EntryId]:
    """Entries 1 to `count`; entry n is seed n."""
    return [eid(n) for n in range(1, count + 1)]


def key(round_no: int, position: int, *, third: bool = False) -> MatchKey:
    return MatchKey(round_no=round_no, is_third_place=third, position=position)


def first_round(bracket: Bracket) -> list[tuple[int | None, int | None]]:
    """The first round as seed numbers, None for a bye."""
    return [
        (
            None if match.side_1 is None else match.side_1.int,
            None if match.side_2 is None else match.side_2.int,
        )
        for match in bracket.first_round
    ]


def by_key(matches: Sequence[BracketMatch]) -> dict[MatchKey, BracketMatch]:
    return {match.key: match for match in matches}


def play_all(
    bracket: Bracket, flips: Sequence[bool] = ()
) -> tuple[dict[MatchKey, Outcome], tuple[BracketMatch, ...]]:
    """Enter a result for every match in schedule order; side 2 wins on a flip."""
    flip = iter(flips)
    outcomes: dict[MatchKey, Outcome] = {}
    for match_key_ in bracket.keys:
        match = by_key(play_bracket(bracket, outcomes))[match_key_]
        if match.is_playable:
            outcomes[match_key_] = (
                Outcome.SIDE_2 if next(flip, False) else Outcome.SIDE_1
            )
    return outcomes, play_bracket(bracket, outcomes)


# BR-040: the bracket's size


@pytest.mark.parametrize(
    ("entries", "size"),
    [
        pytest.param(2, 2, id="final-only"),
        pytest.param(3, 4, id="three"),
        pytest.param(7, 8, id="BR-040-seven-to-eight"),
        pytest.param(8, 8, id="eight"),
        pytest.param(9, 16, id="nine"),
        pytest.param(256, 256, id="FR-032-limit"),
    ],
)
def test_br040_the_bracket_is_the_smallest_power_of_two(
    entries: int, size: int
) -> None:
    assert bracket_size(entries) == size


def test_br080_a_bracket_of_one_entry_is_refused() -> None:
    with pytest.raises(ValueError, match="needs 2 entries"):
        bracket_size(1)


# BR-042: seed placement


def test_br042_seed_slots_of_eight() -> None:
    assert seed_slots(8) == (1, 8, 4, 5, 2, 7, 3, 6)


@pytest.mark.parametrize("size", [0, 1, 3, 6, 12])
def test_a_bracket_size_that_is_not_a_power_of_two_is_refused(size: int) -> None:
    with pytest.raises(ValueError, match="power of two"):
        seed_slots(size)


@pytest.mark.parametrize(
    ("round_no", "rounds", "name"),
    [
        pytest.param(1, 1, RoundName.FINAL, id="final-only"),
        pytest.param(2, 3, RoundName.SEMIFINAL, id="semifinal"),
        pytest.param(1, 3, RoundName.QUARTERFINAL, id="quarterfinal"),
        pytest.param(1, 4, RoundName.ROUND_OF_16, id="round-of-16"),
        pytest.param(1, 8, RoundName.ROUND_OF_256, id="round-of-256"),
    ],
)
def test_rounds_are_named_by_the_entries_still_in(
    round_no: int, rounds: int, name: RoundName
) -> None:
    assert round_name(round_no, rounds) is name


@pytest.mark.parametrize(("round_no", "rounds"), [(0, 3), (4, 3), (1, 9)])
def test_a_round_outside_the_bracket_has_no_name(round_no: int, rounds: int) -> None:
    with pytest.raises(ValueError, match="round"):
        round_name(round_no, rounds)


def test_br041_seven_entries_give_seed_1_a_bye() -> None:
    bracket = draw_bracket(seeds(7), third_place_match=False)

    assert bracket.size == 8
    assert first_round(bracket) == [(1, None), (4, 5), (2, 7), (3, 6)]


def test_br041_five_entries_give_the_three_top_seeds_byes() -> None:
    bracket = draw_bracket(seeds(5), third_place_match=True)

    assert first_round(bracket) == [(1, None), (4, 5), (2, None), (3, None)]


def test_br044_the_third_place_match_follows_the_final() -> None:
    bracket = draw_bracket(seeds(4), third_place_match=True)

    assert bracket.keys == (
        key(1, 1),
        key(1, 2),
        key(2, 1),
        key(2, 1, third=True),
    )
    assert bracket.final == key(2, 1)
    assert key(2, 1, third=True).kind is MatchKind.THIRD_PLACE
    assert match_key(round_no=2, kind=MatchKind.STANDARD, position=1) == key(2, 1)


def test_br080_a_third_place_match_needs_four_entries() -> None:
    with pytest.raises(ValueError, match="too few"):
        draw_bracket(seeds(3), third_place_match=True)


def test_an_entry_seeded_twice_is_refused() -> None:
    with pytest.raises(ValueError, match="given twice"):
        draw_bracket([eid(1), eid(1)], third_place_match=False)


@pytest.mark.parametrize(
    ("matches", "message"),
    [
        pytest.param(
            [FirstRoundMatch(position=2, side_1=eid(1), side_2=eid(2))],
            "positions",
            id="positions",
        ),
        pytest.param(
            [
                FirstRoundMatch(position=1, side_1=eid(1), side_2=eid(2)),
                FirstRoundMatch(position=2, side_1=None, side_2=None),
            ],
            "two byes",
            id="bye-against-bye",
        ),
        pytest.param(
            [
                FirstRoundMatch(position=1, side_1=eid(1), side_2=None),
                FirstRoundMatch(position=2, side_1=eid(2), side_2=eid(1)),
            ],
            "given twice",
            id="twice",
        ),
        pytest.param(
            [
                FirstRoundMatch(position=1, side_1=eid(1), side_2=eid(2)),
                FirstRoundMatch(position=2, side_1=eid(3), side_2=eid(4)),
                FirstRoundMatch(position=3, side_1=eid(5), side_2=eid(6)),
            ],
            "power of two",
            id="three-matches",
        ),
    ],
)
def test_a_stored_first_round_that_breaks_br041_is_refused(
    matches: list[FirstRoundMatch], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        bracket_of(matches, third_place_match=False)


def test_a_stored_first_round_with_one_entry_is_refused() -> None:
    with pytest.raises(ValueError, match="too few"):
        bracket_of(
            [FirstRoundMatch(position=1, side_1=eid(1), side_2=None)],
            third_place_match=False,
        )


# D4: later sides derived from winners


def test_d4_later_sides_wait_for_the_earlier_results() -> None:
    bracket = draw_bracket(seeds(4), third_place_match=True)

    matches = by_key(play_bracket(bracket, {}))

    assert matches[key(2, 1)].side_1 == Side(entry_id=None)
    assert not matches[key(2, 1)].side_1.is_known
    assert not matches[key(2, 1)].is_playable
    assert matches[key(1, 1)].is_playable


def test_d4_a_winner_takes_the_side_of_the_next_match() -> None:
    bracket = draw_bracket(seeds(4), third_place_match=True)

    matches = by_key(
        play_bracket(bracket, {key(1, 1): Outcome.SIDE_2, key(1, 2): Outcome.SIDE_1})
    )

    final, third = matches[key(2, 1)], matches[key(2, 1, third=True)]
    assert (final.side_1.entry_id, final.side_2.entry_id) == (eid(4), eid(2))
    assert (third.side_1.entry_id, third.side_2.entry_id) == (eid(1), eid(3))
    assert matches[key(1, 1)].loser == eid(1)


def test_br041_the_entry_against_a_bye_goes_through_without_a_result() -> None:
    bracket = draw_bracket(seeds(3), third_place_match=False)

    matches = by_key(play_bracket(bracket, {}))

    bye = matches[key(1, 1)]
    assert bye.has_bye
    assert not bye.is_playable
    assert bye.winner == eid(1)
    assert bye.loser is None
    assert matches[key(2, 1)].side_1.entry_id == eid(1)
    assert matches[key(2, 1)].side_2.entry_id is None


def test_d4_changing_a_winner_changes_the_later_sides() -> None:
    bracket = draw_bracket(seeds(4), third_place_match=False)
    outcomes = {key(1, 1): Outcome.SIDE_1, key(1, 2): Outcome.SIDE_1}

    before = by_key(play_bracket(bracket, outcomes))[key(2, 1)]
    after = by_key(play_bracket(bracket, {**outcomes, key(1, 1): Outcome.SIDE_2}))[
        key(2, 1)
    ]

    assert before.side_1.entry_id == eid(1)
    assert after.side_1.entry_id == eid(4)


@pytest.mark.parametrize(
    ("outcomes", "message"),
    [
        pytest.param({key(3, 1): Outcome.SIDE_1}, "outside", id="unknown-match"),
        pytest.param({key(1, 1): Outcome.SIDE_1}, "bye", id="bye"),
        pytest.param({key(2, 1): Outcome.SIDE_1}, "not known", id="sides-unknown"),
        pytest.param({key(1, 2): Outcome.DRAW}, "BR-043", id="draw"),
    ],
)
def test_a_result_the_bracket_cannot_hold_is_refused(
    outcomes: dict[MatchKey, Outcome], message: str
) -> None:
    bracket = draw_bracket(seeds(3), third_place_match=False)

    with pytest.raises(ValueError, match=message):
        play_bracket(bracket, outcomes)


# BR-094: the lock


def test_br094_a_semifinal_feeds_the_final_and_the_third_place_match() -> None:
    bracket = draw_bracket(seeds(8), third_place_match=True)

    assert feeds(bracket, key(2, 2)) == (key(3, 1), key(3, 1, third=True))
    assert feeds(bracket, key(1, 3)) == (key(2, 2),)
    assert feeds(bracket, key(3, 1)) == ()
    assert feeds(bracket, key(3, 1, third=True)) == ()


def test_br094_without_a_third_place_match_a_semifinal_feeds_only_the_final() -> None:
    bracket = draw_bracket(seeds(4), third_place_match=False)

    assert feeds(bracket, key(1, 2)) == (key(2, 1),)


def test_br094_a_result_is_locked_by_any_later_match_it_feeds() -> None:
    bracket = draw_bracket(seeds(4), third_place_match=True)
    outcomes = {
        key(1, 1): Outcome.SIDE_1,
        key(1, 2): Outcome.SIDE_1,
        key(2, 1, third=True): Outcome.SIDE_2,
    }

    assert locked_by(bracket, key(1, 1), outcomes) == (key(2, 1, third=True),)
    assert locked_by(bracket, key(2, 1, third=True), outcomes) == ()
    assert locked_by(bracket, key(1, 2), {key(1, 2): Outcome.SIDE_1}) == ()


def test_br094_a_match_outside_the_bracket_is_refused() -> None:
    bracket = draw_bracket(seeds(4), third_place_match=False)

    with pytest.raises(ValueError, match="not in the bracket"):
        feeds(bracket, key(2, 1, third=True))


# FR-037 and BR-102: the end of the knockout


def test_fr037_the_knockout_ends_with_its_last_result() -> None:
    bracket = draw_bracket(seeds(4), third_place_match=True)
    outcomes, matches = play_all(bracket)

    without_third = {k: v for k, v in outcomes.items() if not k.is_third_place}

    assert is_complete(matches)
    assert not is_complete(play_bracket(bracket, without_third))


def test_br102_byes_give_no_result() -> None:
    bracket = draw_bracket(seeds(3), third_place_match=False)
    _, matches = play_all(bracket)

    results = knockout_results(matches)

    assert [(r.round_no, r.winner_id.int, r.loser_id.int) for r in results] == [
        (1, 2, 3),
        (2, 1, 2),
    ]


# BR-080, BR-085, BR-074: the cut


def test_br085_the_best_entries_go_through_seeded_by_their_place() -> None:
    cut = cut_standing(
        [(eid(3),), (eid(1),), (eid(2),), (eid(4),)],
        qualifiers=3,
        third_place_match=False,
        rng_seed=SEED,
    )

    assert cut.seeds == (eid(3), eid(1), eid(2))
    assert cut.decided_by_lot == frozenset()
    assert not cut.is_cut_by_lot


def test_br074_a_cut_through_a_tie_is_decided_by_lot() -> None:
    tied = (eid(2), eid(3), eid(4))

    cut = cut_standing(
        [(eid(1),), tied, (eid(5),)],
        qualifiers=2,
        third_place_match=False,
        rng_seed=SEED,
    )

    drawn = order_by_lot(tied, rng_seed=SEED, purpose=KNOCKOUT_SEEDING_PURPOSE)
    assert cut.seeds == (eid(1), drawn[0])
    assert cut.decided_by_lot == {drawn[0]}
    assert cut.is_cut_by_lot


def test_br080_disabled_entries_do_not_go_through() -> None:
    cut = cut_standing(
        [(eid(1),), (eid(2),), (eid(3),), (eid(4),)],
        qualifiers=2,
        third_place_match=False,
        rng_seed=SEED,
        disabled=[eid(2), eid(4)],
    )

    assert cut.seeds == (eid(1), eid(3))
    assert cut.skipped == (eid(2),)


@pytest.mark.parametrize(
    ("qualifiers", "third_place", "minimum"),
    [
        pytest.param(1, False, 2, id="one"),
        pytest.param(3, True, 4, id="three-with-third-place"),
        pytest.param(6, False, 2, id="more-than-the-entries"),
    ],
)
def test_br080_a_qualifier_count_out_of_range_is_refused(
    *, qualifiers: int, third_place: bool, minimum: int
) -> None:
    with pytest.raises(QualifierCountError) as raised:
        cut_standing(
            [(eid(n),) for n in range(1, 6)],
            qualifiers=qualifiers,
            third_place_match=third_place,
            rng_seed=SEED,
        )

    assert (raised.value.minimum, raised.value.maximum) == (minimum, 5)
    assert raised.value.given == qualifiers


def test_a_cut_of_an_entry_twice_is_refused() -> None:
    with pytest.raises(ValueError, match="given twice"):
        cut_standing(
            [(eid(1),), (eid(1),)], qualifiers=2, third_place_match=False, rng_seed=SEED
        )


def test_a_disabled_entry_outside_the_standing_is_refused() -> None:
    with pytest.raises(ValueError, match="disabled"):
        cut_standing(
            [(eid(1),), (eid(2),)],
            qualifiers=2,
            third_place_match=False,
            rng_seed=SEED,
            disabled=[eid(9)],
        )


# Properties

entry_counts = st.integers(min_value=2, max_value=64)


@given(count=entry_counts, third_place=st.booleans())
def test_br040_every_entry_is_placed_exactly_once(
    count: int, third_place: bool
) -> None:
    bracket = draw_bracket(seeds(count), third_place_match=third_place and count >= 4)

    placed = Counter(
        side
        for match in bracket.first_round
        for side in (match.side_1, match.side_2)
        if side is not None
    )

    assert sorted(placed) == seeds(count)
    assert set(placed.values()) == {1}


@given(count=entry_counts)
def test_br041_byes_only_in_round_1_and_only_for_the_top_seeds(count: int) -> None:
    bracket = draw_bracket(seeds(count), third_place_match=False)

    with_bye = [
        (match.side_1 or match.side_2)
        for match in bracket.first_round
        if match.side_1 is None or match.side_2 is None
    ]

    assert sorted(entry.int for entry in with_bye if entry) == list(
        range(1, bracket.size - count + 1)
    )
    assert all(
        not match.has_bye
        for match in play_bracket(bracket, {})
        if match.key.round_no > 1
    )


@given(count=st.integers(min_value=4, max_value=64))
def test_br042_the_top_seeds_meet_as_late_as_possible(count: int) -> None:
    bracket = draw_bracket(seeds(count), third_place_match=False)
    spot = {
        side.int: 2 * index + offset
        for index, match in enumerate(bracket.first_round)
        for offset, side in enumerate((match.side_1, match.side_2))
        if side is not None
    }

    halves = {spot[seed] * 2 // bracket.size for seed in (1, 2)}
    quarters = {spot[seed] * 4 // bracket.size for seed in (1, 2, 3, 4)}

    assert len(halves) == 2
    assert len(quarters) == 4


@given(count=entry_counts, third_place=st.booleans(), data=st.data())
def test_d4_the_winner_derivation_is_consistent(
    count: int, third_place: bool, data: st.DataObject
) -> None:
    bracket = draw_bracket(seeds(count), third_place_match=third_place and count >= 4)
    flips = data.draw(st.lists(st.booleans(), max_size=2 * count))
    _, matches = play_all(bracket, flips)
    played = by_key(matches)

    for match in matches:
        assert match.winner is not None
        if match.key.round_no == 1:
            continue
        take_loser = match.key.is_third_place
        position = 1 if take_loser else 2 * match.key.position - 1
        upper = played[key(match.key.round_no - 1, position)]
        lower = played[key(match.key.round_no - 1, position + 1)]
        expected = (
            (upper.loser, lower.loser) if take_loser else (upper.winner, lower.winner)
        )
        assert (match.side_1.entry_id, match.side_2.entry_id) == expected
        assert match.winner in expected


@given(count=entry_counts, third_place=st.booleans(), data=st.data())
def test_br102_places_partition_the_entries(
    count: int, third_place: bool, data: st.DataObject
) -> None:
    has_third_place = third_place and count >= 4
    bracket = draw_bracket(seeds(count), third_place_match=has_third_place)
    flips = data.draw(st.lists(st.booleans(), max_size=2 * count))
    _, matches = play_all(bracket, flips)

    places = place_entries(
        [
            PlacingEntry(entry_id=entry, player_ids=(PlayerId(entry),))
            for entry in seeds(count)
        ],
        knockout=knockout_results(matches),
        third_place_match=has_third_place,
    )

    assert sorted(place.entry_id for place in places) == seeds(count)
    winner = by_key(matches)[bracket.final].winner
    assert [place.entry_id for place in places if place.place == 1] == [winner]


@given(count=entry_counts, third_place=st.booleans(), data=st.data())
def test_br094_a_result_is_locked_exactly_while_a_match_it_feeds_has_one(
    count: int, third_place: bool, data: st.DataObject
) -> None:
    bracket = draw_bracket(seeds(count), third_place_match=third_place and count >= 4)
    flips = data.draw(st.lists(st.booleans(), max_size=2 * count))
    outcomes, _ = play_all(bracket, flips)
    kept = data.draw(st.sets(st.sampled_from(sorted(outcomes))))
    partial = {k: outcomes[k] for k in sorted(kept)}

    for match_key_ in bracket.keys:
        locks = locked_by(bracket, match_key_, partial)
        assert set(locks) == set(feeds(bracket, match_key_)) & set(partial)
