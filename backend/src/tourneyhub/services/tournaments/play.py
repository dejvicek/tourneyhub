"""The play view and the group standings (round robin and Swiss)."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import assert_never
from uuid import UUID

from sqlalchemy.orm import Session

from tourneyhub.db.models.leagues import League
from tourneyhub.db.models.matches import Match
from tourneyhub.db.models.tournaments import Tournament, TournamentPhase
from tourneyhub.engine.fields import waiting_order
from tourneyhub.engine.ids import EntryId
from tourneyhub.engine.standings import (
    FormResult,
    PlayedMatch,
    RoundRobinTiebreaker,
    StandingRow,
    round_robin_standings,
)
from tourneyhub.engine.swiss import (
    SwissMatch,
    SwissRound,
    SwissStanding,
    swiss_standings,
)
from tourneyhub.engine.tournaments import (
    MatchOutcome,
    Participation,
    PhaseFormat,
    Tiebreaker,
)
from tourneyhub.services.leagues import get_league
from tourneyhub.services.tournaments.shared import (
    _field_slots,
    _group_phase,
    _is_done,
    _load_tournament,
    _main_entries,
    _match_slots,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class BusyField:
    """A field that holds players of a waiting match (BR-131)."""

    field_id: UUID
    player_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class WaitingMatch:
    """A match waiting for a field, with the fields its players are on (FR-092)."""

    match_id: UUID
    busy: tuple[BusyField, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class GroupStandingRow:
    """One entry's line in the group-phase standings, of any format (FR-060).

    A round robin's rows come from BR-101, a Swiss's from BR-070 to BR-074.
    `place` is shared by entries still level (BR-074). `form` and `ahead_by`
    are the round robin's: a Swiss has an empty form and no `ahead_by`, since
    its tie-breakers are the phase's own (FR-043). `bh1` and `bh2` are the
    Swiss's (BR-073), None in a round robin. `game_difference` is games won
    minus games lost (BR-101); it ranks only a round robin.
    """

    place: int
    entry_id: EntryId
    played: int
    won: int
    drawn: int
    lost: int
    sat_out: int
    points: int
    game_difference: int
    score_difference: int
    form: tuple[FormResult, ...]
    ahead_by: RoundRobinTiebreaker | None
    bh1: int | None
    bh2: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class PlayView:
    """The running group phase as the play screens read it, computed on read.

    `standings` are the group phase's: a round robin's (BR-101) or a Swiss's
    (BR-070 to BR-074); a Monster DYP has none yet. `group_done` says every
    group-phase match has a result (FR-040); in a Swiss, every match of the
    newest round, since the rounds before it are complete.
    """

    waiting: tuple[WaitingMatch, ...]
    standings: tuple[GroupStandingRow, ...]
    group_done: bool


def _played_match(match: Match) -> PlayedMatch:
    """A round-robin match with its result, as the standings read it."""
    side_1, side_2 = (side.entry_id for side in match.sides)
    if side_1 is None or side_2 is None or match.outcome is None:
        msg = f"match {match.id} has no result between two entries"
        raise ValueError(msg)
    return PlayedMatch(
        side_1=EntryId(side_1),
        side_2=EntryId(side_2),
        outcome=match.outcome,
        games=tuple(game.winner for game in match.games),
        is_walkover=match.is_walkover,
        scores=tuple(
            (game.score_1, game.score_2)
            for game in match.games
            if game.score_1 is not None and game.score_2 is not None
        ),
    )


def _standings_of(
    tournament: Tournament, phase: TournamentPhase
) -> tuple[StandingRow, ...]:
    """The round robin's standings now (BR-070, BR-101).

    A sit-out is counted once every match of its round has a result: the schedule
    holds every round from the start, and a sit-out in a round still to come
    has not happened yet. It earns no points in a round robin (BR-071).
    """
    main = sorted(
        _main_entries(tournament), key=lambda e: (e.seed is None, e.seed or 0, e.id)
    )
    return round_robin_standings(
        (EntryId(entry.id) for entry in main),
        matches=[
            _played_match(match)
            for round_ in phase.rounds
            for match in round_.matches
            if match.outcome is not None
        ],
        match_format=phase.match_format,
        sit_outs=[
            EntryId(row.entry_id)
            for round_ in phase.rounds
            if all(match.outcome is not None for match in round_.matches)
            for row in round_.participation
            if row.status is Participation.SAT_OUT
        ],
    )


def _swiss_rounds(phase: TournamentPhase) -> tuple[SwissRound, ...]:
    """A Swiss phase's stored rounds as the engine reads them (D5, D11).

    A match's score difference sums the games that have a score (BR-073); a
    walkover has none. The entries sitting a round out are its `sat_out` rows;
    a disabled or not yet joined entry is in neither list (BR-064, BR-067).
    """
    rounds: list[SwissRound] = []
    for round_ in phase.rounds:
        matches: list[SwissMatch] = []
        for match in round_.matches:
            side_1, side_2 = (side.entry_id for side in match.sides)
            if side_1 is None or side_2 is None:
                msg = f"Swiss match {match.id} has a side without an entry"
                raise ValueError(msg)
            matches.append(
                SwissMatch(
                    side_1=EntryId(side_1),
                    side_2=EntryId(side_2),
                    outcome=None
                    if match.outcome is None
                    else MatchOutcome(match.outcome),
                    score_difference=sum(
                        game.score_1 - game.score_2
                        for game in match.games
                        if game.score_1 is not None and game.score_2 is not None
                    ),
                )
            )
        rounds.append(
            SwissRound(
                round_no=round_.round_no,
                matches=tuple(matches),
                sat_out=tuple(
                    EntryId(row.entry_id)
                    for row in sorted(round_.participation, key=lambda r: r.entry_id)
                    if row.status is Participation.SAT_OUT
                ),
            )
        )
    return tuple(rounds)


def _swiss_standings_of(
    tournament: Tournament, phase: TournamentPhase
) -> tuple[SwissStanding, ...]:
    """The Swiss standings now, by position (BR-070 to BR-074, BR-076, FR-043).

    Every main entry is in them, disabled ones included (BR-064). A sit-out
    earns the phase's points as soon as its round is drawn (BR-076); the
    tie-breakers are the phase's, in its order; the lot uses the tournament's
    seed (ADR-010).
    """
    return swiss_standings(
        (EntryId(entry.id) for entry in _main_entries(tournament)),
        _swiss_rounds(phase),
        tiebreakers=[Tiebreaker(t) for t in phase.tiebreakers or ()],
        sit_out_points=phase.sit_out_points or 0,  # the CHECK sets it for Swiss
        rng_seed=tournament.rng_seed,
    )


def _swiss_game_differences(
    tournament: Tournament, phase: TournamentPhase
) -> dict[EntryId, int]:
    """Each entry's games won minus games lost in a Swiss (BR-101).

    Shown only, never a Swiss tie-breaker (BR-072). The round-robin tally
    counts the games the same way, a walkover counting the games needed to
    win, so only its `game_difference` is read here.
    """
    return {
        row.entry_id: row.game_difference
        for row in round_robin_standings(
            (EntryId(entry.id) for entry in _main_entries(tournament)),
            matches=[
                _played_match(match)
                for round_ in phase.rounds
                for match in round_.matches
                if match.outcome is not None
            ],
            match_format=phase.match_format,
            sit_outs=[],
        )
    }


def group_standings(
    tournament: Tournament, phase: TournamentPhase
) -> tuple[GroupStandingRow, ...]:
    """The group phase's standings now, best first (FR-060, ADR-009).

    A round robin's by BR-101 (`_standings_of`), a Swiss's by BR-070 to
    BR-074 (`_swiss_standings_of`). A Monster DYP has none yet.
    """
    match phase.format:
        case PhaseFormat.ROUND_ROBIN:
            return tuple(
                GroupStandingRow(
                    place=row.place,
                    entry_id=row.entry_id,
                    played=row.played,
                    won=row.won,
                    drawn=row.drawn,
                    lost=row.lost,
                    sat_out=row.sat_out,
                    points=row.points,
                    game_difference=row.game_difference,
                    score_difference=row.score_difference,
                    form=row.form,
                    ahead_by=row.ahead_by,
                    bh1=None,
                    bh2=None,
                )
                for row in _standings_of(tournament, phase)
            )
        case PhaseFormat.SWISS:
            games = _swiss_game_differences(tournament, phase)
            return tuple(
                GroupStandingRow(
                    place=row.place,
                    entry_id=row.entry_id,
                    played=row.played,
                    won=row.won,
                    drawn=row.drawn,
                    lost=row.lost,
                    sat_out=row.sat_out,
                    points=row.points,
                    game_difference=games[row.entry_id],
                    score_difference=row.score_difference,
                    form=(),
                    ahead_by=None,
                    bh1=row.bh1,
                    bh2=row.bh2,
                )
                for row in _swiss_standings_of(tournament, phase)
            )
        case PhaseFormat.MONSTER_DYP | PhaseFormat.SINGLE_ELIMINATION:
            return ()
        case _:
            assert_never(phase.format)


def tie_groups(rows: Iterable[GroupStandingRow]) -> tuple[tuple[EntryId, ...], ...]:
    """The standings as tie groups by place, best first (BR-074, BR-103).

    The knockout's cut and the places take these; where a strict order is
    needed, they apply their own lot (BR-074).
    """
    groups: dict[int, list[EntryId]] = {}
    for row in rows:
        groups.setdefault(row.place, []).append(row.entry_id)
    return tuple(tuple(groups[place]) for place in sorted(groups))


def read_play(
    session: Session, *, league_id: UUID, tournament_id: UUID, user_id: UUID
) -> PlayView:
    """Return the waiting list, the standings and the phase's end (FR-040, FR-060, FR-092).

    Read without a lock. Each waiting match names the fields its players are
    on, which is why it waits (BR-131). A field that points at a match the read
    did not see counts as free.
    """
    league = get_league(session, league_id=league_id, user_id=user_id)
    tournament = _load_tournament(session, league=league, tournament_id=tournament_id)
    slots = _match_slots(tournament)
    players = {slot.match_id: slot.player_ids or frozenset() for slot in slots}
    # The tournament is read in separate queries, so a write that commits between
    # them can leave a field pointing at a match that was not loaded; such a field
    # counts as free instead of failing the read.
    fields = [
        replace(field, match_id=None)
        if field.match_id is not None and field.match_id not in players
        else field
        for field in sorted(_field_slots(tournament), key=lambda f: f.number)
    ]
    on_fields = [
        (field.field_id, players[field.match_id])
        for field in fields
        if field.match_id is not None
    ]
    waiting = tuple(
        WaitingMatch(
            match_id=slot.match_id,
            busy=tuple(
                BusyField(field_id=field_id, player_ids=tuple(sorted(shared)))
                for field_id, on_field in on_fields
                if (shared := players[slot.match_id] & on_field)
            ),
        )
        for slot in waiting_order(matches=slots, fields=fields)
    )
    group = _group_phase(tournament)
    return PlayView(
        waiting=waiting,
        standings=() if group is None else group_standings(tournament, group),
        group_done=group is not None and bool(group.rounds) and _is_done(group),
    )


def view_group_standings(
    session: Session, *, league: League, tournament_id: UUID, past_setup: bool = False
) -> tuple[GroupStandingRow, ...]:
    """Return the group phase's standings now: a round robin's or a Swiss's (FR-060).

    The same standings as the play read's (`read_play`); none without a group
    phase or for a Monster DYP. With `past_setup`, a tournament in setup is
    404 `tournament_not_found` (FR-070).
    """
    tournament = _load_tournament(
        session, league=league, tournament_id=tournament_id, past_setup=past_setup
    )
    group = _group_phase(tournament)
    return () if group is None else group_standings(tournament, group)
