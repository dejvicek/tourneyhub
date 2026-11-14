"""A Lord have mercy knockout as stored, read into the engine's re-mix state.

Its pairs change every round (BR-084), so it is not a fixed bracket: every
drawn round is stored with its sides and their players, and a later round
exists only once it is drawn (BR-140, DATA-MODEL D4). `knockout_bracket`
returns None for it; this loader reads it instead.
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
    players_who_left,
    remix_state,
)
from tourneyhub.engine.tournaments import MonsterKnockoutMode
from tourneyhub.services.tournaments.shared import _main_entries, knockout_phase


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
        key=key, side_1=_team(side_1), side_2=_team(side_2), outcome=match.outcome
    )


def _team(side: MatchSide) -> Team | None:
    """A stored side's pair, its players sorted; None for a bye (BR-041)."""
    if side.is_bye:
        return None
    first, second = sorted(PlayerId(row.player_id) for row in side.players)
    return first, second


def left_player_ids(
    tournament: Tournament, remix: RemixKnockout
) -> frozenset[PlayerId]:
    """The players still in whose main entry is disabled (BR-147, BR-155).

    Without replacements they stay in the draw (BR-149); the read model shows
    them (FR-049).
    """
    disabled = (
        PlayerId(member.player_id)
        for entry in _main_entries(tournament)
        if entry.is_disabled
        for member in entry.members
    )
    return players_who_left(remix.state, disabled)
