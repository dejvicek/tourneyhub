"""The Lord have mercy re-mix: later rounds, replacements, the lock, places.

In a Lord have mercy knockout (BR-084) the pairs change every round. Round 1
is drawn when the knockout starts (`monster_dyp.select_monster_knockout`);
every later round is drawn here, once the round before is complete, from the
players who went through (BR-140, BR-141). A disabled player who is still in
has left and is replaced in the next draw by the best-placed player who is
knocked out (BR-147, BR-148), or stays in the draw when nobody is available
(BR-149); `plan_replacements` decides who, for the organizer's preview and
for the draw alike. Places are per player, and a player who was replaced
takes the place their replacement gave up (BR-145, BR-151).

BR-140 to BR-149, BR-151 to BR-157, FR-037, FR-049.
"""

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from tourneyhub.engine.ids import EntryId, PlayerId, ensure_distinct
from tourneyhub.engine.knockout import (
    MatchKey,
    bracket_size,
    minimum_qualifiers,
    seed_slots,
)
from tourneyhub.engine.lots import order_by_lot
from tourneyhub.engine.monster_dyp import Team
from tourneyhub.engine.places import PlacingEntry
from tourneyhub.engine.season_points import PlayerPoints, shared_place_points
from tourneyhub.engine.tournaments import MonsterKnockoutMode, Outcome

THIRD_PLACE_PURPOSE = f"{MonsterKnockoutMode.LORD_HAVE_MERCY.value}:third-place"
"""The lot of the third-place match's draw (BR-144, BR-156, ADR-010).

It is its own lot, so the final and the third-place match, drawn together,
do not share one. It holds no draw counter: the same four semifinal losers
always give the same pairs.
"""


REPLACEMENT_PURPOSE = f"{MonsterKnockoutMode.LORD_HAVE_MERCY.value}:replacement"
"""The lot of the replacements' ties (BR-148, BR-074, ADR-010).

It orders the candidates level on the round they were knocked out in and on
their group-phase standing, and the players who left level on their
standing. It holds no draw counter and no round, so the same knockout and
the same disabled players always give the same plan (BR-156).
"""


def remix_purpose(round_no: int) -> str:
    """Name the lot of round `round_no`'s draw, `lord_have_mercy:round-<r>` (BR-156).

    The purpose holds no draw counter, so drawing a round again from the same
    players gives the same pairs and matches (BR-146). Round 1's lot,
    `lord_have_mercy:<draw counter>` (BR-084), never has this form.

    Raises:
        ValueError: `round_no` is below 2; round 1 is drawn when the knockout
            starts.
    """
    if round_no < 2:  # noqa: PLR2004
        msg = f"round {round_no} is not a re-mixed round"
        raise ValueError(msg)
    return f"{MonsterKnockoutMode.LORD_HAVE_MERCY.value}:round-{round_no}"


@dataclass(frozen=True, slots=True, kw_only=True)
class Replacement:
    """A player who came into a draw in place of a player who left (BR-148).

    Attributes:
        player_id: The replacement, a player who was knocked out.
        replaced_player_id: The player who left and was replaced.
    """

    player_id: PlayerId
    replaced_player_id: PlayerId


@dataclass(frozen=True, slots=True, kw_only=True)
class RemixMatch:
    """A stored match of a Lord have mercy knockout.

    Attributes:
        key: Where the match sits: its round, position, and whether it is the
            third-place match.
        side_1: The pair on side 1, or None for a bye (round 1 only, BR-041).
        side_2: The pair on side 2, the same.
        outcome: The stored result, None without one; a bye has none.
        replacements: The match's players who came in as replacements, and
            for whom (BR-148, BR-155), by the replacement's id; never in
            round 1 (BR-152).
    """

    key: MatchKey
    side_1: Team | None
    side_2: Team | None
    outcome: Outcome | None = None
    replacements: tuple[Replacement, ...] = ()

    @property
    def has_bye(self) -> bool:
        """A side is a bye, so the match is not played (BR-041)."""
        return self.side_1 is None or self.side_2 is None

    @property
    def is_decided(self) -> bool:
        """The match has a result, or a bye: who goes through is known."""
        return self.has_bye or self.outcome is not None

    @property
    def players(self) -> tuple[PlayerId, ...]:
        """The match's players, side 1 first."""
        return tuple(
            player_id
            for side in (self.side_1, self.side_2)
            if side is not None
            for player_id in side
        )

    @property
    def winner(self) -> Team | None:
        """The pair that went through: the result's winner or the pair against a bye."""
        if self.side_1 is None or self.side_2 is None:
            return self.side_2 if self.side_1 is None else self.side_1
        if self.outcome is None:
            return None
        return self.side_1 if self.outcome is Outcome.SIDE_1 else self.side_2

    @property
    def loser(self) -> Team | None:
        """The pair that lost the result; None for a bye or without a result."""
        if self.has_bye or self.outcome is None:
            return None
        return self.side_2 if self.outcome is Outcome.SIDE_1 else self.side_1


