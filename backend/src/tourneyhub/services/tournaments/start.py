"""Starting a tournament, previewing its schedule, going back to setup."""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid7

from pydantic import JsonValue
from sqlalchemy import insert
from sqlalchemy.orm import Session

from tourneyhub.db.models.entries import Entry, EntryMember
from tourneyhub.db.models.matches import (
    Match,
    MatchSide,
    MatchSidePlayer,
    Round,
    RoundParticipation,
)
from tourneyhub.db.models.tournaments import Tournament, TournamentPhase
from tourneyhub.engine.errors import EngineError
from tourneyhub.engine.fields import MatchSlot
from tourneyhub.engine.ids import EntryId, MatchId, PlayerId
from tourneyhub.engine.knockout import MAX_KNOCKOUT_ENTRIES, Bracket, draw_bracket
from tourneyhub.engine.schedule import (
    MAX_ROUND_ROBIN_ENTRIES,
    ScheduledMatch,
    ScheduledRound,
    check_entry_count,
    round_robin,
    seed_order,
)
from tourneyhub.engine.swiss import SwissDraw, draw_first_swiss_round
from tourneyhub.engine.tournaments import (
    EntryStage,
    MatchKind,
    Participation,
    PhaseFormat,
    PhaseKind,
    TournamentState,
    TournamentType,
)
from tourneyhub.errors import (
    ConflictError,
    ErrorCode,
    NotFoundError,
    RuleViolationError,
)
from tourneyhub.services.engine_errors import to_app_error
from tourneyhub.services.leagues import get_league
from tourneyhub.services.tournaments.entries import _check_dyp_draw
from tourneyhub.services.tournaments.fields import _fill_fields
from tourneyhub.services.tournaments.places import _ranking
from tourneyhub.services.tournaments.shared import (
    Clock,
    _lock_tournament,
    _main_entries,
    _match_slots,
    _tournament_query,
)
from tourneyhub.services.tournaments.views import (
    TournamentView,
    _setup_of,
    read_tournament,
)


def _check_ready(tournament: Tournament, phase: TournamentPhase) -> None:
    """Refuse a start whose setup is not complete (FR-032, FR-033, BR-030 to BR-032).

    A round robin, a Swiss and a knockout without a group phase are generated
    so far; Monster DYP is 422 `format_not_supported`. Doubles needs every
    picked player in a pair (422 `players_without_partner`); DYP needs its
    halves and pairs (the 422s of a new DYP draw); every type needs FR-032's
    minimum of entries, 4 for a knockout with a third-place match (422
    `not_enough_entries`). A round robin takes at most
    `MAX_ROUND_ROBIN_ENTRIES` (422 `too_many_entries_for_round_robin`), a
    knockout `MAX_KNOCKOUT_ENTRIES` (422 `too_many_entries_for_knockout`); a
    Swiss has no maximum (FR-032).
    """
    if phase.format not in {
        PhaseFormat.ROUND_ROBIN,
        PhaseFormat.SWISS,
        PhaseFormat.SINGLE_ELIMINATION,
    }:
        raise RuleViolationError(ErrorCode.FORMAT_NOT_SUPPORTED, format=phase.format)
    if tournament.type is TournamentType.DOUBLES:
        paired = {m.player_id for entry in tournament.entries for m in entry.members}
        unpaired = sum(row.player_id not in paired for row in tournament.players)
        if unpaired:
            raise RuleViolationError(
                ErrorCode.PLAYERS_WITHOUT_PARTNER, unpaired=unpaired
            )
    elif tournament.type is TournamentType.DYP:
        _check_dyp_draw(tournament)
    given = sum(e.stage is EntryStage.MAIN for e in tournament.entries)
    try:
        check_entry_count(
            tournament_type=tournament.type,
            third_place_match=bool(phase.third_place_match),
            given=given,
        )
    except EngineError as err:
        raise to_app_error(err) from err
    if phase.kind is PhaseKind.KNOCKOUT:
        if given > MAX_KNOCKOUT_ENTRIES:
            raise RuleViolationError(
                ErrorCode.TOO_MANY_ENTRIES_FOR_KNOCKOUT, limit=MAX_KNOCKOUT_ENTRIES
            )
    elif phase.format is PhaseFormat.ROUND_ROBIN and given > MAX_ROUND_ROBIN_ENTRIES:
        raise RuleViolationError(
            ErrorCode.TOO_MANY_ENTRIES_FOR_ROUND_ROBIN, limit=MAX_ROUND_ROBIN_ENTRIES
        )


