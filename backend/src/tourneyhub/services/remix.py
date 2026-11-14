"""The Lord have mercy knockout: draw the next round, and read it round by round.

BR-084, BR-140 to BR-149, BR-153 to BR-156, BR-130, FR-049, ADR-010. Its
pairs change every round, so only the rounds drawn so far are stored, each
with its sides and their players, a replacement naming the player they came
in for (D4); round 1 comes from the start (`services.knockout`). Every write
locks the league row, then the tournament row (ADR-008). A drawn round stores
no participation (D5) and takes the free fields (BR-130).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid7

from sqlalchemy.orm import Session

from tourneyhub.db.models.leagues import League
from tourneyhub.db.models.matches import Match, MatchSide, MatchSidePlayer, Round
from tourneyhub.db.models.tournaments import Tournament
from tourneyhub.engine.ids import PlayerId
from tourneyhub.engine.knockout import RoundName, round_name
from tourneyhub.engine.monster_dyp import Team
from tourneyhub.engine.remix import (
    RemixMatch,
    Replacement,
    allows_result,
    draw_next_round,
)
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
from tourneyhub.services.knockout import _remove_knockout
from tourneyhub.services.leagues import get_league
from tourneyhub.services.public import _shared_league
from tourneyhub.services.tournaments import Clock
from tourneyhub.services.tournaments.fields import _fill_fields
from tourneyhub.services.tournaments.remix import (
    RemixKnockout,
    disabled_players,
    left_player_ids,
    next_draw_plan,
    remix_knockout,
    standing_players,
)
from tourneyhub.services.tournaments.shared import (
    _load_tournament,
    _lock_tournament,
    _main_entries,
    _match_slots,
    _played,
    _require_open_season,
    knockout_phase,
    match_format_of,
    match_score,
)

type RemixMatchState = Literal["bye", "played", "on_field", "ready"]
type RemixPlayerStatus = Literal["still_in", "knocked_out", "replaced"]


@dataclass(frozen=True, slots=True, kw_only=True)
class RemixSideView:
    """A side of a match: a pair of players, or a bye (BR-041).

    `entry_id` is the round-1 pair entry; a later round's pair has none (D4).
    `player_ids` is empty for a bye. `left_player_ids` are the pair's players
    whose main entry is disabled and who stay in the draw (BR-147, BR-149).
    `replacements` are the pair's players who came in for a player who left,
    and for whom (BR-148, BR-155).
    """

    player_ids: tuple[UUID, ...]
    entry_id: UUID | None
    is_bye: bool
    left_player_ids: tuple[UUID, ...]
    replacements: tuple[Replacement, ...]


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
class RemixNextDrawView:
    """What the next draw would do now (FR-049, BR-148, BR-149).

    `replacements` come in for players who left, the replaced player with the
    best group-phase standing first; `staying_player_ids` have left but stay in
    the draw without a replacement, since nobody is available.
    """

    replacements: tuple[Replacement, ...]
    staying_player_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class RemixPlayerView:
    """A knockout player, for the organizer's disable switch (FR-044, BR-147).

    `entry_id` is the player's main entry, which the disable route takes.
    `status`: `still_in`, `knocked_out`, or `replaced` once a replacement came
    in for them (BR-153).
    """

    player_id: UUID
    entry_id: UUID
    status: RemixPlayerStatus
    is_disabled: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class RemixKnockoutView:
    """A Lord have mercy knockout round by round, computed on read (D4, BR-155).

    `size` is twice the round-1 matches; `round_count` how many rounds the
    knockout will have, of which only `rounds` are drawn so far.
    `can_draw_next` says the organizer can draw the next round (BR-140), and
    `left_player_ids` are all the players who have left but stay in (FR-049).
    The organizer's view also has `next_draw`, the replacements the next draw
    would make, while it can be drawn, and `players`, the knockout's players
    by group-phase standing; the share link's has neither (None and empty).
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
    next_draw: RemixNextDrawView | None
    players: tuple[RemixPlayerView, ...]