@dataclass(frozen=True, slots=True, kw_only=True)
class RemixState:
    """A checked Lord have mercy knockout as it stands (BR-140 to BR-147).

    Build it with `remix_state`, which checks the stored matches.

    Attributes:
        size: The bracket's size: twice the round-1 matches, a power of two.
        third_place_match: The knockout has a third-place match (BR-044).
        rounds: The drawn rounds, round 1 first; each in schedule order, the
            standard matches by position and the third-place match after the
            final (BR-130).
    """

    size: int
    third_place_match: bool
    rounds: tuple[tuple[RemixMatch, ...], ...]

    @property
    def round_count(self) -> int:
        """The bracket's number of rounds; the last holds the final."""
        return self.size.bit_length() - 1

    @property
    def rounds_drawn(self) -> int:
        """How many rounds are drawn: 1 once the knockout has started."""
        return len(self.rounds)

    @property
    def matches(self) -> tuple[RemixMatch, ...]:
        """Every drawn match in schedule order (BR-130)."""
        return tuple(match for round_ in self.rounds for match in round_)

    @property
    def newest_round(self) -> tuple[RemixMatch, ...]:
        """The matches of the newest round, the final's with the third-place match."""
        return self.rounds[-1]

    @property
    def players(self) -> frozenset[PlayerId]:
        """Every player of the knockout: the players of round 1."""
        return frozenset(
            player_id for match in self.rounds[0] for player_id in match.players
        )

    @property
    def is_complete(self) -> bool:
        """The knockout is over (FR-037).

        The final's round is drawn, the final has a result and, with a
        third-place match, that match too. Later rounds do not exist until
        they are drawn, so a result for every existing match is not enough.
        """
        return self.rounds_drawn == self.round_count and all(
            match.outcome is not None for match in self.newest_round
        )

    @property
    def can_draw_next(self) -> bool:
        """The organizer can draw the next round (BR-140).

        Every match of the newest round has a result, byes aside, and the
        newest round is not the final's.
        """
        return self.rounds_drawn < self.round_count and all(
            match.is_decided for match in self.newest_round
        )

    @property
    def going_through(self) -> frozenset[PlayerId]:
        """The players who went through from the newest round so far (BR-141).

        The players of its winning pairs and, in round 1, of the pairs with a
        bye. A match without a result adds nobody yet; the third-place match
        leads nowhere and adds nobody.
        """
        return _going_through(self.newest_round)

    @property
    def semifinal_losers(self) -> frozenset[PlayerId]:
        """The players of the pairs that lost a semifinal so far (BR-144).

        Empty while the semifinals are not drawn, and in a knockout of 2
        pairs, which has none.
        """
        semifinal = self.round_count - 1
        if not 1 <= semifinal <= self.rounds_drawn:
            return frozenset()
        return _losers(self.rounds[semifinal - 1])

    @property
    def replaced(self) -> frozenset[PlayerId]:
        """The players a replacement was drawn in place of (BR-148, BR-153)."""
        return frozenset(
            replacement.replaced_player_id
            for match in self.matches
            for replacement in match.replacements
        )

    @property
    def still_in(self) -> frozenset[PlayerId]:
        """The players still in the knockout (BR-147).

        A player is still in when their latest pair won its match or had a
        bye, or its match has no result yet. With a third-place match, the
        semifinal losers are also still in until that match has a result. A
        player who was replaced is not still in, whatever their pair did
        (BR-153). Every other player of the knockout is knocked out.

        A pair that won the final or the third-place match also "won its
        match" and so counts as still in; nothing is drawn after those
        matches, so this decides nothing.
        """
        latest = _last_matches(self.matches)
        waiting = (
            self.semifinal_losers
            if self.third_place_match and self.rounds_drawn < self.round_count
            else frozenset()
        )
        return (
            frozenset(
                player_id
                for player_id, match in latest.items()
                if match.outcome is None
                or player_id in (match.winner or ())
                or player_id in waiting
            )
            - self.replaced
        )

    @property
    def knocked_out(self) -> frozenset[PlayerId]:
        """The knockout's players who are knocked out and were never replaced.

        These are the players a replacement can be picked from (BR-147,
        BR-148, BR-153); a player who was replaced is neither still in nor
        here.
        """
        return self.players - self.still_in - self.replaced

    @property
    def next_pools(self) -> tuple[frozenset[PlayerId], frozenset[PlayerId]]:
        """The players of the next draw before replacements (BR-141, BR-144, BR-156).

        The players going through, and the semifinal losers for the
        third-place match when the next round is the final's; the second
        set is empty otherwise.
        """
        third = (
            self.semifinal_losers
            if self.third_place_match and self.rounds_drawn + 1 == self.round_count
            else frozenset()
        )
        return self.going_through, third

    def match(self, key: MatchKey) -> RemixMatch:
        """The drawn match at `key`.

        Raises:
            ValueError: No drawn match has that key.
        """
        for match in self.matches:
            if match.key == key:
                return match
        msg = f"match {key} is not drawn"
        raise ValueError(msg)


