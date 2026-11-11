"""Swiss: standings, the draw of each round and the recommended rounds.

Covers BR-055 to BR-058, BR-068 and BR-070 to BR-074. The pairing follows
ADR-011: BR-056 as written, and a minimum-cost matching over a widening window
when BR-056 gets stuck.
"""

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from tourneyhub.engine.errors import NotEnoughEntriesError
from tourneyhub.engine.ids import EntryId, ensure_distinct
from tourneyhub.engine.lots import lot_digest
from tourneyhub.engine.matching import Pair, min_cost_matching
from tourneyhub.engine.results import POINTS, Result, result_for, tiebreak_purpose
from tourneyhub.engine.tournaments import MatchOutcome, Tiebreaker

PAIRING_WINDOW = 16
"""How far apart, among the entries that play, the fallback first pairs (ADR-011)."""

MINIMUM_ENTRIES = 2
"""The fewest entries that can play a round (FR-032)."""


class PairingMethod(StrEnum):
    """How a round's pairs were found (BR-055, BR-056, ADR-011)."""

    SEEDS = "seeds"
    """Round 1: the top half of the seeds against the bottom half (BR-055)."""

    NEIGHBOURS = "neighbours"
    """Each entry against the next one below it that it has not played (BR-056)."""

    MATCHING = "matching"
    """BR-056 got stuck: a minimum-cost matching of the whole field (ADR-011)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SwissMatch:
    """One match of a Swiss round (DATA-MODEL `matches`, D11).

    Attributes:
        side_1: The entry on side 1.
        side_2: The entry on side 2.
        outcome: The result, or `None` while there is none. Only a match with
            a result counts for points, opponents and score difference.
        score_difference: Side 1's goals minus side 2's, over the games that
            have a score (BR-073); 0 for a walkover.
    """

    side_1: EntryId
    side_2: EntryId
    outcome: MatchOutcome | None = None
    score_difference: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class SwissRound:
    """One round of a Swiss: its matches and who sat out (DATA-MODEL D5).

    Entries in neither did not play the round because they were disabled or
    had not joined yet; such a round earns them nothing and is not a sit-out
    (BR-064, BR-067).

    Attributes:
        round_no: 1 for the first round.
        matches: The round's matches.
        sat_out: The entry that sat out (BR-058), if any.
    """

    round_no: int
    matches: tuple[SwissMatch, ...]
    sat_out: tuple[EntryId, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class SwissStanding:
    """One entry's line in the Swiss standings (FR-060, BR-070 to BR-074).

    Attributes:
        entry_id: The entry.
        position: The strict order, 1 to n, used to pair the next round and
            to choose who sits out; the lot decides between entries that
            share a place (BR-074).
        place: The shown place: entries level on points and on every enabled
            tie-breaker share the position of the best of them (BR-074).
        points: Points from results and sit-outs (BR-070, BR-071).
        bh1: The sum of the points of every opponent, once per match (BR-073).
        bh2: The sum of those opponents' BH1, once per match (BR-073).
        score_difference: Goals for minus goals against, entered scores only
            (BR-073).
        played: Matches with a result.
        won: Matches won.
        drawn: Matches drawn.
        lost: Matches lost.
        sat_out: Rounds the entry sat out (BR-058); missed rounds of a
            disabled or late entry do not count (BR-064, BR-067).
        is_decided_by_lot: The entry shares its place, so the lot decided its
            position (ADR-009).
    """

    entry_id: EntryId
    position: int
    place: int
    points: int
    bh1: int
    bh2: int
    score_difference: int
    played: int
    won: int
    drawn: int
    lost: int
    sat_out: int
    is_decided_by_lot: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class SwissPair:
    """One match of a drawn round (BR-055 to BR-057).

    Attributes:
        side_1: The higher-placed entry, or the higher seed in round 1.
        side_2: Its opponent.
        is_repeat: The two have met before; only when no pairing without a
            repeat exists (BR-057, ADR-011).
        is_decided_by_lot: The lot decided the position of either entry in
            the standing the pair was drawn from (BR-074, ADR-009).
    """

    side_1: EntryId
    side_2: EntryId
    is_repeat: bool
    is_decided_by_lot: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class SwissDraw:
    """A drawn Swiss round (FR-035, FR-040, FR-042).

    Attributes:
        round_no: The new round's number.
        pairs: The matches, in the order of their higher-placed side.
        sitting_out: The entry that sits out, with an odd number of entries
            playing (BR-058).
        is_sit_out_by_lot: The lot decided which entry sits out: another
            candidate with as few sit-outs shares its place (ADR-009).
        method: How the pairs were found.
    """

    round_no: int
    pairs: tuple[SwissPair, ...]
    sitting_out: EntryId | None
    is_sit_out_by_lot: bool
    method: PairingMethod


def recommended_minimum_rounds(entry_count: int) -> int:
    """Return the recommended minimum number of rounds (BR-068, FR-040).

    It is log₂ of the number of entries, rounded up: 5 to 8 entries give 3
    rounds, 9 to 16 give 4, 17 to 32 give 5. Count the entries the tournament has
    now, late entries included once they have joined; the organizer may stop
    earlier or play on.

    Raises:
        ValueError: `entry_count` is negative.
    """
    if entry_count < 0:
        msg = f"entry count {entry_count} is negative"
        raise ValueError(msg)
    return max(entry_count - 1, 0).bit_length()


def swiss_standings(
    entry_ids: Iterable[EntryId],
    rounds: Iterable[SwissRound],
    *,
    tiebreakers: Sequence[Tiebreaker],
    sit_out_points: int,
    rng_seed: bytes,
) -> tuple[SwissStanding, ...]:
    """Compute the Swiss standings (BR-070 to BR-074, FR-043, FR-060).

    A win earns 2 points, a draw 1 and a loss 0 (BR-070); a sit-out earns
    `sit_out_points`, 0 or 1 (BR-071). Entries are ordered by points, then by
    `tiebreakers`: the enabled tie-breakers in the organizer's order, each
    higher first (BR-072, FR-043). BH1 sums the current points of every
    opponent, once per match, and BH2 sums those opponents' BH1; sit-outs add
    nothing to either (BR-073). Entries still level share the place, and the
    lot `tiebreak:after-round-<n>` gives them a strict position, where `n`
    counts the rounds whose every match has a result (BR-074, ADR-010).

    Pass every entry of the phase, disabled and late ones included: their
    results and points stay, and they are placed by their standing (BR-064,
    BR-067). A match without a result counts for nothing yet.

    Returns:
        One line per entry, by position.

    Raises:
        ValueError: A caller bug: an entry or a tie-breaker is given twice,
            `sit_out_points` is not 0 or 1, or the rounds are not valid (see
            `draw_next_swiss_round`).
    """
    ids = tuple(entry_ids)
    ensure_distinct(ids)
    played_rounds = _checked_rounds(ids, rounds)
    order = tuple(tiebreakers)
    if len(set(order)) != len(order):
        msg = f"tie-breakers {order} name one twice"
        raise ValueError(msg)
    if sit_out_points not in {0, 1}:
        msg = f"sit-out points must be 0 or 1, got {sit_out_points}"
        raise ValueError(msg)

    points: Counter[EntryId] = Counter()
    results: dict[EntryId, Counter[Result]] = {id_: Counter() for id_ in ids}
    difference: Counter[EntryId] = Counter()
    sat_out: Counter[EntryId] = Counter()
    opponents: dict[EntryId, list[EntryId]] = {id_: [] for id_ in ids}
    for round_ in played_rounds:
        for entry_id in round_.sat_out:
            sat_out[entry_id] += 1
            points[entry_id] += sit_out_points
        for match in round_.matches:
            if match.outcome is None:
                continue
            for entry_id, opponent, own, goals in (
                (match.side_1, match.side_2, MatchOutcome.SIDE_1, 1),
                (match.side_2, match.side_1, MatchOutcome.SIDE_2, -1),
            ):
                result = result_for(match.outcome, own)
                results[entry_id][result] += 1
                points[entry_id] += POINTS[result]
                difference[entry_id] += goals * match.score_difference
                opponents[entry_id].append(opponent)
    bh1 = {id_: sum(points[other] for other in opponents[id_]) for id_ in ids}
    bh2 = {id_: sum(bh1[other] for other in opponents[id_]) for id_ in ids}
    values: dict[Tiebreaker, Callable[[EntryId], int]] = {
        Tiebreaker.BH1: bh1.__getitem__,
        Tiebreaker.BH2: bh2.__getitem__,
        Tiebreaker.SCORE_DIFFERENCE: difference.__getitem__,
    }

    def criteria(entry_id: EntryId) -> tuple[int, ...]:
        return (-points[entry_id], *(-values[key](entry_id) for key in order))

    purpose = tiebreak_purpose(
        sum(
            all(match.outcome is not None for match in round_.matches)
            for round_ in played_rounds
        )
    )
    ordered = sorted(
        ids,
        key=lambda entry_id: (
            criteria(entry_id),
            lot_digest(rng_seed=rng_seed, purpose=purpose, candidate=entry_id),
        ),
    )
    ties = Counter(criteria(entry_id) for entry_id in ids)
    places: dict[tuple[int, ...], int] = {}
    for position, entry_id in enumerate(ordered, start=1):
        places.setdefault(criteria(entry_id), position)
    return tuple(
        SwissStanding(
            entry_id=entry_id,
            position=position,
            place=places[criteria(entry_id)],
            points=points[entry_id],
            bh1=bh1[entry_id],
            bh2=bh2[entry_id],
            score_difference=difference[entry_id],
            played=len(opponents[entry_id]),
            won=results[entry_id][Result.WON],
            drawn=results[entry_id][Result.DRAWN],
            lost=results[entry_id][Result.LOST],
            sat_out=sat_out[entry_id],
            is_decided_by_lot=ties[criteria(entry_id)] > 1,
        )
        for position, entry_id in enumerate(ordered, start=1)
    )


def draw_first_swiss_round(seeds: Sequence[EntryId]) -> SwissDraw:
    """Draw round 1 of a Swiss from the seeds (BR-055, BR-058).

    With an odd number of entries the lowest seed sits out: before any
    result the seeds are the standing, and nobody has sat out yet (BR-058).
    The others play top half against bottom half: with 8 entries 1 v 5,
    2 v 6, 3 v 7 and 4 v 8 (BR-055).

    Args:
        seeds: Every entry, seed 1 first.

    Raises:
        NotEnoughEntriesError: Fewer than 2 entries.
        ValueError: An entry is given twice.
    """
    ids = tuple(seeds)
    ensure_distinct(ids)
    if len(ids) < MINIMUM_ENTRIES:
        raise NotEnoughEntriesError(minimum=MINIMUM_ENTRIES, given=len(ids))
    sitting_out = ids[-1] if len(ids) % 2 else None
    playing = ids if sitting_out is None else ids[:-1]
    half = len(playing) // 2
    return SwissDraw(
        round_no=1,
        pairs=tuple(
            SwissPair(
                side_1=playing[index],
                side_2=playing[half + index],
                is_repeat=False,
                is_decided_by_lot=False,
            )
            for index in range(half)
        ),
        sitting_out=sitting_out,
        is_sit_out_by_lot=False,
        method=PairingMethod.SEEDS,
    )


def draw_next_swiss_round(
    standings: Iterable[SwissStanding],
    rounds: Iterable[SwissRound],
    *,
    disabled: Iterable[EntryId] = (),
) -> SwissDraw:
    """Draw the next round of a Swiss from the standings (BR-056 to BR-058, ADR-011).

    1. **Who plays.** Disabled entries are left out (BR-064). With an odd
       number left, the lowest-placed of those who have sat out the fewest
       times sits out (BR-058), by `position`, so the lot breaks a tie.
    2. **BR-056.** Top-down, each unpaired entry plays the next entry below
       it that it has not played. If that pairs everyone, it is the draw.
    3. **Fallback (ADR-011).** If BR-056 gets stuck, the whole field is
       paired by a minimum-cost perfect matching, where a pair costs the
       square of how many places apart the two are among the entries that
       play, times how many entries are at or below the upper one, so the
       top of the standings is kept first. Only pairs that have not met and are at most 16 apart are
       allowed; while no perfect matching exists the window doubles (32, 64,
       ...) up to the whole field. If even the whole field has none, pairs
       that have met are allowed, and the matching first has as few pairs
       that have met as possible (BR-057), then as few earlier meetings
       among them (a pair that met once over a pair that met twice), then
       the lowest cost above.

    The result depends only on the standing and on who has met whom, so it
    is the same for the same seed and round.

    Args:
        standings: The current standings from `swiss_standings`, of every
            entry, after every match of `rounds` has a result (FR-040).
        rounds: Every round played so far, at least round 1.
        disabled: The entries disabled now (FR-044).

    Raises:
        NotEnoughEntriesError: Fewer than 2 entries are not disabled.
        ValueError: A caller bug: an entry is given twice, the positions are
            not 1 to n, there is no round yet (use `draw_first_swiss_round`),
            the round numbers are not 1 to n, an entry plays twice in a
            round or is unknown, a match has no result, or a disabled entry
            is unknown.
    """
    table = tuple(sorted(standings, key=lambda line: line.position))
    ids = tuple(line.entry_id for line in table)
    ensure_distinct(ids)
    if [line.position for line in table] != list(range(1, len(table) + 1)):
        msg = "the standing's positions are not 1 to n"
        raise ValueError(msg)
    played_rounds = _checked_rounds(ids, rounds)
    if not played_rounds:
        msg = "round 1 is drawn from the seeds"
        raise ValueError(msg)
    for round_ in played_rounds:
        if any(match.outcome is None for match in round_.matches):
            msg = f"round {round_.round_no} has a match without a result"
            raise ValueError(msg)
    off = set(disabled)
    if not off <= set(ids):
        msg = f"disabled entries {off - set(ids)} are not in the standing"
        raise ValueError(msg)

    active = [line for line in table if line.entry_id not in off]
    if len(active) < MINIMUM_ENTRIES:
        raise NotEnoughEntriesError(minimum=MINIMUM_ENTRIES, given=len(active))
    sitting: SwissStanding | None = None
    is_sit_out_by_lot = False
    if len(active) % 2:
        fewest = min(line.sat_out for line in active)
        candidates = [line for line in active if line.sat_out == fewest]
        sitting = candidates[-1]
        is_sit_out_by_lot = any(line.place == sitting.place for line in candidates[:-1])
    playing = [line for line in active if line is not sitting]

    index = {line.entry_id: number for number, line in enumerate(playing)}
    met = Counter(
        (
            min(index[match.side_1], index[match.side_2]),
            max(index[match.side_1], index[match.side_2]),
        )
        for round_ in played_rounds
        for match in round_.matches
        if match.side_1 in index and match.side_2 in index
    )
    pairs = _pair_neighbours(len(playing), met)
    method = PairingMethod.NEIGHBOURS
    if pairs is None:
        pairs = _pair_by_matching(len(playing), met)
        method = PairingMethod.MATCHING
    return SwissDraw(
        round_no=len(played_rounds) + 1,
        pairs=tuple(
            SwissPair(
                side_1=playing[top].entry_id,
                side_2=playing[bottom].entry_id,
                is_repeat=(top, bottom) in met,
                is_decided_by_lot=(
                    playing[top].is_decided_by_lot or playing[bottom].is_decided_by_lot
                ),
            )
            for top, bottom in pairs
        ),
        sitting_out=None if sitting is None else sitting.entry_id,
        is_sit_out_by_lot=is_sit_out_by_lot,
        method=method,
    )


def _checked_rounds(
    entry_ids: Sequence[EntryId], rounds: Iterable[SwissRound]
) -> tuple[SwissRound, ...]:
    """Return the rounds by number, refusing what no valid Swiss can hold."""
    ordered = tuple(sorted(rounds, key=lambda round_: round_.round_no))
    if [round_.round_no for round_ in ordered] != list(range(1, len(ordered) + 1)):
        msg = "the round numbers are not 1 to n"
        raise ValueError(msg)
    known = set(entry_ids)
    for round_ in ordered:
        present = [
            *round_.sat_out,
            *(
                side
                for match in round_.matches
                for side in (match.side_1, match.side_2)
            ),
        ]
        ensure_distinct(present)
        if not known.issuperset(present):
            msg = f"round {round_.round_no} has entries that are not given"
            raise ValueError(msg)
    return ordered


def _pair_neighbours(count: int, met: Counter[Pair]) -> tuple[Pair, ...] | None:
    """Pair top-down with the next entry below that has not been met (BR-056)."""
    unpaired = list(range(count))
    pairs: list[Pair] = []
    while unpaired:
        top = unpaired.pop(0)
        bottom = next((other for other in unpaired if (top, other) not in met), None)
        if bottom is None:
            return None
        unpaired.remove(bottom)
        pairs.append((top, bottom))
    return tuple(pairs)


def _pair_cost(count: int, top: int, bottom: int) -> int:
    """Return the cost of a pair: far apart is dear, and more so near the top.

    The weight `count - top` makes a change at the top of the standings cost
    more than the same change further down, so the fallback keeps "1st v 2nd"
    when a draw without repeats allows it (BR-056).
    """
    return (bottom - top) ** 2 * (count - top)


def _pair_by_matching(count: int, met: Counter[Pair]) -> tuple[Pair, ...]:
    """Pair the whole field by a minimum-cost matching (ADR-011)."""
    window = PAIRING_WINDOW
    while True:
        pairs = min_cost_matching(
            count,
            (
                (top, bottom, _pair_cost(count, top, bottom))
                for top in range(count)
                for bottom in range(top + 1, min(count, top + window + 1))
                if (top, bottom) not in met
            ),
        )
        if 2 * len(pairs) == count:
            return pairs
        if window >= count - 1:
            break
        window *= 2
    return min_cost_matching(count, _repeat_costs(count, met))


def _repeat_costs(count: int, met: Counter[Pair]) -> Iterable[tuple[int, int, int]]:
    """Cost every pair so a matching is ranked by three keys in turn (BR-057).

    1. The fewest pairs that have met: a repeat pair costs `pair_weight`.
    2. Then the fewest earlier meetings among those pairs: each costs
       `meeting_weight`, so one pair that met once beats one that met twice.
    3. Then `_pair_cost`, the distance in the standings.

    Each weight is more than the most the lower keys can add up to over a
    whole matching, so a key decides only when the keys before it are equal.
    A matching has `count // 2` pairs of distance cost at most
    `(count - 1) ** 2 * count` each, and at most every earlier meeting among
    its pairs. The weights grow with `count` and the history, so the order
    holds for any field size; the costs stay whole numbers, without ties
    from rounding.
    """
    distance_bound = count // 2 * (count - 1) ** 2 * count
    meeting_weight = distance_bound + 1
    pair_weight = meeting_weight * sum(met.values()) + distance_bound + 1
    for top in range(count):
        for bottom in range(top + 1, count):
            times = met[(top, bottom)]
            repeat = pair_weight + meeting_weight * times if times else 0
            yield top, bottom, repeat + _pair_cost(count, top, bottom)