def draw_knockout_round(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    expected_round_no: int,
    clock: Clock,
) -> RemixKnockoutView:
    """Draw the next round of a Lord have mercy knockout (BR-140 to BR-149, BR-156).

    The round before must be complete: every match has a result, byes aside
    (BR-140). The players who went through are paired by lot, the final's
    round with the third-place match among the semifinal losers (BR-141,
    BR-142, BR-144); the lots hold no draw counter, so the same players always
    give the same pairs (ADR-010, BR-156). A player whose main entry is
    disabled now has left: the best-placed player who is knocked out comes in
    for them, or with nobody available they are drawn like everyone else
    (BR-147 to BR-149). The plan is the one `GET …/knockout/rounds` shows in
    `next_draw`, and each replacement is stored on their side-player row. The
    round takes the free fields, the third-place match after the final
    (BR-130), and locks the winners of the round before (BR-146).

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
    drawn = draw_next_round(
        state,
        rng_seed=tournament.rng_seed,
        disabled=disabled_players(tournament),
        standing=standing_players(tournament),
    )
    remix.phase.rounds.append(_stored_round(expected_round_no, drawn, now))
    tournament.updated_at = now
    session.flush()  # the matches exist before a field references one
    _fill_fields(tournament, _match_slots(tournament), now)
    session.flush()
    return _remix_view(tournament, _loaded(tournament), organizer=True)


def delete_knockout_round(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    round_id: UUID,
    user_id: UUID,
    clock: Clock,
) -> None:
    """Delete the newest round of a Lord have mercy knockout, with its results.

    FR-046, BR-146. The round is named by its id (ADR-008): an unknown one, a
    group round or a repeated delete is 404 `round_not_found`. A closed season
    is 409 `season_closed`, a fixed-pair knockout 422 `format_not_supported`
    (detail `format`, `mode`), a round that is not the newest 409
    `round_not_newest` (detail `round_id`, the newest round's). There is no
    check of the tournament's state: deleting the newest round of a finished
    tournament puts it back in progress (BR-095), and the season standings,
    computed on read, follow (BR-112).

    The fields let go of the round's matches and take the next ones that can
    be played (BR-130); the round before is unlocked, since the lock follows
    the newest round (BR-146), and drawing again gives the same pairs while
    the players are the same (BR-156). The round's replacements go with its
    side players, so they are undone: a re-enabled player is in the next draw
    again, and one who is still disabled is replaced again (BR-154). Deleting
    round 1 deletes the knockout as `DELETE …/phases/{id}` does (BR-087).
    `is_disabled` stays as it is.
    """
    league, tournament = _lock_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user_id,
        rounds=True,
    )
    _require_open_season(league, tournament)
    phase = knockout_phase(tournament)
    round_ = next(
        (r for r in ([] if phase is None else phase.rounds) if r.id == round_id),
        None,
    )
    if phase is None or round_ is None:
        raise NotFoundError(ErrorCode.ROUND_NOT_FOUND)
    remix = _require_remix(tournament)
    newest = remix.rounds[remix.state.rounds_drawn]
    if round_ is not newest:
        raise ConflictError(ErrorCode.ROUND_NOT_NEWEST, round_id=str(newest.id))
    now = clock()
    if round_.round_no == 1:
        _remove_knockout(session, tournament, phase, now)
        return
    matches = {match.id for match in round_.matches}
    for field in tournament.fields:
        if field.match_id in matches:
            field.match_id = None
            field.updated_at = now
    session.flush()  # the fields let go of the matches before they are deleted
    phase.rounds.remove(round_)
    if tournament.state is TournamentState.FINISHED:
        tournament.state = TournamentState.IN_PROGRESS
    tournament.updated_at = now
    session.flush()  # the matches are gone before the free fields take the next ones
    _fill_fields(tournament, _match_slots(tournament), now)
    session.flush()


def read_knockout_rounds(
    session: Session, *, league_id: UUID, tournament_id: UUID, user_id: UUID
) -> RemixKnockoutView:
    """Return the organizer's Lord have mercy knockout round by round (BR-155).

    Read without a lock. See `view_knockout_rounds` for the refusals.
    """
    league = get_league(session, league_id=league_id, user_id=user_id)
    return view_knockout_rounds(
        session, league=league, tournament_id=tournament_id, organizer=True
    )


def view_knockout_rounds(
    session: Session,
    *,
    league: League,
    tournament_id: UUID,
    past_setup: bool = False,
    organizer: bool = False,
) -> RemixKnockoutView:
    """Return one of the league's Lord have mercy knockouts, read without a lock.

    A tournament without a knockout is 404 `knockout_not_found`; a fixed-pair
    knockout is 422 `format_not_supported` (detail `format`, `mode`), and its
    rounds are read with `…/bracket`. An unknown tournament, one of another
    league and, with `past_setup`, one in setup are 404 `tournament_not_found`
    (FR-070). With `organizer`, the view also has the next draw's plan and the
    players (FR-049).
    """
    tournament = _load_tournament(
        session, league=league, tournament_id=tournament_id, past_setup=past_setup
    )
    return _remix_view(tournament, _require_remix(tournament), organizer=organizer)


def read_shared_knockout_rounds(
    session: Session, *, share_token: str, tournament_id: UUID
) -> RemixKnockoutView:
    """Return a Lord have mercy knockout through the share link (FR-070, ADR-008).

    The league is found by its token first (404 `share_link_not_found`); a
    tournament in setup is 404 `tournament_not_found`, like an unknown one.
    """
    league = _shared_league(session, share_token=share_token)
    return view_knockout_rounds(
        session, league=league, tournament_id=tournament_id, past_setup=True
    )


def _require_remix(tournament: Tournament) -> RemixKnockout:
    """The tournament's Lord have mercy knockout, else 404 or 422.

    No knockout is 404 `knockout_not_found`; a fixed-pair one is 422
    `format_not_supported` (detail `format`, `mode`).
    """
    remix = remix_knockout(tournament)
    if remix is not None:
        return remix
    phase = knockout_phase(tournament)
    if phase is None:
        raise NotFoundError(ErrorCode.KNOCKOUT_NOT_FOUND)
    raise RuleViolationError(
        ErrorCode.FORMAT_NOT_SUPPORTED,
        format=phase.format,
        mode=phase.monster_knockout_mode,
    )


def _loaded(tournament: Tournament) -> RemixKnockout:
    remix = remix_knockout(tournament)
    if remix is None:  # the caller checked for a Lord have mercy knockout
        msg = "the tournament has no Lord have mercy knockout"
        raise ValueError(msg)
    return remix


def _pair(pair: Team | None) -> Team:
    """The players of a side; a later round never has a bye (BR-141)."""
    if pair is None:
        msg = "a drawn match of a later round has a side without players"
        raise ValueError(msg)
    return pair


def _stored_round(round_no: int, drawn: tuple[RemixMatch, ...], now: datetime) -> Round:
    """A drawn round as rows: a match per pair of pairs, no participation (D5).

    A replacement names the player they came in for on their row (BR-148).
    """
    replaced = {
        r.player_id: r.replaced_player_id for m in drawn for r in m.replacements
    }
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
                                side=number,
                                player_id=player,
                                replaced_player_id=replaced.get(player),
                                created_at=now,
                            )
                            for player in pair
                        ],
                    )
                    for number, pair in (
                        (1, _pair(match.side_1)),
                        (2, _pair(match.side_2)),
                    )
                ],
                games=[],
            )
            for match in drawn
        ],
        participation=[],
    )


def _remix_view(
    tournament: Tournament, remix: RemixKnockout, *, organizer: bool
) -> RemixKnockoutView:
    """The knockout round by round (BR-155); the organizer's adds FR-049's parts."""
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

    def side_view(row: MatchSide, match: RemixMatch) -> RemixSideView:
        players = tuple(sorted(p.player_id for p in row.players))
        return RemixSideView(
            player_ids=players,
            entry_id=row.entry_id,
            is_bye=row.is_bye,
            left_player_ids=tuple(p for p in players if p in left),
            replacements=tuple(r for r in match.replacements if r.player_id in players),
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
            sides=(side_view(side_1, match), side_view(side_2, match)),
            outcome=row.outcome,
            is_walkover=row.is_walkover,
            score=match_score(row),
            match_format=match_format_of(remix.phase, round_, row),
            field_number=field_number,
            winner_locked=not match.has_bye
            and not allows_result(state, match.key, None),
        )

    next_draw: RemixNextDrawView | None = None
    players: tuple[RemixPlayerView, ...] = ()
    if organizer:
        plan = next_draw_plan(tournament, remix)
        if plan is not None:
            next_draw = RemixNextDrawView(
                replacements=plan.replacements, staying_player_ids=plan.staying
            )
        players = _player_views(tournament, remix)
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
        next_draw=next_draw,
        players=players,
    )


def _player_views(
    tournament: Tournament, remix: RemixKnockout
) -> tuple[RemixPlayerView, ...]:
    """The knockout's players by group-phase standing (FR-044, BR-147, BR-153)."""
    state = remix.state
    entry_of = {
        PlayerId(member.player_id): entry
        for entry in _main_entries(tournament)
        for member in entry.members
    }
    order = {
        player_id: index
        for index, group in enumerate(standing_players(tournament))
        for player_id in group
    }

    def status(player_id: PlayerId) -> RemixPlayerStatus:
        if player_id in state.replaced:
            return "replaced"
        return "still_in" if player_id in state.still_in else "knocked_out"

    return tuple(
        RemixPlayerView(
            player_id=player_id,
            entry_id=entry_of[player_id].id,
            status=status(player_id),
            is_disabled=entry_of[player_id].is_disabled,
        )
        for player_id in sorted(
            state.players, key=lambda p: (order.get(p, len(order)), p)
        )
    )