def _going_through(round_: Iterable[RemixMatch]) -> frozenset[PlayerId]:
    return frozenset(
        player_id
        for match in round_
        if not match.key.is_third_place and match.winner is not None
        for player_id in match.winner
    )


def _losers(round_: Iterable[RemixMatch]) -> frozenset[PlayerId]:
    return frozenset(
        player_id
        for match in round_
        if match.loser is not None
        for player_id in match.loser
    )


def _last_matches(matches: Iterable[RemixMatch]) -> dict[PlayerId, RemixMatch]:
    """Each player's latest match; `matches` are in schedule order."""
    latest: dict[PlayerId, RemixMatch] = {}
    for match in matches:
        for player_id in match.players:
            latest[player_id] = match
    return latest


def remix_state(
    matches: Iterable[RemixMatch], *, third_place_match: bool
) -> RemixState:
    """Check the stored matches of a Lord have mercy knockout (BR-140 to BR-144).

    Round 1 is the bracket drawn when the knockout started: n matches at
    positions 1 to n, n a power of two, with byes only there (BR-041). Round
    r has `size >> r` standard matches, and the final's round also holds the
    third-place match when the knockout has one (BR-144). Each later round
    must be drawn from the players who went through (BR-141), with each
    replacement in place of the player who left (BR-148, BR-156), and only
    once the round before is complete (BR-140).

    Args:
        matches: Every stored match of the knockout, in any order.
        third_place_match: The knockout has a third-place match (BR-044).

    Raises:
        ValueError: A caller bug: a match is given twice, has two byes, a bye
            after round 1, a result on a bye, a draw (BR-043), or a pair that
            is not two different players; round 1's positions are not 1 to n
            for a power of two; too few pairs (2, or 4 with a third-place
            match, BR-080); rounds that are not contiguous or have the wrong
            number of matches; a player twice in one round; a round drawn
            before the round before is complete, or not from the players who
            went through; a third-place match outside the final's round,
            against the flag, missing, or not between the semifinal losers;
            a round 1 larger than its pairs need (#96); a replacement in
            round 1 or on a match they do not play; a replacement who was not
            knocked out at the draw (still in, already replaced, or not in
            the knockout), a replaced player outside their match's pool, or
            a player coming in or replaced twice in one round (BR-148,
            BR-153).
    """
    matches = tuple(matches)
    repeated = [
        key for key, count in Counter(m.key for m in matches).items() if count > 1
    ]
    if repeated:
        msg = f"matches given twice: {sorted(repeated)}"
        raise ValueError(msg)
    for match in matches:
        _check_match(match)

    by_round: defaultdict[int, list[RemixMatch]] = defaultdict(list)
    for match in matches:
        by_round[match.key.round_no].append(match)
    first = sorted(by_round[1], key=lambda match: match.key.position)
    if [match.key for match in first] != [
        MatchKey(round_no=1, is_third_place=False, position=position)
        for position in range(1, len(first) + 1)
    ]:
        msg = "round 1's positions are not 1 to n"
        raise ValueError(msg)
    size = 2 * len(first)
    seed_slots(size)  # raises unless a power of two
    pairs = sum(match.side_1 is not None for match in first) + sum(
        match.side_2 is not None for match in first
    )
    if pairs < minimum_qualifiers(third_place_match=third_place_match):
        msg = f"{pairs} pairs are too few for this knockout"
        raise ValueError(msg)
    if size != bracket_size(pairs):
        msg = f"{pairs} pairs need a bracket of {bracket_size(pairs)}, not {size}"
        raise ValueError(msg)
    round_count = size.bit_length() - 1
    if (
        sorted(by_round) != list(range(1, len(by_round) + 1))
        or len(by_round) > round_count
    ):
        msg = f"the rounds {sorted(by_round)} are not 1 to at most {round_count}"
        raise ValueError(msg)

    rounds: list[tuple[RemixMatch, ...]] = []
    for round_no in range(1, len(by_round) + 1):
        round_ = _check_round(
            by_round[round_no],
            round_no=round_no,
            before=RemixState(
                size=size, third_place_match=third_place_match, rounds=tuple(rounds)
            ),
        )
        rounds.append(round_)
    return RemixState(
        size=size, third_place_match=third_place_match, rounds=tuple(rounds)
    )