def _round_robin_of(
    main: Sequence[Entry], phase: TournamentPhase
) -> tuple[ScheduledRound, ...]:
    """The round robin of the main entries by seed (BR-050 to BR-052).

    Start writes it and the preview shows it, so both come from this one call.
    """
    return round_robin(
        seed_order((EntryId(entry.id), entry.seed) for entry in main),
        legs=phase.round_robin_legs or 1,  # the CHECK sets it for a round robin
    )


def _swiss_round_of(draw: SwissDraw) -> ScheduledRound:
    """A drawn Swiss round as the rows of a schedule take it (BR-055 to BR-058)."""
    return ScheduledRound(
        round_no=draw.round_no,
        matches=tuple(
            ScheduledMatch(side_1=pair.side_1, side_2=pair.side_2)
            for pair in draw.pairs
        ),
        sitting_out=draw.sitting_out,
    )


def _group_schedule(
    main: Sequence[Entry], phase: TournamentPhase
) -> tuple[ScheduledRound, ...]:
    """What the start writes for a group phase, and the preview shows.

    A round robin's every round (BR-050 to BR-052); a Swiss's round 1 from
    the seeds, the lowest seed sitting out with an odd number (BR-055,
    BR-058). Fewer than 2 entries is 422 `not_enough_entries`.
    """
    if phase.format is not PhaseFormat.SWISS:
        return _round_robin_of(main, phase)
    try:
        draw = draw_first_swiss_round(
            seed_order((EntryId(entry.id), entry.seed) for entry in main)
        )
    except EngineError as err:
        raise to_app_error(err) from err
    return (_swiss_round_of(draw),)


def _bracket_from_seeds(main: Sequence[Entry], phase: TournamentPhase) -> Bracket:
    """The bracket of a knockout without a group phase, by setup seed (BR-040 to BR-044).

    The setup seeds are the knockout's seeds (FR-034): the byes go to the top
    seeds and seeds 1 and 2 can meet only in the final. Start writes it and
    the preview shows it, so both come from this one call.
    """
    return draw_bracket(
        seed_order((EntryId(entry.id), entry.seed) for entry in main),
        third_place_match=bool(phase.third_place_match),
    )


def _bracket_rounds(
    bracket: Bracket, members: Mapping[UUID, Sequence[EntryMember]], now: datetime
) -> list[Round]:
    """Every round of the bracket; only the first round stores its sides (D4)."""
    rounds = [
        Round(
            id=uuid7(), round_no=round_no, created_at=now, matches=[], participation=[]
        )
        for round_no in range(1, bracket.round_count + 1)
    ]
    first = {match.position: match for match in bracket.first_round}
    for key in bracket.keys:
        sides: list[MatchSide] = []
        if key.round_no == 1:
            stored = first[key.position]
            sides = [
                MatchSide(
                    side=number,
                    entry_id=entry_id,
                    is_bye=entry_id is None,
                    created_at=now,
                    players=[
                        MatchSidePlayer(
                            side=number, player_id=member.player_id, created_at=now
                        )
                        for member in ([] if entry_id is None else members[entry_id])
                    ],
                )
                for number, entry_id in ((1, stored.side_1), (2, stored.side_2))
            ]
        rounds[key.round_no - 1].matches.append(
            Match(
                id=uuid7(),
                position=key.position,
                kind=key.kind,
                outcome=None,
                is_walkover=False,
                result_entered_at=None,
                requeued_at=None,
                created_at=now,
                sides=sides,
                games=[],
            )
        )
    return rounds


