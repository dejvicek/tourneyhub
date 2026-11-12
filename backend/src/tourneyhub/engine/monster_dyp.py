"""Monster DYP: standings, the draw of each round and the knockout's entries.

Covers FR-041, FR-045, BR-060 to BR-063 with BR-064, BR-067 and BR-070 to
BR-074, and BR-080 to BR-084. Repeated partners are avoided as ADR-011 says:
swaps first, then a minimum-cost matching when the swaps get stuck.
"""

from collections import Counter
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from tourneyhub.engine.errors import (
    NotEnoughPlayersError,
    OddQualifierCountError,
    QualifierCountError,
)
from tourneyhub.engine.ids import PlayerId, ensure_distinct
from tourneyhub.engine.lots import lot_digest, order_by_lot
from tourneyhub.engine.matching import Pair, min_cost_matching
from tourneyhub.engine.results import POINTS, Result, result_for, tiebreak_purpose
from tourneyhub.engine.tournaments import (
    MatchOutcome,
    MonsterKnockoutMode,
    Tiebreaker,
)

GROUP_SIZE = 4
"""Players in a group, who play one match: #1 + #4 v #2 + #3 (BR-060)."""

MINIMUM_PLAYERS = GROUP_SIZE
"""The fewest players who are not disabled that a round needs (FR-032, BR-063)."""

TOP_PLAYER_ROUNDS = 2
"""The rounds that keep the top players apart: rounds 1 and 2 (BR-061)."""

_MINIMUM_KNOCKOUT_ENTRIES = 2
_MINIMUM_KNOCKOUT_ENTRIES_WITH_THIRD_PLACE = 4

type Team = tuple[PlayerId, PlayerId]
"""Two partners: the side of a Monster DYP match (DATA-MODEL D2)."""


class TopPlayerOrder(StrEnum):
    """Which players count as top players first (FR-041, BR-061).

    Players marked by the organizer come first, then the others; the first as
    many as the round has matches are its top players. The unmarked ones are
    always taken from the league ranking (FR-041); this order only sorts the
    marked ones.

    The PRD has settled it: the marked players who play count in league-ranking
    order (BR-061, FR-041), so `LEAGUE_RANKING` is the only rule and there is no
    setting. This enum and `MonsterDypOptions.top_player_order` stay until
    issue #60 removes them.
    """

    LEAGUE_RANKING = "league_ranking"
    """The league ranking (BR-020), as ADR-011 and DATA-MODEL propose."""

    STANDING = "standing"
    """The marked players in the order the round is drawn from: the league
    ranking in round 1, the current standing in round 2."""