def _check_match(match: RemixMatch) -> None:
    if match.side_1 is None and match.side_2 is None:
        msg = f"match {match.key} has two byes"
        raise ValueError(msg)
    if match.has_bye:
        if match.key.round_no != 1:
            msg = f"match {match.key} has a bye after round 1"
            raise ValueError(msg)
        if match.outcome is not None:
            msg = f"match {match.key} has a bye and a result"
            raise ValueError(msg)
    if match.outcome is Outcome.DRAW:
        msg = f"match {match.key} is a draw, which a knockout has not (BR-043)"
        raise ValueError(msg)
    for side in (match.side_1, match.side_2):
        if side is not None and side[0] == side[1]:
            msg = f"match {match.key} has a pair that is not two different players"
            raise ValueError(msg)
    if match.replacements and match.key.round_no == 1:
        msg = f"match {match.key} has a replacement in round 1 (BR-152)"
        raise ValueError(msg)
    if any(r.player_id not in match.players for r in match.replacements):
        msg = f"match {match.key} marks a replacement who does not play in it"
        raise ValueError(msg)


def _check_round(
    matches: Sequence[RemixMatch], *, round_no: int, before: RemixState
) -> tuple[RemixMatch, ...]:
    """Check one round against the rounds before and return it in schedule order.

    `before` holds the rounds already checked, none for round 1.
    """
    size = before.size
    round_count = before.round_count
    standard = sorted(
        (match for match in matches if not match.key.is_third_place),
        key=lambda match: match.key.position,
    )
    third = [match for match in matches if match.key.is_third_place]
    if [match.key.position for match in standard] != list(
        range(1, (size >> round_no) + 1)
    ):
        msg = f"round {round_no} does not have its {size >> round_no} matches"
        raise ValueError(msg)
    stray = [
        match.key
        for match in third
        if match.key != MatchKey(round_no=round_count, is_third_place=True, position=1)
    ]
    if stray:
        msg = f"the third-place matches {stray} are not in the final's round"
        raise ValueError(msg)
    ensure_distinct(player_id for match in matches for player_id in match.players)
    if round_count == round_no and bool(third) != before.third_place_match:
        msg = "the third-place match does not match the knockout's setting"
        raise ValueError(msg)
    if round_no > 1:
        if not all(match.is_decided for match in before.newest_round):
            msg = f"round {round_no} is drawn before round {round_no - 1} is complete"
            raise ValueError(msg)
        _check_replacements(matches, before=before)
        going_through, semifinal_losers = before.next_pools
        if _players_after(standard) != going_through:
            msg = f"round {round_no} is not drawn from the players who went through"
            raise ValueError(msg)
        if third and _players_after(third) != semifinal_losers:
            msg = "the third-place match is not between the semifinal losers"
            raise ValueError(msg)
    return (*standard, *third)


def _check_replacements(matches: Sequence[RemixMatch], *, before: RemixState) -> None:
    """Check a later round's replacements against the rounds before (BR-148, BR-153).

    Each replacement was knocked out and never replaced when the round was
    drawn, and each replaced player was in the pool of their match: the
    players going through for a standard match, the semifinal losers for the
    third-place match. Nobody comes in or is replaced twice in a round.
    """
    replacements = [r for match in matches for r in match.replacements]
    ensure_distinct(r.player_id for r in replacements)
    ensure_distinct(r.replaced_player_id for r in replacements)
    not_out = {r.player_id for r in replacements} - before.knocked_out
    if not_out:
        msg = f"replacements {sorted(not_out)} were not knocked out at the draw"
        raise ValueError(msg)
    going_through, semifinal_losers = before.next_pools
    for match in matches:
        pool = semifinal_losers if match.key.is_third_place else going_through
        outside = {r.replaced_player_id for r in match.replacements} - pool
        if outside:
            msg = (
                f"match {match.key} replaces {sorted(outside)}, who are not in its pool"
            )
            raise ValueError(msg)