@dataclass(frozen=True, slots=True, kw_only=True)
class _ScheduleRows:
    """The rows of a round robin, one list per table, in insert order (D2, D5)."""

    rounds: list[dict[str, object]]
    matches: list[dict[str, object]]
    sides: list[dict[str, object]]
    side_players: list[dict[str, object]]
    participation: list[dict[str, object]]
    slots: list[MatchSlot]


def _schedule_rows(
    phase: TournamentPhase,
    schedule: Sequence[ScheduledRound],
    members: Mapping[UUID, Sequence[UUID]],
    now: datetime,
    *,
    disabled: Collection[UUID] = frozenset(),
) -> _ScheduleRows:
    """The rounds of the schedule with their matches, sides and participation.

    Every main entry in `members` gets a participation row in every round
    (D5): `sat_out` for the one sitting out, `disabled` for a disabled entry,
    which is not drawn (BR-064), and `played` for the others. Every stored
    side lists its players (D2). The slots are the matches as the field queue
    sees them, so no row needs loading to fill the fields.
    """
    rows = _ScheduleRows(
        rounds=[], matches=[], sides=[], side_players=[], participation=[], slots=[]
    )
    for scheduled_round in schedule:
        round_id = uuid7()
        rows.rounds.append(
            {
                "id": round_id,
                "phase_id": phase.id,
                "round_no": scheduled_round.round_no,
                "created_at": now,
            }
        )
        for position, scheduled in enumerate(scheduled_round.matches, start=1):
            match_id = uuid7()
            rows.matches.append(
                {
                    "id": match_id,
                    "round_id": round_id,
                    "position": position,
                    "kind": MatchKind.STANDARD,
                    "outcome": None,
                    "is_walkover": False,
                    "result_entered_at": None,
                    "requeued_at": None,
                    "created_at": now,
                }
            )
            players: set[PlayerId] = set()
            for side, entry_id in ((1, scheduled.side_1), (2, scheduled.side_2)):
                rows.sides.append(
                    {
                        "match_id": match_id,
                        "side": side,
                        "entry_id": entry_id,
                        "is_bye": False,
                        "created_at": now,
                    }
                )
                for player_id in members[entry_id]:
                    rows.side_players.append(
                        {
                            "match_id": match_id,
                            "side": side,
                            "player_id": player_id,
                            "created_at": now,
                        }
                    )
                    players.add(PlayerId(player_id))
            rows.slots.append(
                MatchSlot(
                    match_id=MatchId(match_id),
                    phase_position=phase.position,
                    round_no=scheduled_round.round_no,
                    kind=MatchKind.STANDARD,
                    position=position,
                    player_ids=frozenset(players),
                    has_bye=False,
                    has_result=False,
                    requeued_at=None,
                )
            )
        rows.participation.extend(
            {
                "round_id": round_id,
                "entry_id": entry_id,
                "status": Participation.SAT_OUT
                if entry_id == scheduled_round.sitting_out
                else Participation.DISABLED
                if entry_id in disabled
                else Participation.PLAYED,
                "created_at": now,
            }
            for entry_id in sorted(members)
        )
    return rows


def _insert_schedule(session: Session, rows: _ScheduleRows) -> None:
    """Write the schedule's rows in bulk, parents first.

    A 64-entry double round robin has 4,032 matches and some 20,000 to 30,000
    other rows; one ORM object per row would be far too slow.
    """
    for model, table_rows in (
        (Round, rows.rounds),
        (Match, rows.matches),
        (MatchSide, rows.sides),
        (MatchSidePlayer, rows.side_players),
        (RoundParticipation, rows.participation),
    ):
        session.execute(insert(model), table_rows)