class GroupingMethod(StrEnum):
    """How a round's groups were found (BR-060 to BR-062, ADR-011)."""

    STANDING = "standing"
    """The groups of BR-060 and BR-061 as they are: no repeated partner."""

    SWAPS = "swaps"
    """Players were swapped to avoid repeated partners (BR-062)."""

    MATCHING = "matching"
    """The swaps got stuck; a minimum-cost matching formed the teams (ADR-011)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class MonsterDypOptions:
    """Rules once left open, as parameters (BR-061, BR-063, issue #24).

    The PRD has since settled all three (BR-061, BR-063 as reviewed in #46):
    top players are not exempt from the sit-out lot, the marked players count in
    league-ranking order, and players who did not sit out the round before are
    picked to sit out first, before the fewest sit-outs. So the options are
    obsolete: the first two are always off and `LEAGUE_RANKING`, and
    `avoids_sitting_out_twice_in_a_row` is always on, with that priority (the
    code below puts the fewest sit-outs first). Issue #60 removes the options and
    follows BR-063, including a missed round counting as a sit-out for the order
    (BR-064, BR-067).

    Attributes:
        are_top_players_exempt: In rounds 1 and 2, the top players never sit
            out; the sit-out lot is drawn among the others. Off, as BR-061
            and BR-063 say: the top players are chosen after the sit-outs.
        top_player_order: In which order the marked players count first as top
            players (FR-041); the unmarked always follow the league ranking.
        avoids_sitting_out_twice_in_a_row: Among players with as few
            sit-outs, those who sat out the previous round sit out last
            (issue #24). BR-063 always puts the round-before rule first,
            before the fewest sit-outs; issue #60 makes the engine follow
            that.
    """

    are_top_players_exempt: bool = False
    top_player_order: TopPlayerOrder = TopPlayerOrder.LEAGUE_RANKING
    avoids_sitting_out_twice_in_a_row: bool = False


DEFAULT_OPTIONS = MonsterDypOptions()
"""No exemption and the league ranking, as BR-061 and BR-063 say.

The round-before rule of BR-063 stays off until issue #60 changes the engine.
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class MonsterMatch:
    """One played or drawn match of a Monster DYP round (DATA-MODEL D2, D11).

    Attributes:
        team_1: The players on side 1.
        team_2: The players on side 2.
        outcome: The result, or `None` while there is none. Only a match with
            a result counts for points, opponents and score difference.
        score_difference: Side 1's goals minus side 2's, over the games that
            have a score (BR-073); 0 for a walkover.
    """

    team_1: Team
    team_2: Team
    outcome: MatchOutcome | None = None
    score_difference: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class MonsterRound:
    """One round of a Monster DYP: its matches and who sat out (DATA-MODEL D5).

    Players in neither did not play the round because they were disabled or
    had not joined yet; such a round earns them nothing and is not a sit-out
    (BR-064, BR-067).

    Attributes:
        round_no: 1 for the first round.
        matches: The round's matches.
        sat_out: The players who sat out (BR-063).
    """

    round_no: int
    matches: tuple[MonsterMatch, ...]
    sat_out: tuple[PlayerId, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class MonsterStanding:
    """One player's line in the Monster DYP standings (FR-060, BR-070 to BR-074).

    Attributes:
        player_id: The player.
        position: The strict order, 1 to n, used to group the next round and
            for the knockout's cut and seeding; the lot decides between
            players who share a place (BR-074).
        place: The shown place: players level on points and on every enabled
            tie-breaker share the position of the best of them (BR-074).
        points: The player's own points from results and sit-outs (BR-070,
            BR-071).
        bh1: The sum of the points of both opponents, once per match (BR-073).
        bh2: The sum of those opponents' BH1, once per match (BR-073).
        score_difference: Goals for minus goals against, entered scores only
            (BR-073).
        played: Matches with a result.
        won: Matches won.
        drawn: Matches drawn.
        lost: Matches lost.
        sat_out: Rounds the player sat out (BR-063); missed rounds of a
            disabled or late player do not count here (BR-064, BR-067, FR-060).
            BR-063 counts them for the sit-out order only; issue #60 adds that.
        is_decided_by_lot: The player shares their place, so the lot decided
            their position (ADR-009).
    """

    player_id: PlayerId
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
class MonsterGroup:
    """One group of four in a drawn round, and its match (BR-060, BR-061).

    Attributes:
        team_1: The group's 1st and 4th player (BR-060).
        team_2: The group's 2nd and 3rd player.
        top_player: In rounds 1 and 2, the group's top player, who is its 1st
            (BR-061); `None` from round 3.
        is_team_1_repeat: The partners of `team_1` were partners before; only
            when every grouping has a repeat (BR-062).
        is_team_2_repeat: The same for `team_2`.
    """

    team_1: Team
    team_2: Team
    top_player: PlayerId | None
    is_team_1_repeat: bool
    is_team_2_repeat: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class MonsterDraw:
    """A drawn Monster DYP round (FR-035, FR-040, FR-042).

    Attributes:
        round_no: The new round's number.
        groups: The matches, one per group, in group order.
        sitting_out: The players who sit out (BR-063): fewest sit-outs first,
            then by lot.
        is_sit_out_by_lot: The lot decided who sits out: another player with
            as many sit-outs plays (ADR-009).
        top_players: In rounds 1 and 2, one per group, in group order
            (BR-061); empty from round 3.
        method: How the groups were found.
        is_grouping_by_lot: The lot chose between equally good swaps
            (ADR-011, ADR-009).
    """

    round_no: int
    groups: tuple[MonsterGroup, ...]
    sitting_out: tuple[PlayerId, ...]
    is_sit_out_by_lot: bool
    top_players: tuple[PlayerId, ...]
    method: GroupingMethod
    is_grouping_by_lot: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class MonsterKnockoutEntry:
    """One entry of the knockout after Monster DYP rounds (BR-081 to BR-084).

    Attributes:
        seed: 1 to n; the bracket places the seeds (BR-040 to BR-042).
        player_ids: One player in the Singles mode, else two, the
            better-placed first.
        is_drawn_by_lot: The lot drew the partner or the seed, or decided the
            position of a player of the entry (ADR-009).
    """

    seed: int
    player_ids: tuple[PlayerId, ...]
    is_drawn_by_lot: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class MonsterKnockout:
    """The knockout's entries after Monster DYP rounds (FR-045, BR-080).

    Attributes:
        mode: How the entries were formed.
        entries: The entries, seed 1 first.
        qualifiers: The qualifying players, by position.
        skipped: Disabled players placed above the last qualifier, whom the
            next players replaced (BR-080).
        is_cut_by_lot: The last qualifier shares their place with the first
            player who does not qualify, so the lot decided the cut (BR-074).
    """

    mode: MonsterKnockoutMode
    entries: tuple[MonsterKnockoutEntry, ...]
    qualifiers: tuple[PlayerId, ...]
    skipped: tuple[PlayerId, ...]
    is_cut_by_lot: bool


def sit_out_purpose(round_no: int) -> str:
    """Name the sit-out lot of a round, `sit-out:round-<round_no>` (BR-063, ADR-010)."""
    return f"sit-out:round-{round_no}"


def swap_purpose(round_no: int) -> str:
    """Name the lot between equally good swaps, `monster-swap:round-<n>` (ADR-011)."""
    return f"monster-swap:round-{round_no}"


def knockout_purpose(mode: MonsterKnockoutMode, draw_counter: int) -> str:
    """Name the lot of a knockout mode, `<mode>:<draw_counter>` (BR-083, BR-084).

    For example `a_little_mercy:0`. A new draw of the knockout increments the
    tournament's draw counter (ADR-010).
    """
    return f"{mode.value}:{draw_counter}"


def monster_standings(
    player_ids: Iterable[PlayerId],
    rounds: Iterable[MonsterRound],
    *,
    tiebreakers: Sequence[Tiebreaker],
    sit_out_points: int,
    rng_seed: bytes,
) -> tuple[MonsterStanding, ...]:
    """Compute the Monster DYP standings (BR-070 to BR-074, FR-043, FR-060).

    Each player collects their own points: a win earns both players of the
    team 2, a draw 1 and a loss 0 (BR-070); a sit-out earns `sit_out_points`,
    0, 1 or 2 (BR-071). Players are ordered by points, then by `tiebreakers`, the
    enabled tie-breakers in the organizer's order, each higher first (BR-072,
    FR-043). BH1 sums the current points of both opponents, once per match,
    and BH2 sums those opponents' BH1; partners and sit-outs add nothing
    (BR-073). Players still level share the place, and the lot
    `tiebreak:after-round-<n>` gives them a strict position, where `n` counts
    the rounds whose every match has a result (BR-074, ADR-010).

    Pass every player of the phase, disabled and late ones included: their
    results and points stay, and they are placed by their standing (BR-064,
    BR-067). A match without a result counts for nothing yet.

    Returns:
        One line per player, by position.

    Raises:
        ValueError: A caller bug: a player or a tie-breaker is given twice,
            `sit_out_points` is not 0, 1 or 2, or the rounds are not valid (see
            `draw_monster_round`).
    """
    ids = tuple(player_ids)
    ensure_distinct(ids)
    played_rounds = _checked_rounds(ids, rounds)
    order = tuple(tiebreakers)
    if len(set(order)) != len(order):
        msg = f"tie-breakers {order} name one twice"
        raise ValueError(msg)
    if sit_out_points not in {0, 1, 2}:
        msg = f"sit-out points must be 0, 1 or 2, got {sit_out_points}"
        raise ValueError(msg)

    points: Counter[PlayerId] = Counter()
    results: dict[PlayerId, Counter[Result]] = {id_: Counter() for id_ in ids}
    difference: Counter[PlayerId] = Counter()
    sat_out: Counter[PlayerId] = Counter()
    opponents: dict[PlayerId, list[PlayerId]] = {id_: [] for id_ in ids}
    for round_ in played_rounds:
        for player_id in round_.sat_out:
            sat_out[player_id] += 1
            points[player_id] += sit_out_points
        for match in round_.matches:
            if match.outcome is None:
                continue
            for team, others, own, goals in (
                (match.team_1, match.team_2, MatchOutcome.SIDE_1, 1),
                (match.team_2, match.team_1, MatchOutcome.SIDE_2, -1),
            ):
                result = result_for(match.outcome, own)
                for player_id in team:
                    results[player_id][result] += 1
                    points[player_id] += POINTS[result]
                    difference[player_id] += goals * match.score_difference
                    opponents[player_id].extend(others)
    bh1 = {id_: sum(points[other] for other in opponents[id_]) for id_ in ids}
    bh2 = {id_: sum(bh1[other] for other in opponents[id_]) for id_ in ids}
    values: dict[Tiebreaker, Callable[[PlayerId], int]] = {
        Tiebreaker.BH1: bh1.__getitem__,
        Tiebreaker.BH2: bh2.__getitem__,
        Tiebreaker.SCORE_DIFFERENCE: difference.__getitem__,
    }

    def criteria(player_id: PlayerId) -> tuple[int, ...]:
        return (-points[player_id], *(-values[key](player_id) for key in order))

    purpose = tiebreak_purpose(
        sum(
            all(match.outcome is not None for match in round_.matches)
            for round_ in played_rounds
        )
    )
    ordered = sorted(
        ids,
        key=lambda player_id: (
            criteria(player_id),
            lot_digest(rng_seed=rng_seed, purpose=purpose, candidate=player_id),
        ),
    )
    ties = Counter(criteria(player_id) for player_id in ids)
    places: dict[tuple[int, ...], int] = {}
    for position, player_id in enumerate(ordered, start=1):
        places.setdefault(criteria(player_id), position)
    return tuple(
        MonsterStanding(
            player_id=player_id,
            position=position,
            place=places[criteria(player_id)],
            points=points[player_id],
            bh1=bh1[player_id],
            bh2=bh2[player_id],
            score_difference=difference[player_id],
            played=len(opponents[player_id]) // 2,
            won=results[player_id][Result.WON],
            drawn=results[player_id][Result.DRAWN],
            lost=results[player_id][Result.LOST],
            sat_out=sat_out[player_id],
            is_decided_by_lot=ties[criteria(player_id)] > 1,
        )
        for position, player_id in enumerate(ordered, start=1)
    )


def draw_monster_round(
    standing: Sequence[PlayerId],
    rounds: Iterable[MonsterRound],
    *,
    league_ranking: Sequence[PlayerId],
    rng_seed: bytes,
    marked_top_players: Iterable[PlayerId] = (),
    disabled: Iterable[PlayerId] = (),
    options: MonsterDypOptions = DEFAULT_OPTIONS,
) -> MonsterDraw:
    """Draw the next round of a Monster DYP (FR-041, FR-042, BR-060 to BR-063).

    1. **Who plays.** Disabled players are left out (BR-064). With m matches
       (the players left, divided by 4, rounded down), the extra one to three
       sit out: those who have sat out the fewest times, the lot
       `sit-out:round-<n>` deciding ties (BR-063).
    2. **Top players, rounds 1 and 2 (BR-061, FR-041).** The first m playing
       players, those marked by the organizer first, in
       `options.top_player_order`, and then the others in league-ranking
       order. A marked player who sits out or is disabled is replaced by the
       next one.
    3. **Groups (BR-060, BR-061).** In rounds 1 and 2, group g is the g-th
       top player and then the next three other players in standing order;
       from round 3, the playing players in standing order, four at a time.
       In each group the 1st and 4th play the 2nd and 3rd.
    4. **Swaps (BR-062, ADR-011).** While a team repeats a partnership, the
       swap of two players' places that leaves the fewest repeats is made;
       among those, the one that leaves the smallest sum of earlier counts
       (how many times each team has been partners before); among those, the
       one that moves players least far from their places in step 3; and of
       those the first by the lot `monster-swap:round-<n>`. Top players are
       not swapped in rounds 1 and 2. The swaps stop when no repeat is left
       or none improves the draw.
    5. **Matching (ADR-011).** If repeats are left, a minimum-cost matching
       of all the players, where a team costs more the more often it has been
       partners (the number of repeats first, then the sum of the counts),
       tells whether a better draw exists. If so, its teams replace the
       others, placed where their players move least. Every draw therefore
       has the fewest repeated partners possible, and of those the smallest
       sum of earlier counts. This happens only from round 3: in rounds 1 and
       2 the swaps always remove every repeat.

    Repeated opponents are allowed. The result depends only on the inputs
    and the seed, so the same round is drawn on every call.

    Args:
        standing: Every player of the phase in strict order: the league
            ranking in round 1, the standings' positions after that.
        rounds: Every round played so far.
        league_ranking: The same players in league-ranking order (BR-020),
            for the top players.
        rng_seed: The tournament's seed (ADR-010).
        marked_top_players: The players the organizer marked as top players
            (FR-041, `entries.is_top_player`).
        disabled: The players disabled now (FR-044).
        options: The rules the PRD leaves open.

    Raises:
        NotEnoughPlayersError: Fewer than 4 players are not disabled.
        ValueError: A caller bug: a player is given twice, `league_ranking`
            has other players than `standing`, a marked or disabled player is
            unknown, the round numbers are not 1 to n, or a player is in a
            round twice or is unknown.
    """
    order = tuple(standing)
    ensure_distinct(order)
    played_rounds = _checked_rounds(order, rounds)
    ranking = tuple(league_ranking)
    ensure_distinct(ranking)
    if set(ranking) != set(order):
        msg = "the league ranking has other players than the standing"
        raise ValueError(msg)
    marked = set(marked_top_players)
    off = set(disabled)
    if not (marked | off) <= set(order):
        msg = f"players {(marked | off) - set(order)} are not in the standing"
        raise ValueError(msg)

    round_no = len(played_rounds) + 1
    active = [player for player in order if player not in off]
    if len(active) < MINIMUM_PLAYERS:
        raise NotEnoughPlayersError(minimum=MINIMUM_PLAYERS, given=len(active))
    match_count = len(active) // GROUP_SIZE
    marked_order = (
        ranking if options.top_player_order is TopPlayerOrder.LEAGUE_RANKING else order
    )

    def pick_top_players(candidates: Iterable[PlayerId]) -> tuple[PlayerId, ...]:
        pool = set(candidates)
        first = [player for player in marked_order if player in pool & marked]
        rest = [player for player in ranking if player in pool - marked]
        return tuple((first + rest)[:match_count])

    has_top_players = round_no <= TOP_PLAYER_ROUNDS
    exempt = (
        pick_top_players(active)
        if has_top_players and options.are_top_players_exempt
        else ()
    )
    sitting_out, is_sit_out_by_lot = _choose_sit_outs(
        active,
        played_rounds,
        count=len(active) - GROUP_SIZE * match_count,
        exempt=exempt,
        rng_seed=rng_seed,
        purpose=sit_out_purpose(round_no),
        avoids_twice_in_a_row=options.avoids_sitting_out_twice_in_a_row,
    )
    playing = [player for player in active if player not in sitting_out]
    top_players = (exempt or pick_top_players(playing)) if has_top_players else ()
    if top_players:
        others = [player for player in playing if player not in top_players]
        start = [
            player
            for index, top in enumerate(top_players)
            for player in (top, *others[3 * index : 3 * index + 3])
        ]
    else:
        start = playing

    grouping = _Grouping(
        start,
        partners=_partnerships(played_rounds),
        fixed=frozenset(range(0, len(start), GROUP_SIZE))
        if top_players
        else frozenset(),
    )
    is_grouping_by_lot = grouping.swap(
        rng_seed=rng_seed, purpose=swap_purpose(round_no)
    )
    method = (
        GroupingMethod.SWAPS if grouping.slots != start else GroupingMethod.STANDING
    )
    if grouping.match():
        method = GroupingMethod.MATCHING
    return MonsterDraw(
        round_no=round_no,
        groups=grouping.groups(has_top_players=bool(top_players)),
        sitting_out=sitting_out,
        is_sit_out_by_lot=is_sit_out_by_lot,
        top_players=top_players,
        method=method,
        is_grouping_by_lot=is_grouping_by_lot,
    )


def select_monster_knockout(
    standings: Iterable[MonsterStanding],
    *,
    qualifiers: int,
    mode: MonsterKnockoutMode,
    rng_seed: bytes,
    draw_counter: int,
    third_place_match: bool = False,
    disabled: Iterable[PlayerId] = (),
) -> MonsterKnockout:
    """Form the knockout's entries after Monster DYP rounds (FR-045, BR-080 to BR-084).

    The best `qualifiers` players by position qualify; disabled players do
    not, and the next ones move up (BR-080). With N qualifiers:

    - **Seeded pairs (BR-081):** the 1st partners the (N/2 + 1)th, the 2nd
      the (N/2 + 2)th, and so on; pair i is seed i.
    - **Singles (BR-082):** each qualifier is an entry, seeded by position.
    - **A little mercy (BR-083):** the top half by position, each drawn a
      partner from the bottom half by the lot `a_little_mercy:<n>`; pair i,
      with the i-th top-half player, is seed i.
    - **Lord have mercy (BR-084):** all qualifiers ordered by the lot
      `lord_have_mercy:<n>`; the 1st and 2nd form seed 1, the 3rd and 4th
      seed 2, and so on, ignoring the standings.

    Args:
        standings: The final standings from `monster_standings`.
        qualifiers: How many players qualify (FR-045).
        mode: How the entries are formed.
        rng_seed: The tournament's seed (ADR-010).
        draw_counter: The tournament's draw counter, part of the lot's
            purpose (ADR-010).
        third_place_match: The knockout has a third-place match (BR-044).
        disabled: The players disabled now (FR-044).

    Raises:
        OddQualifierCountError: A pair mode with an odd number (BR-080).
        QualifierCountError: Fewer qualifiers than 2 entries need, 4 with a
            third-place match (pairs: twice as many players), or more than
            the players who are not disabled (BR-080).
        ValueError: A caller bug: a player is given twice, the positions are
            not 1 to n, or a disabled player is unknown.
    """
    table = tuple(sorted(standings, key=lambda line: line.position))
    ensure_distinct(line.player_id for line in table)
    if [line.position for line in table] != list(range(1, len(table) + 1)):
        msg = "the standing's positions are not 1 to n"
        raise ValueError(msg)
    off = set(disabled)
    if not off <= {line.player_id for line in table}:
        msg = "a disabled player is not in the standing"
        raise ValueError(msg)

    eligible = [line for line in table if line.player_id not in off]
    is_pairs = mode is not MonsterKnockoutMode.SINGLES
    team_size = 2 if is_pairs else 1
    if is_pairs and qualifiers % 2:
        raise OddQualifierCountError(given=qualifiers)
    minimum = team_size * (
        _MINIMUM_KNOCKOUT_ENTRIES_WITH_THIRD_PLACE
        if third_place_match
        else _MINIMUM_KNOCKOUT_ENTRIES
    )
    maximum = len(eligible) - len(eligible) % team_size
    if not minimum <= qualifiers <= maximum:
        raise QualifierCountError(minimum=minimum, maximum=maximum, given=qualifiers)

    chosen = eligible[:qualifiers]
    last = chosen[-1].position
    ids = [line.player_id for line in chosen]
    entries = _knockout_entries(
        ids,
        mode=mode,
        by_lot={line.player_id for line in chosen if line.is_decided_by_lot},
        rng_seed=rng_seed,
        purpose=knockout_purpose(mode, draw_counter),
    )
    return MonsterKnockout(
        mode=mode,
        entries=entries,
        qualifiers=tuple(ids),
        skipped=tuple(
            line.player_id
            for line in table
            if line.player_id in off and line.position < last
        ),
        is_cut_by_lot=(
            len(eligible) > qualifiers
            and eligible[qualifiers].place == chosen[-1].place
        ),
    )


def _knockout_entries(
    ids: Sequence[PlayerId],
    *,
    mode: MonsterKnockoutMode,
    by_lot: Collection[PlayerId],
    rng_seed: bytes,
    purpose: str,
) -> tuple[MonsterKnockoutEntry, ...]:
    """Form the entries of one mode from the qualifiers by position (BR-081-084).

    `by_lot` are the qualifiers whose position the lot decided (BR-074); an
    entry that follows the positions is drawn by lot when one of its players
    is among them (ADR-009).
    """
    half = len(ids) // 2
    match mode:
        case MonsterKnockoutMode.SINGLES:
            return tuple(
                MonsterKnockoutEntry(
                    seed=seed, player_ids=(id_,), is_drawn_by_lot=id_ in by_lot
                )
                for seed, id_ in enumerate(ids, start=1)
            )
        case MonsterKnockoutMode.SEEDED_PAIRS:
            return _pair_entries(
                ids,
                zip(ids[:half], ids[half:], strict=True),
                is_drawn_by_lot=False,
                by_lot=by_lot,
            )
        case MonsterKnockoutMode.A_LITTLE_MERCY:
            drawn = order_by_lot(ids[half:], rng_seed=rng_seed, purpose=purpose)
            return _pair_entries(
                ids, zip(ids[:half], drawn, strict=True), is_drawn_by_lot=True
            )
        case MonsterKnockoutMode.LORD_HAVE_MERCY:
            drawn = order_by_lot(ids, rng_seed=rng_seed, purpose=purpose)
            return _pair_entries(
                ids, zip(drawn[0::2], drawn[1::2], strict=True), is_drawn_by_lot=True
            )
        case _:
            assert_never(mode)


def _pair_entries(
    ids: Sequence[PlayerId],
    pairs: Iterable[tuple[PlayerId, PlayerId]],
    *,
    is_drawn_by_lot: bool,
    by_lot: Collection[PlayerId] = (),
) -> tuple[MonsterKnockoutEntry, ...]:
    """Number the pairs as seeds in the order given, the better-placed player first.

    A pair is drawn by lot when `is_drawn_by_lot`, or when a player of it is
    in `by_lot`.
    """
    place = {id_: index for index, id_ in enumerate(ids)}
    return tuple(
        MonsterKnockoutEntry(
            seed=seed,
            player_ids=tuple(sorted(pair, key=place.__getitem__)),
            is_drawn_by_lot=is_drawn_by_lot or any(id_ in by_lot for id_ in pair),
        )
        for seed, pair in enumerate(pairs, start=1)
    )


def _checked_rounds(
    player_ids: Sequence[PlayerId], rounds: Iterable[MonsterRound]
) -> tuple[MonsterRound, ...]:
    """Return the rounds by number, refusing what no valid Monster DYP can hold."""
    ordered = tuple(sorted(rounds, key=lambda round_: round_.round_no))
    if [round_.round_no for round_ in ordered] != list(range(1, len(ordered) + 1)):
        msg = "the round numbers are not 1 to n"
        raise ValueError(msg)
    known = set(player_ids)
    for round_ in ordered:
        present = [
            *round_.sat_out,
            *(
                player
                for match in round_.matches
                for player in (*match.team_1, *match.team_2)
            ),
        ]
        ensure_distinct(present)
        if not known.issuperset(present):
            msg = f"round {round_.round_no} has players that are not given"
            raise ValueError(msg)
    return ordered


type Partnership = frozenset[PlayerId]
"""Two players, in either order."""


def _partnerships(rounds: Iterable[MonsterRound]) -> Counter[Partnership]:
    """Count how many times each pair of players have been partners (BR-062)."""
    return Counter(
        frozenset(team)
        for round_ in rounds
        for match in round_.matches
        for team in (match.team_1, match.team_2)
    )


def _choose_sit_outs(
    active: Sequence[PlayerId],
    rounds: Sequence[MonsterRound],
    *,
    count: int,
    exempt: Iterable[PlayerId],
    rng_seed: bytes,
    purpose: str,
    avoids_twice_in_a_row: bool,
) -> tuple[tuple[PlayerId, ...], bool]:
    """Choose who sits out, and whether the lot decided it (BR-063, ADR-009).

    BR-063 picks first the players who did not sit out the round before, then
    those with the fewest sit-outs (a missed round counts as one), then a lot.
    This code puts the fewest sit-outs first and the round before second, only
    when `avoids_twice_in_a_row` is set, and counts no missed round. Issue #60
    changes it.
    """
    if count == 0:
        return (), False
    sat_out = Counter(player for round_ in rounds for player in round_.sat_out)
    last = set(rounds[-1].sat_out) if rounds and avoids_twice_in_a_row else set()

    def rule(player: PlayerId) -> tuple[int, bool]:
        return sat_out[player], player in last

    excluded = set(exempt)
    candidates = sorted(
        (player for player in active if player not in excluded),
        key=lambda player: (
            rule(player),
            lot_digest(rng_seed=rng_seed, purpose=purpose, candidate=player),
        ),
    )
    # There are more candidates than sit-outs: at least 3m + count of them.
    return tuple(candidates[:count]), rule(candidates[count - 1]) == rule(
        candidates[count]
    )


def _partner_slot(slot: int) -> int:
    """Return the slot of `slot`'s partner: #1 + #4 and #2 + #3 in each group."""
    offset = slot % GROUP_SIZE
    return slot - offset + GROUP_SIZE - 1 - offset


class _Grouping:
    """The players' places ("slots") in a round, and the swaps of ADR-011.

    Slot `4g + k` is the (k + 1)th player of group g. `home` is each player's
    slot in the groups of BR-060 and BR-061; how far a grouping moves the
    players from it is the sum of the distances. A grouping is the better the
    fewer teams repeat a partnership, and of those the smaller the sum of how
    many times its teams have been partners before.
    """

    def __init__(
        self,
        start: Sequence[PlayerId],
        *,
        partners: Counter[Partnership],
        fixed: frozenset[int],
    ) -> None:
        self.slots = list(start)
        self.home = {player: slot for slot, player in enumerate(start)}
        self.partners = partners
        self.fixed = fixed

    def earlier(self, slot: int) -> int:
        """Count how many times the team at `slot` have been partners before."""
        return self.partners[
            frozenset((self.slots[slot], self.slots[_partner_slot(slot)]))
        ]

    def is_repeat(self, slot: int) -> bool:
        """Whether the team at `slot` were partners before."""
        return self.earlier(slot) > 0

    def repeats(self) -> int:
        """Count the teams that were partners before."""
        return sum(
            self.is_repeat(slot)
            for slot in range(len(self.slots))
            if slot < _partner_slot(slot)
        )

    def swap(self, *, rng_seed: bytes, purpose: str) -> bool:
        """Swap players while that reduces repeats; return whether a lot chose."""

        def lot(swap: Pair) -> tuple[bytes, ...]:
            return tuple(
                sorted(
                    lot_digest(rng_seed=rng_seed, purpose=purpose, candidate=player)
                    for player in (self.slots[swap[0]], self.slots[swap[1]])
                )
            )

        is_by_lot = False
        while best := self._best_swaps():
            is_by_lot = is_by_lot or len(best) > 1
            first, second = min(best, key=lot)
            self.slots[first], self.slots[second] = (
                self.slots[second],
                self.slots[first],
            )
        return is_by_lot

    def _best_swaps(self) -> list[Pair]:
        """Return the swaps that reduce repeats the most and move players least."""
        repeated = {
            slot
            for slot in range(len(self.slots))
            if slot not in self.fixed and self.is_repeat(slot)
        }
        best: list[Pair] = []
        best_key = (0, 0, 0)
        for first in sorted(repeated):
            for second in range(len(self.slots)):
                if (
                    second in self.fixed
                    or second in {first, _partner_slot(first)}
                    or (second in repeated and second < first)
                ):
                    continue
                key = self._swap_effect(first, second)
                if key[:2] >= (0, 0):
                    continue
                if not best or key < best_key:
                    best, best_key = [(first, second)], key
                elif key == best_key:
                    best.append((first, second))
        return best

    def _swap_effect(self, first: int, second: int) -> tuple[int, int, int]:
        """Return how a swap changes the repeats, the earlier counts and the distance.

        The change in repeats is compared first, then the change in the sum of
        the earlier counts, then the change in the distance moved from home.
        """
        a, b = self.slots[first], self.slots[second]
        mate_a = self.slots[_partner_slot(first)]
        mate_b = self.slots[_partner_slot(second)]
        now = self.earlier(first), self.earlier(second)
        after = (
            self.partners[frozenset((b, mate_a))],
            self.partners[frozenset((a, mate_b))],
        )
        repeats = sum(count > 0 for count in after) - sum(count > 0 for count in now)
        moved = (
            abs(first - self.home[b])
            + abs(second - self.home[a])
            - abs(first - self.home[a])
            - abs(second - self.home[b])
        )
        return repeats, sum(after) - sum(now), moved

    def match(self) -> bool:
        """Re-form the teams by a minimum-cost matching if that is a better draw.

        A pair costs more than every sum of counts together if it repeats a
        partnership, plus the number of times it has: so the matching has the
        fewest repeats, and of those the smallest sum of earlier counts. Of
        equally good matchings, the one that keeps the most teams as they
        stand is taken.

        It runs only from round 3, where no player is fixed. In rounds 1 and
        2 every player has had at most one partner, so a repeated team
        always has a player who is not a top player, and swapping that
        player with one who is not fixed in another team leaves both new
        teams without a repeat: the swaps alone remove every repeat.

        Returns:
            Whether the teams changed.
        """
        if not self.repeats():
            return False
        count = len(self.slots)
        # More than the sum of all the teams' counts, `count / 2` teams with
        # at most the highest count each.
        repeat_cost = count // 2 * max(self.partners.values()) + 1

        # The costs are multiplied to leave room for one more per team that
        # does not stand as it is.
        scale = count // 2 + 1

        def worth(u: int, v: int) -> int:
            earlier = self.partners[frozenset((self.slots[u], self.slots[v]))]
            return repeat_cost * (earlier > 0) + earlier

        def cost(u: int, v: int) -> int:
            return scale * worth(u, v) + (v != _partner_slot(u))

        matched = min_cost_matching(
            count,
            ((u, v, cost(u, v)) for u in range(count) for v in range(u + 1, count)),
        )
        current = sum(
            worth(slot, _partner_slot(slot))
            for slot in range(count)
            if slot < _partner_slot(slot)
        )
        if sum(worth(u, v) for u, v in matched) >= current:
            return False
        self._lay_out(matched)
        return True

    def _lay_out(self, teams: Sequence[Pair]) -> None:
        """Place the new teams where their players move least (ADR-011).

        A team that is already in place stays. The others, the best-placed
        first, each take the free place for a team that moves its two players
        the shortest sum of distances from their homes, the better-placed
        player first.
        """
        old = list(self.slots)
        new: list[PlayerId | None] = [None] * len(old)
        moving: list[Pair] = []
        for u, v in teams:
            if v == _partner_slot(u):
                new[u], new[v] = old[u], old[v]
            else:
                moving.append((u, v))
        moving.sort(key=lambda pair: min(self.home[old[slot]] for slot in pair))
        for u, v in moving:
            a, b = sorted((old[u], old[v]), key=self.home.__getitem__)
            best_slot, best_cost = 0, -1
            for slot in range(len(old)):
                if slot > _partner_slot(slot) or new[slot] is not None:
                    continue
                cost = abs(slot - self.home[a]) + abs(
                    _partner_slot(slot) - self.home[b]
                )
                if best_cost < 0 or cost < best_cost:
                    best_slot, best_cost = slot, cost
            new[best_slot], new[_partner_slot(best_slot)] = a, b
        self.slots = [player for player in new if player is not None]

    def groups(self, *, has_top_players: bool) -> tuple[MonsterGroup, ...]:
        """Return the groups in slot order, with their teams (BR-060)."""
        return tuple(
            MonsterGroup(
                team_1=(self.slots[slot], self.slots[slot + 3]),
                team_2=(self.slots[slot + 1], self.slots[slot + 2]),
                top_player=self.slots[slot] if has_top_players else None,
                is_team_1_repeat=self.is_repeat(slot),
                is_team_2_repeat=self.is_repeat(slot + 1),
            )
            for slot in range(0, len(self.slots), GROUP_SIZE)
        )