def _players_after(matches: Iterable[RemixMatch]) -> frozenset[PlayerId]:
    """The players of `matches`, each replacement swapped back for the player they replaced.

    Equal to a pool exactly when the matches were drawn from it (BR-156).
    """
    swapped_back: set[PlayerId] = set()
    for match in matches:
        came_in = {r.player_id: r.replaced_player_id for r in match.replacements}
        swapped_back.update(came_in.get(p, p) for p in match.players)
    return frozenset(swapped_back)


def _draw(
    players: Iterable[PlayerId], *, rng_seed: bytes, purpose: str
) -> list[tuple[Team, Team]]:
    """Pair the players in lot order and place the pairs: 1+2 v 3+4, ... (BR-141)."""
    ordered = order_by_lot(sorted(players), rng_seed=rng_seed, purpose=purpose)
    teams = [(ordered[i], ordered[i + 1]) for i in range(0, len(ordered), 2)]
    return [(teams[i], teams[i + 1]) for i in range(0, len(teams), 2)]


@dataclass(frozen=True, slots=True, kw_only=True)
class ReplacementPlan:
    """Who comes into the next draw for whom, and who stays in without one (FR-049).

    Attributes:
        replacements: The replacements of the next draw, the replaced player
            with the best group-phase standing first (BR-148).
        staying: The players who left and stay in the draw without a
            replacement, best group-phase standing first (BR-149).
    """

    replacements: tuple[Replacement, ...]
    staying: tuple[PlayerId, ...]


def plan_replacements(
    state: RemixState,
    *,
    disabled: Iterable[PlayerId],
    standing: Iterable[Iterable[PlayerId]],
    rng_seed: bytes,
) -> ReplacementPlan:
    """Plan the replacements of the next draw (BR-147 to BR-149, BR-153).

    The players to replace are the disabled players of the next draw's pool:
    the players going through and, when the next round is the final's with a
    third-place match, the semifinal losers, whose replacement comes into the
    third-place match. The candidates are the knockout's players who are
    knocked out, not disabled and never replaced; semifinal losers waiting
    for the third-place match are still in, so before the final of a
    4-pair knockout with one there are none. Best-placed candidates come
    first: last knocked out in a later round, then the better group-phase
    standing, then the lot `REPLACEMENT_PURPOSE` (BR-074). The players to
    replace are ordered by their standing, then the same lot. With too few
    candidates, those with the best standing stay in the draw without one
    (BR-149) and the others are replaced in that order, the better standing
    getting the better replacement (BR-148).

    The organizer's preview and the draw (`draw_next_round`) both use this
    plan. Its lot holds no draw counter, so the same state always gives the
    same plan (BR-156, ADR-010).

    Args:
        state: The knockout as it stands.
        disabled: The players whose main entry is disabled now (FR-044);
            others outside the next draw's pool are ignored.
        standing: The group phase's tie groups of players, best first; a
            player missing from it ranks after every player in it.
        rng_seed: The tournament's seed (ADR-010).

    Raises:
        ValueError: The next round cannot be drawn (`can_draw_next`).
    """
    if not state.can_draw_next:
        msg = "the next round cannot be drawn"
        raise ValueError(msg)
    disabled = frozenset(disabled)
    rank = {
        player_id: index for index, group in enumerate(standing) for player_id in group
    }
    knocked_out_in = {
        player_id: match.key.round_no
        for player_id, match in _last_matches(state.matches).items()
    }
    going_through, semifinal_losers = state.next_pools
    leaving = _by_standing(
        (going_through | semifinal_losers) & disabled, rank=rank, rng_seed=rng_seed
    )
    candidates = sorted(
        _by_standing(state.knocked_out - disabled, rank=rank, rng_seed=rng_seed),
        key=lambda player_id: -knocked_out_in[player_id],
    )
    left_in = max(len(leaving) - len(candidates), 0)
    return ReplacementPlan(
        replacements=tuple(
            Replacement(player_id=candidate, replaced_player_id=player_id)
            for player_id, candidate in zip(leaving[left_in:], candidates, strict=False)
        ),
        staying=leaving[:left_in],
    )


def _by_standing(
    players: Iterable[PlayerId], *, rank: dict[PlayerId, int], rng_seed: bytes
) -> tuple[PlayerId, ...]:
    """Players by group-phase standing, ties by the lot (BR-148, BR-074)."""
    ordered = order_by_lot(
        sorted(players), rng_seed=rng_seed, purpose=REPLACEMENT_PURPOSE
    )
    return tuple(sorted(ordered, key=lambda player_id: rank.get(player_id, len(rank))))


