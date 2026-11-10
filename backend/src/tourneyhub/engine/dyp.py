"""DYP halves and partners (BR-031, BR-032, BR-033)."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from tourneyhub.engine.errors import (
    DypHalvesUnequalError,
    NotEnoughPlayersError,
    TooManyLeftOutError,
)
from tourneyhub.engine.ids import PlayerId, ensure_distinct
from tourneyhub.engine.lots import order_by_lot
from tourneyhub.engine.ranking import RankedPlayer

DYP_MINIMUM_PLAYERS = 4
"""The fewest players a DYP tournament takes (BR-031)."""


class DypHalf(StrEnum):
    """Where a DYP player stands before the draw (DATA-MODEL `dyp_halves.half`)."""

    TOP = "top"
    BOTTOM = "bottom"
    LEFT_OUT = "left_out"


@dataclass(frozen=True, slots=True, kw_only=True)
class DypHalves:
    """A DYP tournament's halves (BR-032).

    Attributes:
        top: The top half.
        bottom: The bottom half, as large as the top half.
        left_out: With an odd number of players, the one who does not play.
        is_left_out_by_lot: A lot chose `left_out` (ADR-009); false when the
            organizer did, or when nobody is left out.
        is_boundary_by_lot: The last top-half player and the first bottom-half
            player tie on every league-ranking criterion, so the ranking's lot
            decided which half each is in (BR-020, ADR-009).
    """

    top: tuple[PlayerId, ...]
    bottom: tuple[PlayerId, ...]
    left_out: PlayerId | None
    is_left_out_by_lot: bool
    is_boundary_by_lot: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class DypPair:
    """A drawn DYP pair: a top-half player and their partner (BR-033).

    Attributes:
        top: The top-half player.
        bottom: The bottom-half partner drawn for them.
        is_drawn_by_lot: The partner was drawn by lot (ADR-009); always true
            for pairs from `draw_partners`.
    """

    top: PlayerId
    bottom: PlayerId
    is_drawn_by_lot: bool


def left_out_purpose(draw_counter: int) -> str:
    """Name the lot that leaves a player out, `dyp-left-out:<n>` (BR-032, ADR-010)."""
    return f"dyp-left-out:{draw_counter}"


def partner_purpose(draw_counter: int) -> str:
    """Name the lot that draws partners, `dyp-partner:<n>` (BR-033, ADR-010)."""
    return f"dyp-partner:{draw_counter}"


def _check_player_count(count: int) -> None:
    if count < DYP_MINIMUM_PLAYERS:
        raise NotEnoughPlayersError(minimum=DYP_MINIMUM_PLAYERS, given=count)


def split_halves_by_ranking(
    ranking: Iterable[RankedPlayer], *, rng_seed: bytes, draw_counter: int
) -> DypHalves:
    """Split the DYP players into halves by league ranking (BR-031, BR-032).

    With an odd number of players, the first player of the lot
    `dyp-left-out:<draw_counter>`, drawn among all of them, is left out. The
    top half is the better-ranked half of the rest, the bottom half the other.
    The halves mark the left-out player as drawn by lot, and the boundary
    between them as drawn by lot when the players on either side of it share
    a tie group in the league ranking (ADR-009).

    Args:
        ranking: The tournament's players with their league-ranking positions
            (BR-020).
        rng_seed: The tournament's seed (ADR-010).
        draw_counter: The tournament's draw counter (ADR-010).

    Returns:
        Both halves in ranking order, best-ranked first.

    Raises:
        NotEnoughPlayersError: Fewer than 4 players (BR-031).
        ValueError: A player is given twice.
    """
    players = sorted(ranking, key=lambda ranked: ranked.position)
    ensure_distinct(ranked.player_id for ranked in players)
    _check_player_count(len(players))
    left_out = None
    if len(players) % 2 == 1:
        left_out = order_by_lot(
            (ranked.player_id for ranked in players),
            rng_seed=rng_seed,
            purpose=left_out_purpose(draw_counter),
        )[0]
    playing = [ranked for ranked in players if ranked.player_id != left_out]
    half = len(playing) // 2
    return DypHalves(
        top=tuple(ranked.player_id for ranked in playing[:half]),
        bottom=tuple(ranked.player_id for ranked in playing[half:]),
        left_out=left_out,
        is_left_out_by_lot=left_out is not None,
        is_boundary_by_lot=playing[half - 1].tie_group == playing[half].tie_group,
    )


def check_hand_halves(halves: Mapping[PlayerId, DypHalf]) -> DypHalves:
    """Check halves the organizer set by hand (BR-031, BR-032).

    Every player is in a half or left out; with an odd number, one is left
    out, and both halves have the same size. Equal halves and at most one
    left out together give exactly one left out with an odd number and none
    with an even one.

    Args:
        halves: Every DYP player of the tournament with their half.

    Returns:
        The halves, each ordered by player id, since a hand-set half has no
        order of its own. Nothing in them is marked as decided by lot.

    Raises:
        NotEnoughPlayersError: Fewer than 4 players, the left-out one
            included (BR-031).
        TooManyLeftOutError: More than one player left out (BR-032).
        DypHalvesUnequalError: The halves differ in size (BR-032).
    """
    _check_player_count(len(halves))

    def members(half: DypHalf) -> tuple[PlayerId, ...]:
        return tuple(sorted(player for player, at in halves.items() if at is half))

    top, bottom, left_out = (members(half) for half in DypHalf)
    if len(left_out) > 1:
        raise TooManyLeftOutError(maximum=1, given=len(left_out))
    if len(top) != len(bottom):
        raise DypHalvesUnequalError(top=len(top), bottom=len(bottom))
    return DypHalves(
        top=top,
        bottom=bottom,
        left_out=next(iter(left_out), None),
        is_left_out_by_lot=False,
        is_boundary_by_lot=False,
    )


def draw_partners(
    halves: DypHalves, *, rng_seed: bytes, draw_counter: int
) -> tuple[DypPair, ...]:
    """Draw each top-half player a partner from the bottom half (BR-033, ADR-010).

    The bottom half is ordered by the lot `dyp-partner:<draw_counter>`, and
    the n-th top-half player, ordered by player id, gets the n-th player of
    that order. Neither half's stored order matters (`dyp_halves` keeps
    none). A "new DYP draw" increments the draw counter.

    Returns:
        One pair per top-half player, ordered by the top-half player's id,
        each marked as drawn by lot (ADR-009).

    Raises:
        DypHalvesUnequalError: The halves differ in size (BR-032).
    """
    if len(halves.top) != len(halves.bottom):
        raise DypHalvesUnequalError(top=len(halves.top), bottom=len(halves.bottom))
    drawn = order_by_lot(
        halves.bottom, rng_seed=rng_seed, purpose=partner_purpose(draw_counter)
    )
    return tuple(
        DypPair(top=top, bottom=bottom, is_drawn_by_lot=True)
        for top, bottom in zip(sorted(halves.top), drawn, strict=True)
    )