def start_tournament(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    expected_draw_counter: int,
    expected_seed_order: Sequence[UUID],
    clock: Clock,
) -> TournamentView:
    """Generate the schedule and start the tournament (FR-035).

    The request carries the draw counter and the seed order the review screen
    showed: a started tournament is 409 `tournament_not_in_setup`, a stale
    counter 409 `draw_counter_changed`, so a repeat never starts twice
    (ADR-008). A hand reordering of the seeds leaves the counter (ADR-010), so
    a seed order that is not the entries' current one, seed 1 first, is 409
    `seed_order_changed`: the schedule is never drawn from a setup the
    organizer did not see. The seeds follow the entries, so the same check
    covers a change to the players or to their pairs. A round robin, a Swiss
    and a knockout without a group phase are generated so far; Monster DYP is
    422 `format_not_supported`. An incomplete setup is a 422 (`_check_ready`).

    The round robin follows the seeds (BR-050 to BR-052); a Swiss gets round 1
    only, top half of the seeds against the bottom half, the lowest seed
    sitting out with an odd number (BR-055, BR-058), and its later rounds are
    added one at a time (`add_round`, FR-040). Every main entry gets a
    participation row in every round (D5). A knockout without a group phase
    (FR-031) is drawn from the setup seeds into the setup's phase: every
    bracket match at once, the byes for the top seeds in round 1 and the
    third-place match in the final's round (BR-040 to BR-044); only the first
    round stores its sides (D4). The first matches take the free fields in
    schedule order (BR-130). The draws stay as they are (ADR-010).
    """
    _, tournament = _lock_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user_id,
        rounds=True,
    )
    if tournament.state is not TournamentState.SETUP:
        raise ConflictError(ErrorCode.TOURNAMENT_NOT_IN_SETUP, state=tournament.state)
    if tournament.draw_counter != expected_draw_counter:
        raise ConflictError(
            ErrorCode.DRAW_COUNTER_CHANGED, draw_counter=tournament.draw_counter
        )
    phase = tournament.phases[0]  # setup holds exactly one phase (D9)
    _check_ready(tournament, phase)
    main = _main_entries(tournament)
    if list(expected_seed_order) != _seed_order_of(main):
        raise ConflictError(ErrorCode.SEED_ORDER_CHANGED)
    if phase.kind is PhaseKind.KNOCKOUT:
        now = clock()
        bracket = _bracket_from_seeds(main, phase)
        phase.rounds.extend(
            _bracket_rounds(bracket, {entry.id: entry.members for entry in main}, now)
        )
        tournament.state = TournamentState.IN_PROGRESS
        tournament.updated_at = now
        session.flush()  # the matches exist before a field references one
        _fill_fields(tournament, _match_slots(tournament), now)
        session.flush()
        return read_tournament(
            session, league_id=league_id, tournament_id=tournament.id, user_id=user_id
        )
    members = {
        entry.id: sorted(member.player_id for member in entry.members) for entry in main
    }
    schedule = _group_schedule(main, phase)
    now = clock()
    rows = _schedule_rows(phase, schedule, members, now)
    _insert_schedule(session, rows)  # the matches exist before a field references one
    tournament.state = TournamentState.IN_PROGRESS
    tournament.updated_at = now
    _fill_fields(tournament, rows.slots, now)
    session.flush()
    return read_tournament(
        session, league_id=league_id, tournament_id=tournament.id, user_id=user_id
    )


def _seed_order_of(main: Sequence[Entry]) -> list[UUID]:
    """The main entries' ids, seed 1 first: what the preview and the start agree on."""
    return list[UUID](seed_order((EntryId(entry.id), entry.seed) for entry in main))


@dataclass(frozen=True, slots=True, kw_only=True)
class StartProblem:
    """Why "Generate and start" would be refused: the code and detail of its 422."""

    code: ErrorCode
    detail: dict[str, JsonValue]


