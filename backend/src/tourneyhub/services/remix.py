"""The Lord have mercy knockout: draw the next round, and read it round by round.

BR-084, BR-140 to BR-144, BR-155, BR-156, BR-130, FR-049, ADR-010. Its pairs
change every round, so only the rounds drawn so far are stored, each with its
sides and their players (D4); round 1 comes from the start (`services.knockout`).
Every write locks the league row, then the tournament row (ADR-008). A drawn
round stores no participation (D5) and takes the free fields (BR-130).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid7

from sqlalchemy.orm import Session

from tourneyhub.db.models.matches import Match, MatchSide, MatchSidePlayer, Round
from tourneyhub.db.models.tournaments import Tournament
from tourneyhub.engine.knockout import RoundName, round_name
from tourneyhub.engine.remix import RemixMatch, draw_next_round
from tourneyhub.engine.tournaments import (
    KnockoutMatchFormat,
    MatchFormat,
    MatchKind,
    Outcome,
    TournamentState,
)
from tourneyhub.errors import (
    ConflictError,
    ErrorCode,
    NotFoundError,
    RuleViolationError,
)
from tourneyhub.services.knockout import _score
from tourneyhub.services.tournaments import Clock
from tourneyhub.services.tournaments.fields import _fill_fields
from tourneyhub.services.tournaments.remix import (
    RemixKnockout,
    is_remix,
    left_player_ids,
    remix_knockout,
)
from tourneyhub.services.tournaments.results import _match_format
from tourneyhub.services.tournaments.shared import (
    _lock_tournament,
    _match_slots,
    _played,
    _require_open_season,
    knockout_phase,
)

type RemixMatchState = Literal["bye", "played", "on_field", "ready"]


@dataclass(frozen=True, slots=True, kw_only=True)
class RemixSideView:
    """A side of a match: a pair of players, or a bye (BR-041).

    `entry_id` is the round-1 pair entry; a later round's pair has none (D4).
    `player_ids` is empty for a bye. `left_player_ids` are the pair's players
    whose main entry is disabled and who stay in the draw (BR-147, BR-149).
    """

    player_ids: tuple[UUID, ...]
    entry_id: UUID | None
    is_bye: bool
    left_player_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class RemixMatchView:
    """A match of a drawn round (BR-155).

    `number` counts the tournament's matches, the earlier phases' first; a bye
    has none (BR-041) and the third-place match comes after the final. `score`
    is side 1's, as in the bracket. `winner_locked` says a later round is
    drawn, so the result can be corrected but not cleared or given to the
    other pair (BR-146).
    """

    match_id: UUID
    number: int | None
    position: int
    kind: MatchKind
    state: RemixMatchState
    sides: tuple[RemixSideView, RemixSideView]
    outcome: Outcome | None
    is_walkover: bool
    score: tuple[int, int] | None
    match_format: MatchFormat
    field_number: int | None
    winner_locked: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class RemixRoundView:
    """A drawn round with its matches; `result_count` counts the results in it."""

    round_id: UUID
    round_no: int
    name: RoundName
    result_count: int
    matches: tuple[RemixMatchView, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class RemixKnockoutView:
    """A Lord have mercy knockout round by round, computed on read (D4, BR-155).

    `size` is twice the round-1 matches; `round_count` how many rounds the
    knockout will have, of which only `rounds` are drawn so far.
    `can_draw_next` says the organizer can draw the next round (BR-140), and
    `left_player_ids` are all the players who have left but stay in (FR-049).
    """

    phase_id: UUID
    size: int
    round_count: int
    third_place_match: bool
    match_format: MatchFormat
    final_match_format: KnockoutMatchFormat | None
    can_draw_next: bool
    left_player_ids: tuple[UUID, ...]
    rounds: tuple[RemixRoundView, ...]


def draw_knockout_round(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    expected_round_no: int,
    clock: Clock,
) -> RemixKnockoutView:
    """Draw the next round of a Lord have mercy knockout (BR-140 to BR-144, BR-156).

    The round before must be complete: every match has a result, byes aside
    (BR-140). The players who went through are paired by lot, the final's
    round with the third-place match among the semifinal losers (BR-141,
    BR-142, BR-144); the lots hold no draw counter, so the same players always
    give the same pairs (ADR-010, BR-156). Disabled players still in are drawn
    like everyone else (BR-149). The round takes the free fields, the
    third-place match after the final (BR-130), and locks the winners of the
    round before (BR-146).

    A closed season is 409 `season_closed`, a tournament not in progress 409
    `tournament_not_in_progress` (detail `state`), no knockout 404
    `knockout_not_found`, a fixed-pair knockout 422 `format_not_supported`
    (detail `format`, `mode`), an `expected_round_no` other than the rounds
    drawn plus one 409 `round_number_changed` (detail `current_round_no`, the
    newest round's), so a repeat draws nothing (ADR-008), and a match of the
    newest round without a result 422 `round_not_complete` (detail
    `matches_left`).
    """
    league, tournament = _lock_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user_id,
        rounds=True,
    )
    _require_open_season(league, tournament)
    if tournament.state is not TournamentState.IN_PROGRESS:
        raise ConflictError(
            ErrorCode.TOURNAMENT_NOT_IN_PROGRESS, state=tournament.state
        )
    remix = _require_remix(tournament)
    state = remix.state
    if expected_round_no != state.rounds_drawn + 1:
        raise ConflictError(
            ErrorCode.ROUND_NUMBER_CHANGED, current_round_no=state.rounds_drawn
        )
    if not state.can_draw_next:
        left = sum(
            not match.has_bye and match.outcome is None for match in state.newest_round
        )
        raise RuleViolationError(ErrorCode.ROUND_NOT_COMPLETE, matches_left=left)
    now = clock()
    drawn = draw_next_round(state, rng_seed=tournament.rng_seed)
    remix.phase.rounds.append(_stored_round(expected_round_no, drawn, now))
    tournament.updated_at = now
    session.flush()  # the matches exist before a field references one
    _fill_fields(tournament, _match_slots(tournament), now)
    session.flush()
    return _remix_view(tournament, _loaded(tournament))


def _require_remix(tournament: Tournament) -> RemixKnockout:
    """The tournament's Lord have mercy knockout, else 404 or 422.

    No knockout is 404 `knockout_not_found`; a fixed-pair one is 422
    `format_not_supported` (detail `format`, `mode`).
    """
    phase = knockout_phase(tournament)
    if phase is None:
        raise NotFoundError(ErrorCode.KNOCKOUT_NOT_FOUND)
    if not is_remix(phase):
        raise RuleViolationError(
            ErrorCode.FORMAT_NOT_SUPPORTED,
            format=phase.format,
            mode=phase.monster_knockout_mode,
        )
    return _loaded(tournament)


def _loaded(tournament: Tournament) -> RemixKnockout:
    remix = remix_knockout(tournament)
    if remix is None:  # the caller checked for a Lord have mercy knockout
        msg = "the tournament has no Lord have mercy knockout"
        raise ValueError(msg)
    return remix


def _stored_round(round_no: int, drawn: tuple[RemixMatch, ...], now: datetime) -> Round:
    """A drawn round as rows: a match per pair of pairs, no participation (D5)."""
    return Round(
        id=uuid7(),
        round_no=round_no,
        created_at=now,
        matches=[
            Match(
                id=uuid7(),
                position=match.key.position,
                kind=match.key.kind,
                outcome=None,
                is_walkover=False,
                result_entered_at=None,
                requeued_at=None,
                created_at=now,
                sides=[
                    MatchSide(
                        side=number,
                        entry_id=None,
                        is_bye=False,
                        created_at=now,
                        players=[
                            MatchSidePlayer(
                                side=number, player_id=player, created_at=now
                            )
                            for player in pair
                        ],
                    )
                    for number, pair in ((1, match.side_1), (2, match.side_2))
                    if pair is not None  # a later round has no bye (BR-141)
                ],
                games=[],
            )
            for match in drawn
        ],
        participation=[],
    )


def _remix_view(tournament: Tournament, remix: RemixKnockout) -> RemixKnockoutView:
    """The knockout round by round (BR-155)."""
    state = remix.state
    left = left_player_ids(tournament, remix)
    on_field = {
        field.match_id: field.number
        for field in tournament.fields
        if field.match_id is not None
    }
    earlier = sum(
        len(_played(round_))
        for phase in tournament.phases
        if phase.position < remix.phase.position
        for round_ in phase.rounds
    )
    numbers: dict[UUID, int] = {}
    for match in state.matches:
        if not match.has_bye:
            numbers[remix.rows[match.key].id] = earlier + len(numbers) + 1

    def side_view(row: MatchSide) -> RemixSideView:
        players = tuple(sorted(p.player_id for p in row.players))
        return RemixSideView(
            player_ids=players,
            entry_id=row.entry_id,
            is_bye=row.is_bye,
            left_player_ids=tuple(p for p in players if p in left),
        )

    def match_view(match: RemixMatch) -> RemixMatchView:
        row = remix.rows[match.key]
        round_ = remix.rounds[match.key.round_no]
        side_1, side_2 = sorted(row.sides, key=lambda side: side.side)
        field_number = on_field.get(row.id)
        if match.has_bye:
            match_state: RemixMatchState = "bye"
        elif match.outcome is not None:
            match_state = "played"
        else:
            match_state = "ready" if field_number is None else "on_field"
        return RemixMatchView(
            match_id=row.id,
            number=numbers.get(row.id),
            position=row.position,
            kind=row.kind,
            state=match_state,
            sides=(side_view(side_1), side_view(side_2)),
            outcome=row.outcome,
            is_walkover=row.is_walkover,
            score=_score(row),
            match_format=_match_format(remix.phase, round_, row),
            field_number=field_number,
            winner_locked=not match.has_bye and match.key.round_no < state.rounds_drawn,
        )

    return RemixKnockoutView(
        phase_id=remix.phase.id,
        size=state.size,
        round_count=state.round_count,
        third_place_match=state.third_place_match,
        match_format=remix.phase.match_format,
        final_match_format=remix.phase.final_match_format,
        can_draw_next=state.can_draw_next,
        left_player_ids=tuple(sorted(left)),
        rounds=tuple(
            RemixRoundView(
                round_id=remix.rounds[round_no].id,
                round_no=round_no,
                name=round_name(round_no, state.round_count),
                result_count=sum(match.outcome is not None for match in matches),
                matches=tuple(match_view(match) for match in matches),
            )
            for round_no, matches in enumerate(state.rounds, start=1)
        ),
    )