def draw_next_round(
    state: RemixState,
    *,
    rng_seed: bytes,
    disabled: Iterable[PlayerId] = (),
    standing: Iterable[Iterable[PlayerId]] = (),
) -> tuple[RemixMatch, ...]:
    """Draw the next round of a Lord have mercy knockout (BR-141 to BR-144, BR-148, BR-156).

    The pool is the players who went through (`RemixState.going_through`),
    with each replacement that `plan_replacements` plans in place of the
    player who left (BR-148, BR-149). It is ordered by the lot
    `remix_purpose(r)`: players 1 and 2 form the first pair, 3 and 4 the
    second, and so on, and pairs 1 and 2 play the round's first match (pair 1
    on side 1), pairs 3 and 4 the second, and so on. Partners from earlier
    rounds are not avoided (BR-143). The final is re-mixed too (BR-142). With
    a third-place match, the final's round also gets that match: the four
    semifinal losers, with their replacements, ordered by the lot
    `THIRD_PLACE_PURPOSE`, 1 and 2 against 3 and 4 (BR-144). Neither lot
    holds a draw counter, so the same players always give the same matches
    (BR-146, BR-156). Each drawn match lists its replacements (BR-155).

    Args:
        state: The knockout as it stands.
        rng_seed: The tournament's seed (ADR-010).
        disabled: The players whose main entry is disabled now (FR-044).
        standing: The group phase's tie groups of players, best first.

    Returns:
        The new round's matches without results, in schedule order.

    Raises:
        ValueError: The next round cannot be drawn (`can_draw_next`).
    """
    plan = plan_replacements(
        state, disabled=disabled, standing=standing, rng_seed=rng_seed
    )
    came_in = {r.replaced_player_id: r for r in plan.replacements}
    going_through, semifinal_losers = state.next_pools
    round_no = state.rounds_drawn + 1

    def drawn(
        pool: frozenset[PlayerId], *, purpose: str, third: bool
    ) -> list[RemixMatch]:
        players = [came_in[p].player_id if p in came_in else p for p in pool]
        return [
            RemixMatch(
                key=MatchKey(
                    round_no=round_no, is_third_place=third, position=index + 1
                ),
                side_1=side_1,
                side_2=side_2,
                replacements=tuple(
                    sorted(
                        (
                            r
                            for r in plan.replacements
                            if r.player_id in (*side_1, *side_2)
                        ),
                        key=lambda r: r.player_id,
                    )
                ),
            )
            for index, (side_1, side_2) in enumerate(
                _draw(players, rng_seed=rng_seed, purpose=purpose)
            )
        ]

    matches = drawn(going_through, purpose=remix_purpose(round_no), third=False)
    if semifinal_losers:
        matches += drawn(semifinal_losers, purpose=THIRD_PLACE_PURPOSE, third=True)
    return tuple(matches)


def allows_result(state: RemixState, key: MatchKey, outcome: Outcome | None) -> bool:
    """Whether a match may take `outcome`; None clears its result (BR-146).

    In the newest round any result can be entered, changed or cleared; the
    final and the third-place match count as one round. Drawing a round locks
    the winners of the round before: there a result can be corrected only
    with the same winner, never cleared and never given to the other pair.

    Raises:
        ValueError: A caller bug: `key` is not a drawn match, the match has a
            bye, or `outcome` is a draw (BR-043).
    """
    match = state.match(key)
    if match.has_bye:
        msg = f"match {key} has a bye and takes no result"
        raise ValueError(msg)
    if outcome is Outcome.DRAW:
        msg = f"match {key} cannot be a draw (BR-043)"
        raise ValueError(msg)
    if key.round_no == state.rounds_drawn:
        return True
    return outcome is match.outcome


def players_who_left(
    state: RemixState, disabled: Iterable[PlayerId]
) -> frozenset[PlayerId]:
    """The players who have left and are still in (BR-147, BR-149, BR-155).

    A disabled player who is still in has left. Once the round they play is
    drawn they stay in it, and their pair loses by walkover, which the
    organizer records (BR-149, BR-152); both pairs of a match can have one
    (BR-157). Before the next draw they are replaced, or stay in the draw
    when nobody is available (`plan_replacements`, BR-148, BR-149). Disabled
    players outside the knockout, knocked out or replaced are ignored.
    """
    return state.still_in & frozenset(disabled)