@dataclass(frozen=True, slots=True, kw_only=True)
class PreviewMatch:
    """A match of the preview: the players of each side, a pair in entry order."""

    sides: tuple[tuple[UUID, ...], tuple[UUID, ...]]


@dataclass(frozen=True, slots=True, kw_only=True)
class PreviewRound:
    """A round of the preview; `sitting_out` lists the players of each entry out.

    `byes` lists the players of each entry that goes straight to the second
    round of a knockout, seed 1 first (BR-041); a bye is not a match.
    """

    round_no: int
    matches: tuple[PreviewMatch, ...]
    sitting_out: tuple[tuple[UUID, ...], ...]
    byes: tuple[tuple[UUID, ...], ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class SchedulePreview:
    """What "Generate and start" would create, or why it would not (FR-035).

    With a `problem` there are no rounds, no counts and no `seed_order`.
    `draw_counter` and `seed_order`, the main entries with seed 1 first, are
    the ones the start must carry (ADR-008). A round robin lists all its rounds;
    a Swiss its round 1, without counts, since its rounds come one at a time. A
    knockout without a group phase lists its first round, with the byes, and
    counts every match of the bracket (the third-place match too, no byes)
    and its rounds; `bracket_size` is its number of first-round spots.
    """

    draw_counter: int
    seed_order: tuple[UUID, ...]
    problem: StartProblem | None
    rounds: tuple[PreviewRound, ...]
    match_count: int | None
    round_count: int | None
    bracket_size: int | None

    @property
    def can_start(self) -> bool:
        return self.problem is None


def _start_problem(tournament: Tournament) -> StartProblem | None:
    """The refusal `start_tournament` would answer after its draw counter check."""
    if tournament.state is not TournamentState.SETUP:
        return StartProblem(
            code=ErrorCode.TOURNAMENT_NOT_IN_SETUP, detail={"state": tournament.state}
        )
    try:
        _check_ready(tournament, tournament.phases[0])
    except RuleViolationError as err:
        return StartProblem(code=err.code, detail=err.detail)
    return None


def preview_schedule(
    session: Session, *, league_id: UUID, tournament_id: UUID, user_id: UUID
) -> SchedulePreview:
    """Return what `start_tournament` would create, writing nothing (FR-035).

    Read without a lock, like the setup. The checks and the schedule are the
    start's own (`_check_ready`, `_group_schedule`), so a preview that can start
    is the schedule the start writes for the same draw counter. A refusal comes
    back as the `problem`, not as an error: the review screen shows it. A
    Swiss shows round 1 only and no counts: its later rounds are drawn one at a
    time from the standings (FR-040).
    """
    league = get_league(session, league_id=league_id, user_id=user_id)
    tournament = session.scalars(_tournament_query(league, tournament_id)).one_or_none()
    if tournament is None:
        raise NotFoundError(ErrorCode.TOURNAMENT_NOT_FOUND)
    problem = _start_problem(tournament)
    if problem is not None:
        return SchedulePreview(
            draw_counter=tournament.draw_counter,
            seed_order=(),
            problem=problem,
            rounds=(),
            match_count=None,
            round_count=None,
            bracket_size=None,
        )
    setup = _setup_of(
        tournament, _ranking(session, league=league, tournament=tournament)
    )
    players = {entry.id: entry.player_ids for entry in setup.entries}
    phase = tournament.phases[0]
    if phase.kind is PhaseKind.KNOCKOUT:
        return _bracket_preview(
            tournament.draw_counter, _main_entries(tournament), phase, players
        )
    schedule = _group_schedule(_main_entries(tournament), phase)
    rounds = tuple(
        PreviewRound(
            round_no=scheduled.round_no,
            matches=tuple(
                PreviewMatch(sides=(players[m.side_1], players[m.side_2]))
                for m in scheduled.matches
            ),
            sitting_out=()
            if scheduled.sitting_out is None
            else (players[scheduled.sitting_out],),
        )
        for scheduled in schedule
    )
    swiss = phase.format is PhaseFormat.SWISS  # its rounds come one at a time
    return SchedulePreview(
        draw_counter=tournament.draw_counter,
        seed_order=tuple(_seed_order_of(_main_entries(tournament))),
        problem=None,
        rounds=rounds,
        match_count=None if swiss else sum(len(r.matches) for r in rounds),
        round_count=None if swiss else len(rounds),
        bracket_size=None,
    )


def _bracket_preview(
    draw_counter: int,
    main: Sequence[Entry],
    phase: TournamentPhase,
    players: Mapping[UUID, tuple[UUID, ...]],
) -> SchedulePreview:
    """The preview of a knockout without a group phase (BR-040 to BR-044).

    The first round's matches in bracket order, the better seed on side 1, and
    the byes, which are the top seeds, one each (BR-041). The bracket has one
    match fewer than it has entries, and one more with a third-place match.
    """
    bracket = _bracket_from_seeds(main, phase)
    seeds = seed_order((EntryId(entry.id), entry.seed) for entry in main)
    first = bracket.first_round
    return SchedulePreview(
        draw_counter=draw_counter,
        seed_order=tuple(seeds),
        problem=None,
        rounds=(
            PreviewRound(
                round_no=1,
                matches=tuple(
                    PreviewMatch(sides=(players[m.side_1], players[m.side_2]))
                    for m in first
                    if m.side_1 is not None and m.side_2 is not None
                ),
                sitting_out=(),
                byes=tuple(
                    players[entry_id] for entry_id in seeds[: bracket.size - len(seeds)]
                ),
            ),
        ),
        match_count=len(seeds) - 1 + int(bracket.third_place_match),
        round_count=bracket.round_count,
        bracket_size=bracket.size,
    )


def back_to_setup(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    clock: Clock,
) -> TournamentView:
    """Take a started tournament back to setup (FR-036).

    The request expects the tournament in progress; in any other state it is
    409 `tournament_not_in_progress`, so a repeat changes nothing (ADR-008).
    Once a match has a result it is 422 `tournament_has_results`. The rounds,
    with their matches and participation, are deleted and the fields freed: a
    knockout without a group phase keeps its phase, the format of setup, and
    loses its bracket (D4);
    the entries, seeds and draws stay, and every disabled flag is cleared
    (ADR-010, DATA-MODEL §4.4).
    """
    _, tournament = _lock_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user_id,
        rounds=True,
    )
    if tournament.state is not TournamentState.IN_PROGRESS:
        raise ConflictError(
            ErrorCode.TOURNAMENT_NOT_IN_PROGRESS, state=tournament.state
        )
    results = sum(
        match.outcome is not None
        for phase in tournament.phases
        for round_ in phase.rounds
        for match in round_.matches
    )
    if results:
        raise RuleViolationError(ErrorCode.TOURNAMENT_HAS_RESULTS, results=results)
    _reset_to_setup(session, tournament, clock())
    return read_tournament(
        session, league_id=league_id, tournament_id=tournament.id, user_id=user_id
    )


def _reset_to_setup(session: Session, tournament: Tournament, now: datetime) -> None:
    """Delete every round and put the tournament back in setup (FR-036, FR-046).

    The fields are freed and the rounds go with their matches, results and
    participation; the phases, entries, seeds and draws stay, and every
    disabled flag is cleared (DATA-MODEL §4.4, §4.5). Going back to setup and
    deleting a Swiss's round 1 share it.
    """
    for field in tournament.fields:
        if field.match_id is not None:
            field.match_id = None
            field.updated_at = now
    session.flush()  # the fields let go of the matches before they are deleted
    for phase in tournament.phases:
        phase.rounds.clear()
    for entry in tournament.entries:
        entry.is_disabled = False
    tournament.state = TournamentState.SETUP
    tournament.updated_at = now
    session.flush()
