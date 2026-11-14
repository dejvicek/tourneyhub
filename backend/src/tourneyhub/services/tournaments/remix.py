"""A Lord have mercy knockout as stored, read into the engine's re-mix state.

Its pairs change every round (BR-084), so it is not a fixed bracket: every
drawn round is stored with its sides and their players, and a later round
exists only once it is drawn (BR-140, DATA-MODEL D4). A player who came in as
a replacement names the player they came in for on their side-player row
(BR-148). `knockout_bracket` returns None for it; this loader reads it
instead.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from tourneyhub.db.models.matches import Match, MatchSide, Round
from tourneyhub.db.models.tournaments import Tournament, TournamentPhase
from tourneyhub.engine.ids import PlayerId
from tourneyhub.engine.knockout import MatchKey, match_key
from tourneyhub.engine.monster_dyp import Team
from tourneyhub.engine.remix import (
    RemixMatch,
    RemixState,
    Replacement,
    ReplacementPlan,
    plan_replacements,
    players_who_left,
    remix_state,
)
from tourneyhub.engine.tournaments import MonsterKnockoutMode, TournamentState
from tourneyhub.services.tournaments.play import group_standings, tie_groups
from tourneyhub.services.tournaments.shared import (
    _group_phase,
    _main_entries,
    knockout_phase,
)


def is_remix(phase: TournamentPhase) -> bool:
    """The knockout re-mixes its pairs every round: Lord have mercy (BR-084)."""
    return phase.monster_knockout_mode is MonsterKnockoutMode.LORD_HAVE_MERCY


@dataclass(frozen=True, slots=True, kw_only=True)
class RemixKnockout:
    """A Lord have mercy knockout with its stored rounds checked (BR-140 to BR-144).

    `keys` maps each stored match's id to its key, `rows` each key to its
    match, and `rounds` each drawn round's number to its row.
    """

    phase: TournamentPhase
    state: RemixState
    keys: Mapping[UUID, MatchKey]
    rows: Mapping[MatchKey, Match]
    rounds: Mapping[int, Round]


def remix_knockout(tournament: Tournament) -> RemixKnockout | None:
    """The tournament's Lord have mercy knockout; None for none or a fixed one.

    The tournament needs its rounds loaded in full. Each side's pair comes
    from its stored players, sorted; a bye side is None (BR-041). Stored
    rounds the engine refuses are a bug and raise `ValueError`.
    """
    phase = knockout_phase(tournament)
    if phase is None or not is_remix(phase):
        return None
    keys = {
        match.id: match_key(
            round_no=round_.round_no, kind=match.kind, position=match.position
        )
        for round_ in phase.rounds
        for match in round_.matches
    }
    rows = {
        keys[match.id]: match for round_ in phase.rounds for match in round_.matches
    }
    state = remix_state(
        (_remix_match(key, match) for key, match in rows.items()),
        third_place_match=bool(phase.third_place_match),
    )
    return RemixKnockout(
        phase=phase,
        state=state,
        keys=keys,
        rows=rows,
        rounds={round_.round_no: round_ for round_ in phase.rounds},
    )


def _remix_match(key: MatchKey, match: Match) -> RemixMatch:
    side_1, side_2 = sorted(match.sides, key=lambda side: side.side)
    return RemixMatch(
        key=key,
        side_1=_team(side_1),
        side_2=_team(side_2),
        outcome=match.outcome,
        replacements=tuple(
            sorted(
                (
                    Replacement(
                        player_id=PlayerId(row.player_id),
                        replaced_player_id=PlayerId(row.replaced_player_id),
                    )
                    for side in match.sides
                    for row in side.players
                    if row.replaced_player_id is not None
                ),
                key=lambda replacement: replacement.player_id,
            )
        ),
    )


def _team(side: MatchSide) -> Team | None:
    """A stored side's pair, its players sorted; None for a bye (BR-041)."""
    if side.is_bye:
        return None
    first, second = sorted(PlayerId(row.player_id) for row in side.players)
    return first, second


def disabled_players(tournament: Tournament) -> frozenset[PlayerId]:
    """The players whose main entry is disabled now (FR-044, BR-147)."""
    return frozenset(
        PlayerId(member.player_id)
        for entry in _main_entries(tournament)
        if entry.is_disabled
        for member in entry.members
    )


def left_player_ids(
    tournament: Tournament, remix: RemixKnockout
) -> frozenset[PlayerId]:
    """The players still in whose main entry is disabled (BR-147, BR-155).

    In a drawn round they stay in, and their pair loses by walkover (BR-149,
    BR-152); the read model shows them (FR-049).
    """
    return players_who_left(remix.state, disabled_players(tournament))


def standing_players(tournament: Tournament) -> tuple[tuple[PlayerId, ...], ...]:
    """The group phase's standing as tie groups of players, best first (BR-074).

    A Lord have mercy knockout follows Monster DYP rounds, whose main entries
    are single players (BR-084); each entry stands for its player.
    """
    group = _group_phase(tournament)
    if group is None:  # a Lord have mercy knockout follows Monster DYP rounds
        msg = "the Lord have mercy knockout has no group phase"
        raise ValueError(msg)
    player_of = {
        entry.id: PlayerId(member.player_id)
        for entry in _main_entries(tournament)
        for member in entry.members
    }
    return tuple(
        tuple(player_of[entry_id] for entry_id in group_)
        for group_ in tie_groups(group_standings(tournament, group))
    )


def next_draw_plan(
    tournament: Tournament, remix: RemixKnockout
) -> ReplacementPlan | None:
    """The replacements the next draw would make now, if it can be drawn (FR-049).

    None unless the tournament is in progress and the next round can be drawn
    (BR-140). The draw itself makes the same plan (`plan_replacements`).
    """
    if (
        tournament.state is not TournamentState.IN_PROGRESS
        or not remix.state.can_draw_next
    ):
        return None
    return plan_replacements(
        remix.state,
        disabled=disabled_players(tournament),
        standing=standing_players(tournament),
        rng_seed=tournament.rng_seed,
    )