@dataclass(frozen=True, slots=True, kw_only=True)
class RemixPlace:
    """One player's final place after a Lord have mercy knockout (BR-145).

    Attributes:
        entry_id: The player's own entry.
        player_id: The player.
        place: 1 for the winners; players of a pair, and pairs or entries
            sharing a place, have the same number (BR-104).
        partner_id: The partner of the player's last knockout match; None
            for a player who did not qualify. For a player who was replaced,
            and for the partner of the seat they took, the player now in the
            other seat of that pair (BR-151).
        seat_round_no: For a player who was replaced, the round in which
            their replacement was last knocked out before coming in: they
            are placed as if knocked out in it (BR-151). None for everyone
            else.
    """

    entry_id: EntryId
    player_id: PlayerId
    place: int
    partner_id: PlayerId | None
    seat_round_no: int | None = None


def place_remix_players(
    state: RemixState,
    *,
    entries: Iterable[PlacingEntry],
    standing: Iterable[Iterable[EntryId]] = (),
) -> tuple[RemixPlace, ...]:
    """Place every player after a Lord have mercy knockout (BR-100, BR-102 to BR-104, BR-145).

    Each knockout player takes the place of the pair they played their last
    knockout match with, and those pairs are placed as if they were entries
    (BR-102): the final's winners 1st and losers 2nd; with a third-place
    match its winners 3rd and losers 4th; the pairs losing the same earlier
    round share a place, the semifinal losers 3rd without a third-place
    match. A player who was replaced takes the seat their replacement gave
    up, in the pair the replacement was last knocked out with before coming
    in, so every place keeps its number of players (BR-151). The players who
    did not qualify follow in `standing` order,
    numbered after the knockout pairs, each counting as one, tie groups
    sharing a place (BR-103). Places count pairs, not players: after 4
    knockout pairs the best non-qualifier is 5th.

    Order within a shared place, which the PRD leaves open for re-mixed pairs:
    pairs by the position of their last match in its round; the two players
    of a pair by their group-phase standing, then seed (seedless last), then
    entry id; non-qualifiers by seed, seedless last, then entry id.

    Args:
        state: A complete knockout.
        entries: One single-player entry per player of the tournament.
        standing: The group phase's tie groups of entries, best first.

    Returns:
        One row per player, best place first.

    Raises:
        ValueError: A caller bug: the knockout is not complete, an entry is
            given twice or has not exactly one player, a player has two
            entries, a knockout player has no entry, an entry in `standing`
            is unknown, or a player would be placed twice or not at all.
    """
    if not state.is_complete:
        msg = "the knockout is not complete"
        raise ValueError(msg)
    entries = tuple(entries)
    ensure_distinct(entry.entry_id for entry in entries)
    if any(len(entry.player_ids) != 1 for entry in entries):
        msg = "a Lord have mercy entry is not a single player"
        raise ValueError(msg)
    ensure_distinct(entry.player_ids[0] for entry in entries)
    by_entry = {entry.entry_id: entry for entry in entries}
    by_player = {entry.player_ids[0]: entry for entry in entries}
    groups = [tuple(group) for group in standing]
    ensure_distinct(entry_id for group in groups for entry_id in group)
    unknown = [
        entry_id for group in groups for entry_id in group if entry_id not in by_entry
    ]
    if unknown:
        msg = f"entries {unknown} in the standing are not among the entries"
        raise ValueError(msg)
    missing = state.players - by_player.keys()
    if missing:
        msg = f"knockout players {sorted(missing)} have no entry"
        raise ValueError(msg)
    rank = {entry_id: index for index, group in enumerate(groups) for entry_id in group}

    def player_order(player_id: PlayerId) -> tuple[int, bool, int, int]:
        entry = by_player[player_id]
        return (rank.get(entry.entry_id, len(groups)), *_order(entry))

    seats = _seats(state)
    seat_round = {player_id: key.round_no for (key, _), player_id in seats.items()}
    rows: list[RemixPlace] = []
    place = 1
    for block in _pair_blocks(state, seats):
        for team in block:
            first, second = sorted(team, key=player_order)
            rows.extend(
                RemixPlace(
                    entry_id=by_player[player_id].entry_id,
                    player_id=player_id,
                    place=place,
                    partner_id=partner_id,
                    seat_round_no=seat_round.get(player_id),
                )
                for player_id, partner_id in ((first, second), (second, first))
            )
        place += len(block)
    for group in groups:
        rest = sorted(
            (
                by_entry[entry_id]
                for entry_id in group
                if by_entry[entry_id].player_ids[0] not in state.players
            ),
            key=_order,
        )
        rows.extend(
            RemixPlace(
                entry_id=entry.entry_id,
                player_id=entry.player_ids[0],
                place=place,
                partner_id=None,
            )
            for entry in rest
        )
        place += len(rest)
    ensure_distinct(row.player_id for row in rows)
    unplaced = set(by_player) - {row.player_id for row in rows}
    if unplaced:
        msg = f"players {sorted(unplaced)} are left without a place"
        raise ValueError(msg)
    return tuple(rows)


def _order(entry: PlacingEntry) -> tuple[bool, int, int]:
    """Order entries sharing a place: by seed, seedless last, then by id (BR-104)."""
    seed = entry.seed
    return (seed is None, 0 if seed is None else seed, entry.entry_id.int)


type _Seat = tuple[MatchKey, PlayerId]


def _seats(state: RemixState) -> dict[_Seat, PlayerId]:
    """The seats replacements gave up, each with the replaced player who takes it (BR-151).

    A seat is a player's place in the pair of one match. A replacement gave
    up their seat in the match they were last knocked out in before coming
    in; the player they replaced takes it.
    """
    seats: dict[_Seat, PlayerId] = {}
    for index, round_ in enumerate(state.rounds):
        latest = _last_matches(state.matches[: sum(map(len, state.rounds[:index]))])
        for match in round_:
            for replacement in match.replacements:
                given_up = latest[replacement.player_id].key
                seats[given_up, replacement.player_id] = replacement.replaced_player_id
    return seats


def _pair_blocks(state: RemixState, seats: dict[_Seat, PlayerId]) -> list[list[Team]]:
    """The knockout's pairs by their last match, sharing a place, best first (BR-102).

    Each block lists its pairs by the position of their last match, with a
    replaced player in each seat a replacement gave up (`_seats`, BR-151).
    Pairs sharing a place are listed in lot order (#94 option A); this is
    the one place to change.
    """

    def seated(key: MatchKey, team: Team) -> Team:
        first, second = (seats.get((key, player_id), player_id) for player_id in team)
        return first, second

    # The final, then the third-place match: each has a winner and a loser.
    blocks = [
        [team]
        for match in state.newest_round
        for team in (match.winner, match.loser)
        if team is not None
    ]
    # With a third-place match, the semifinal losers are placed by it. No
    # replacement comes in after the final's round, so only earlier seats
    # can be given up.
    earlier = state.rounds[: -2 if state.third_place_match else -1]
    blocks.extend(
        [seated(match.key, match.loser) for match in round_ if match.loser is not None]
        for round_ in reversed(earlier)
    )
    return blocks


def remix_season_points(
    places: Iterable[RemixPlace], table: Sequence[int]
) -> tuple[PlayerPoints, ...]:
    """Compute the placement points after a Lord have mercy knockout (BR-110, BR-111, BR-145).

    The units sharing a place are the knockout pairs, each a player with
    their partner, and the single non-qualifiers. Each unit gets the average
    of the places they cover, rounded down (`shared_place_points`), and both
    players of a pair get the pair's full points. With the default table and
    4 pairs without a third-place match, the four semifinal losers get
    (6 + 4) / 2 = 5 each.

    Returns:
        One `PlayerPoints` per player, with the player's own entry, best
        place first and by player id within a place.

    Raises:
        ValueError: A caller bug: a player is given twice, a partner has no
            row of their own, at another place or with another partner, or
            the places are not what BR-104 produces.
    """
    rows = tuple(places)
    ensure_distinct(row.player_id for row in rows)
    by_player = {row.player_id: row for row in rows}
    units: Counter[int] = Counter()
    for row in rows:
        if row.partner_id is None:
            units[row.place] += 2
            continue
        partner = by_player.get(row.partner_id)
        if (
            partner is None
            or partner.partner_id != row.player_id
            or partner.place != row.place
        ):
            msg = f"player {row.player_id}'s partner is not placed with them"
            raise ValueError(msg)
        units[row.place] += 1
    expected = 1
    for place in sorted(units):
        if place != expected:
            msg = f"place {place} follows a gap: expected {expected}"
            raise ValueError(msg)
        expected += units[place] // 2
    points = {
        place: shared_place_points(place=place, entry_count=count // 2, table=table)
        for place, count in units.items()
    }
    return tuple(
        sorted(
            (
                PlayerPoints(
                    player_id=row.player_id,
                    entry_id=row.entry_id,
                    place=row.place,
                    points=points[row.place],
                )
                for row in rows
            ),
            key=lambda row: (row.place, row.player_id.int),
        )
    )
