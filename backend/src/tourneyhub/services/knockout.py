"""The knockout after a group phase: preview, start, final format, delete, bracket.

FR-045, FR-046, FR-054, BR-040 to BR-044, BR-080, BR-085 to BR-087, BR-094, BR-120.
Every write locks the league row, then the tournament row (ADR-008). Starting
creates the knockout's entries, which continue the qualifying group-phase
entries (`source_entry_id`, BR-085), and every bracket match at once, with
the first round's sides stored; later sides are derived on read (D4). Results
go through `tournaments.set_match_result`, which knows the knockout's lock and
finishes the tournament with its last result (BR-094, FR-037).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid7

from pydantic import JsonValue
from sqlalchemy.orm import Session

from tourneyhub.db.models.entries import Entry, EntryMember
from tourneyhub.db.models.leagues import League
from tourneyhub.db.models.matches import Match
from tourneyhub.db.models.tournaments import Tournament, TournamentPhase
from tourneyhub.engine.errors import EngineError
from tourneyhub.engine.ids import EntryId
from tourneyhub.engine.knockout import (
    BracketMatch,
    Cut,
    FirstRoundMatch,
    RoundName,
    cut_standing,
    draw_bracket,
    feeds,
    locked_by,
    minimum_qualifiers,
    round_name,
)
from tourneyhub.engine.tournaments import (
    EntryStage,
    KnockoutMatchFormat,
    MatchFormat,
    MatchKind,
    MonsterKnockoutMode,
    Outcome,
    PhaseFormat,
    PhaseKind,
    TournamentState,
)
from tourneyhub.errors import (
    ConflictError,
    ErrorCode,
    NotFoundError,
    RuleViolationError,
)
from tourneyhub.services.engine_errors import to_app_error
from tourneyhub.services.leagues import get_league
from tourneyhub.services.public import _shared_league
from tourneyhub.services.tournaments import (
    PLAYED_GROUP_FORMATS,
    Clock,
    GroupStandingRow,
    KnockoutBracket,
    TournamentView,
    group_standings,
    knockout_bracket,
    read_tournament,
    tie_groups,
)
from tourneyhub.services.tournaments.fields import _fill_fields
from tourneyhub.services.tournaments.results import _match_format
from tourneyhub.services.tournaments.shared import (
    _current_phase,
    _group_phase,
    _load_tournament,
    _lock_tournament,
    _match_slots,
    _played,
    _require_open_season,
)
from tourneyhub.services.tournaments.start import _bracket_rounds

# ---------------------------------------------------------------- the cut


@dataclass(frozen=True, slots=True, kw_only=True)
class KnockoutProblem:
    """Why starting the knockout would be refused: the code and detail of its error."""

    code: ErrorCode
    detail: dict[str, JsonValue]


@dataclass(frozen=True, slots=True, kw_only=True)
class PreviewMember:
    """A group-phase entry behind a knockout entry, with its group-phase place."""

    entry_id: UUID
    place: int


@dataclass(frozen=True, slots=True, kw_only=True)
class PreviewEntry:
    """A knockout entry the start would create, by seed (BR-085).

    `decided_by_lot` says the lot placed it among the entries level with it,
    or took it through the cut (BR-074, ADR-009).
    """

    seed: int
    members: tuple[PreviewMember, ...]
    decided_by_lot: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class KnockoutPreview:
    """What starting the knockout would draw, writing nothing (FR-045).

    `qualifiers` is the number asked for, kept between the fewest a knockout
    needs and `max_qualifiers`, the entries that can go through. With a
    `problem` the start would be refused, and there are no entries when no
    knockout is possible. `first_round` pairs seeds, None for a bye (BR-041).
    """

    problem: KnockoutProblem | None
    max_qualifiers: int
    qualifiers: int
    entries: tuple[PreviewEntry, ...]
    first_round: tuple[tuple[int, int | None], ...]
    bracket_size: int | None
    locks_round_no: int | None
    skipped_entry_ids: tuple[UUID, ...]
    is_cut_by_lot: bool


def _played_group(tournament: Tournament) -> TournamentPhase:
    """The round robin or Swiss a knockout follows; Monster DYP comes later.

    Without a group phase, or after a Monster DYP, it is 422
    `format_not_supported` (detail `format`).
    """
    group = _group_phase(tournament)
    if group is None or group.format not in PLAYED_GROUP_FORMATS:
        format_ = tournament.phases[0].format if group is None else group.format
        raise RuleViolationError(ErrorCode.FORMAT_NOT_SUPPORTED, format=format_)
    return group


def _require_no_mode(group: TournamentPhase, mode: MonsterKnockoutMode | None) -> None:
    """Refuse a Monster DYP mode for another group phase (FR-045): 422."""
    if mode is not None:
        raise RuleViolationError(
            ErrorCode.KNOCKOUT_MODE_NOT_APPLICABLE, format=group.format
        )


def _require_group_done(group: TournamentPhase) -> None:
    """Refuse a knockout before every group-phase match has a result (FR-040)."""
    left = sum(
        match.outcome is None for round_ in group.rounds for match in _played(round_)
    )
    if left:
        raise RuleViolationError(ErrorCode.GROUP_PHASE_NOT_DONE, matches_left=left)


def _cut(
    tournament: Tournament,
    standings: Sequence[GroupStandingRow],
    *,
    qualifiers: int,
    third_place_match: bool,
) -> Cut:
    """The engine's cut of the standings (BR-074, BR-080, BR-085); 422 out of range."""
    try:
        return cut_standing(
            tie_groups(standings),
            qualifiers=qualifiers,
            third_place_match=third_place_match,
            rng_seed=tournament.rng_seed,
            disabled=[
                EntryId(entry.id)
                for entry in tournament.entries
                if entry.stage is EntryStage.MAIN and entry.is_disabled
            ],
        )
    except EngineError as err:
        raise to_app_error(err) from err


def preview_knockout(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    qualifiers: int,
    third_place_match: bool,
    mode: MonsterKnockoutMode | None = None,
) -> KnockoutPreview:
    """Return the cut, the seeds and the byes the start would draw (FR-045, BR-080).

    Read without a lock. The cut and the bracket are the start's own, so a
    preview that can start is what the start writes while the results stay.
    The number asked for is kept within what a knockout can take, so the
    screen can always show one; a refusal of the start comes back as the
    `problem`, not as an error.
    """
    league = get_league(session, league_id=league_id, user_id=user_id)
    tournament = _load_tournament(session, league=league, tournament_id=tournament_id)
    problem = _start_problem(league, tournament, mode=mode)
    group = _group_phase(tournament)
    if group is None or group.format not in PLAYED_GROUP_FORMATS:
        return KnockoutPreview(
            problem=problem,
            max_qualifiers=0,
            qualifiers=qualifiers,
            entries=(),
            first_round=(),
            bracket_size=None,
            locks_round_no=None,
            skipped_entry_ids=(),
            is_cut_by_lot=False,
        )
    standings = group_standings(tournament, group)
    eligible = sum(
        not entry.is_disabled
        for entry in tournament.entries
        if entry.stage is EntryStage.MAIN
    )
    minimum = minimum_qualifiers(third_place_match=third_place_match)
    shown = max(minimum, min(qualifiers, eligible))
    locks = group.rounds[-1].round_no if group.rounds else None
    if eligible < minimum:
        return KnockoutPreview(
            problem=problem,
            max_qualifiers=eligible,
            qualifiers=shown,
            entries=(),
            first_round=(),
            bracket_size=None,
            locks_round_no=locks,
            skipped_entry_ids=(),
            is_cut_by_lot=False,
        )
    cut = _cut(
        tournament, standings, qualifiers=shown, third_place_match=third_place_match
    )
    place = {row.entry_id: row.place for row in standings}
    bracket = draw_bracket(cut.seeds, third_place_match=third_place_match)
    seed_of = {entry_id: seed for seed, entry_id in enumerate(cut.seeds, start=1)}
    return KnockoutPreview(
        problem=problem,
        max_qualifiers=eligible,
        qualifiers=shown,
        entries=tuple(
            PreviewEntry(
                seed=seed,
                members=(PreviewMember(entry_id=entry_id, place=place[entry_id]),),
                decided_by_lot=entry_id in cut.decided_by_lot,
            )
            for seed, entry_id in enumerate(cut.seeds, start=1)
        ),
        first_round=tuple(_seed_pair(match, seed_of) for match in bracket.first_round),
        bracket_size=bracket.size,
        locks_round_no=locks,
        skipped_entry_ids=cut.skipped,
        is_cut_by_lot=cut.is_cut_by_lot,
    )


def _seed_pair(
    match: FirstRoundMatch, seed_of: dict[EntryId, int]
) -> tuple[int, int | None]:
    """A first-round match as seeds, the better one first; None for a bye."""
    seeds = sorted(
        seed_of[entry_id]
        for entry_id in (match.side_1, match.side_2)
        if entry_id is not None
    )
    return seeds[0], seeds[1] if len(seeds) > 1 else None


def _start_problem(
    league: League, tournament: Tournament, *, mode: MonsterKnockoutMode | None
) -> KnockoutProblem | None:
    """The refusal `start_knockout` would answer, its expectations aside."""
    try:
        _require_open_season(league, tournament)
    except ConflictError as err:
        return KnockoutProblem(code=err.code, detail=err.detail)
    if tournament.state is not TournamentState.IN_PROGRESS:
        return KnockoutProblem(
            code=ErrorCode.TOURNAMENT_NOT_IN_PROGRESS,
            detail={"state": tournament.state},
        )
    if knockout_bracket(tournament) is not None:
        current = _current_phase(tournament)
        return KnockoutProblem(
            code=ErrorCode.CURRENT_PHASE_CHANGED,
            detail={"current_phase_id": None if current is None else str(current.id)},
        )
    try:
        group = _played_group(tournament)
        _require_no_mode(group, mode)
        _require_group_done(group)
    except RuleViolationError as err:
        return KnockoutProblem(code=err.code, detail=err.detail)
    return None


# ---------------------------------------------------------------- start


@dataclass(frozen=True, slots=True, kw_only=True)
class KnockoutStart:
    """The organizer's choices for the knockout (FR-045, BR-080, BR-120).

    `match_format` None takes the league's default; `final_match_format`
    None lets the final play `match_format` (BR-120). `expected_qualifier_ids`
    are the group-phase entries the preview showed going through, in seed
    order (the cut and the seeding, which fix the bracket). `mode` is for a
    knockout after Monster DYP rounds (BR-081 to BR-084), which comes later.
    """

    expected_current_phase_id: UUID
    expected_qualifier_ids: tuple[UUID, ...]
    qualifiers: int
    third_place_match: bool
    match_format: KnockoutMatchFormat | None
    final_match_format: KnockoutMatchFormat | None
    mode: MonsterKnockoutMode | None = None


def start_knockout(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    start: KnockoutStart,
    clock: Clock,
) -> TournamentView:
    """Draw the knockout after a round robin or a Swiss and start it (FR-045).

    The request carries the phase the screen saw as the current one, the
    group phase: once the knockout exists it is 409 `current_phase_changed`
    (detail `current_phase_id`), so a repeat draws nothing (ADR-008). A
    tournament not in progress is 409 `tournament_not_in_progress`, a closed
    season 409 `season_closed`. A Monster DYP or a tournament without a
    group phase is 422 `format_not_supported`, a group-phase match
    without a result 422 `group_phase_not_done`, and a number of qualifiers
    out of range 422 `qualifiers_out_of_range` (detail `minimum`, `maximum`,
    `given`; BR-080). The request also carries the qualifying entries in seed
    order that the preview showed; a group result that changed the cut or the
    seeds since is 409 `qualifiers_changed` (detail `entry_ids`, the current
    ones), so the organizer sees the new draw before it is written (ADR-008).

    The best entries of the standings go through as they are and are seeded
    by their place; entries still level are ordered by the lot
    `knockout-seeding` (BR-074, BR-085). Each becomes a knockout entry that
    continues it (`source_entry_id`). Every bracket match is created, the
    byes for the top seeds in round 1 (BR-040 to BR-042), with the third-place
    match in the final's round (BR-044). The phase gets its match format,
    the league's default unless the request names one, and the final its own
    or none (BR-120). The first matches take the free fields (BR-130), and
    the group phase's results are locked from now on (BR-053, BR-065).
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
    current = _current_phase(tournament)
    if current is None or current.id != start.expected_current_phase_id:
        raise ConflictError(
            ErrorCode.CURRENT_PHASE_CHANGED,
            current_phase_id=None if current is None else str(current.id),
        )
    group = _played_group(tournament)
    _require_no_mode(group, start.mode)
    _require_group_done(group)
    cut = _cut(
        tournament,
        group_standings(tournament, group),
        qualifiers=start.qualifiers,
        third_place_match=start.third_place_match,
    )
    if tuple(cut.seeds) != start.expected_qualifier_ids:
        raise ConflictError(
            ErrorCode.QUALIFIERS_CHANGED, entry_ids=[str(i) for i in cut.seeds]
        )
    now = clock()
    phase = TournamentPhase(
        id=uuid7(),
        position=2,
        kind=PhaseKind.KNOCKOUT,
        format=PhaseFormat.SINGLE_ELIMINATION,
        round_robin_legs=None,
        sit_out_points=None,
        tiebreakers=None,
        qualifiers=start.qualifiers,
        third_place_match=start.third_place_match,
        monster_knockout_mode=None,
        match_format=MatchFormat(
            start.match_format or league.default_match_format.value
        ),
        final_match_format=start.final_match_format,
        created_at=now,
        rounds=[],
    )
    tournament.phases.append(phase)
    seeds = _knockout_entries(tournament, cut.seeds, now)
    session.flush()  # the entries and the phase exist before the matches name them
    members = {entry.id: entry.members for entry in seeds}
    bracket = draw_bracket(
        [EntryId(entry.id) for entry in seeds],
        third_place_match=start.third_place_match,
    )
    phase.rounds.extend(_bracket_rounds(bracket, members, now))
    tournament.updated_at = now
    session.flush()  # the matches exist before a field references one
    _fill_fields(tournament, _match_slots(tournament), now)
    session.flush()
    return read_tournament(
        session, league_id=league_id, tournament_id=tournament.id, user_id=user_id
    )


def _knockout_entries(
    tournament: Tournament, seeds: Sequence[EntryId], now: datetime
) -> list[Entry]:
    """One knockout entry per qualifier, continuing it, seed 1 first (BR-085, D4)."""
    by_id = {entry.id: entry for entry in tournament.entries}
    created: list[Entry] = []
    for seed, source_id in enumerate(seeds, start=1):
        source = by_id[source_id]
        entry_id = uuid7()
        entry = Entry(
            id=entry_id,
            stage=EntryStage.KNOCKOUT,
            kind=source.kind,
            seed=seed,
            source_entry_id=source.id,
            is_top_player=False,
            is_disabled=False,
            created_at=now,
            members=[
                EntryMember(
                    entry_id=entry_id,
                    player_id=member.player_id,
                    tournament_id=tournament.id,
                    stage=EntryStage.KNOCKOUT,
                    created_at=now,
                )
                for member in source.members
            ],
        )
        tournament.entries.append(entry)
        created.append(entry)
    return created


# ---------------------------------------------------------------- the final's format


def set_final_format(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    final_match_format: KnockoutMatchFormat | None,
    clock: Clock,
) -> TournamentView:
    """Give the final a format of its own, or None to play the knockout's (FR-054).

    The final is the standard match of the bracket's last round (D4, BR-120);
    the third-place match keeps the knockout's format. The change is allowed
    while the final has no result (BR-096): one with a result, which every
    finished tournament's final has, is 409 `match_has_result` (detail
    `match_id`), as a field placement is: the screen hides the control then, so
    only a stale one sends it. A closed season is 409 `season_closed`, a
    tournament in setup 409 `tournament_not_in_progress` (detail `state`), and
    a tournament without a knockout 404 `knockout_not_found`. A repeat stores
    the same format again (ADR-008).
    """
    league, tournament = _lock_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user_id,
        rounds=True,
    )
    _require_open_season(league, tournament)
    if tournament.state is TournamentState.SETUP:
        raise ConflictError(
            ErrorCode.TOURNAMENT_NOT_IN_PROGRESS, state=tournament.state
        )
    knockout = knockout_bracket(tournament)
    if knockout is None:
        raise NotFoundError(ErrorCode.KNOCKOUT_NOT_FOUND)
    last = max(knockout.phase.rounds, key=lambda round_: round_.round_no)
    final = next(m for m in last.matches if m.kind is MatchKind.STANDARD)
    if final.outcome is not None:
        raise ConflictError(ErrorCode.MATCH_HAS_RESULT, match_id=str(final.id))
    now = clock()
    knockout.phase.final_match_format = final_match_format
    knockout.phase.updated_at = now
    tournament.updated_at = now
    session.flush()
    return read_tournament(
        session, league_id=league_id, tournament_id=tournament.id, user_id=user_id
    )


# ---------------------------------------------------------------- delete


def delete_knockout(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    phase_id: UUID,
    user_id: UUID,
    clock: Clock,
) -> None:
    """Delete the knockout that follows a group phase, with its results (FR-046).

    The phase is named by its id, so a repeat, or a screen that saw another
    knockout, gets 404 `phase_not_found` and reloads (ADR-008). A closed
    season is 409 `season_closed`. A group phase, or a knockout without a
    group phase before it, is 422 `phase_not_deletable`: going back to setup
    or deleting a round does that (FR-036, FR-046).

    The knockout's matches and entries go, the fields let go of its matches
    and take the next ones that can be played (BR-130), and the group phase
    is unlocked: the organizer chooses again what comes next (BR-087). A
    finished tournament is back in progress.
    """
    league, tournament = _lock_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user_id,
        rounds=True,
    )
    _require_open_season(league, tournament)
    phase = next((p for p in tournament.phases if p.id == phase_id), None)
    if phase is None:
        raise NotFoundError(ErrorCode.PHASE_NOT_FOUND)
    if phase.kind is not PhaseKind.KNOCKOUT or _group_phase(tournament) is None:
        raise RuleViolationError(ErrorCode.PHASE_NOT_DELETABLE, kind=phase.kind)
    now = clock()
    matches = {match.id for round_ in phase.rounds for match in round_.matches}
    for field in tournament.fields:
        if field.match_id in matches:
            field.match_id = None
            field.updated_at = now
    session.flush()  # the fields let go of the matches before they are deleted
    tournament.phases.remove(phase)
    for entry in [e for e in tournament.entries if e.stage is EntryStage.KNOCKOUT]:
        tournament.entries.remove(entry)
    if tournament.state is TournamentState.FINISHED:
        tournament.state = TournamentState.IN_PROGRESS
    tournament.updated_at = now
    session.flush()  # the matches are gone before the free fields take the next ones
    _fill_fields(tournament, _match_slots(tournament), now)
    session.flush()


# ---------------------------------------------------------------- the bracket

type MatchState = Literal["bye", "played", "on_field", "ready", "waiting"]


@dataclass(frozen=True, slots=True, kw_only=True)
class BracketSideView:
    """A side of a bracket match: the entry and its knockout seed, or a bye.

    `decided_by_lot` says a lot placed the entry among those level with it in
    the group phase, or took it through the cut (BR-074, ADR-009).
    """

    entry_id: UUID | None
    seed: int | None
    is_bye: bool
    decided_by_lot: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class BracketMatchView:
    """A bracket match as the knockout screens show it (screens 9, 10).

    `number` counts the tournament's matches, the group phase's first, and is
    None for a bye, which is not a match (BR-041). `score` is from side 1:
    the goals of a BO1 game, else the games won. `next_number` is the match
    the winner plays next. `result_locked` says a later match it feeds has a
    result, so this one cannot change (BR-094).
    """

    match_id: UUID
    number: int | None
    round_no: int
    position: int
    kind: MatchKind
    state: MatchState
    sides: tuple[BracketSideView, BracketSideView]
    outcome: Outcome | None
    is_walkover: bool
    score: tuple[int, int] | None
    match_format: MatchFormat
    field_number: int | None
    next_number: int | None
    result_locked: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class BracketRoundView:
    round_no: int
    name: RoundName
    matches: tuple[BracketMatchView, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class BracketView:
    """The knockout, computed on read (D4)."""

    phase_id: UUID
    size: int
    third_place_match: bool
    has_group_phase: bool
    match_format: MatchFormat
    final_match_format: KnockoutMatchFormat | None
    rounds: tuple[BracketRoundView, ...]


def read_bracket(
    session: Session, *, league_id: UUID, tournament_id: UUID, user_id: UUID
) -> BracketView:
    """Return the organizer's knockout, read without a lock (screens 9, 10)."""
    league = get_league(session, league_id=league_id, user_id=user_id)
    return view_bracket(session, league=league, tournament_id=tournament_id)


def view_bracket(
    session: Session, *, league: League, tournament_id: UUID, past_setup: bool = False
) -> BracketView:
    """Return one of the league's knockouts, read without a lock.

    A tournament without a knockout is 404 `knockout_not_found`; an unknown
    one, one of another league and, with `past_setup`, one in setup are 404
    `tournament_not_found` (FR-070).
    """
    tournament = _load_tournament(session, league=league, tournament_id=tournament_id)
    if past_setup and tournament.state is TournamentState.SETUP:
        raise NotFoundError(ErrorCode.TOURNAMENT_NOT_FOUND)
    knockout = knockout_bracket(tournament)
    if knockout is None:
        raise NotFoundError(ErrorCode.KNOCKOUT_NOT_FOUND)
    return _bracket_view(tournament, knockout)


def _bracket_view(tournament: Tournament, knockout: KnockoutBracket) -> BracketView:
    seed = {entry.id: entry.seed for entry in tournament.entries}
    by_lot = _decided_by_lot(tournament, knockout)
    on_field = {
        field.match_id: field.number
        for field in tournament.fields
        if field.match_id is not None
    }
    earlier = sum(
        len(_played(round_))
        for phase in tournament.phases
        if phase.position < knockout.phase.position
        for round_ in phase.rounds
    )
    played = {match.key: match for match in knockout.played.values()}
    numbers: dict[UUID, int] = {}
    for key in knockout.bracket.keys:
        if not played[key].has_bye:
            numbers[knockout.rows[key].id] = earlier + len(numbers) + 1
    rounds_by_no = {round_.round_no: round_ for round_ in knockout.phase.rounds}

    def view(match: BracketMatch) -> BracketMatchView:
        row = knockout.rows[match.key]
        later = [
            key for key in feeds(knockout.bracket, match.key) if not key.is_third_place
        ]
        return BracketMatchView(
            match_id=row.id,
            number=numbers.get(row.id),
            round_no=match.key.round_no,
            position=match.key.position,
            kind=match.key.kind,
            state=_state(match, on_field.get(row.id)),
            sides=(
                _side_view(
                    match.side_1.entry_id,
                    is_bye=match.side_1.is_bye,
                    seed=seed,
                    by_lot=by_lot,
                ),
                _side_view(
                    match.side_2.entry_id,
                    is_bye=match.side_2.is_bye,
                    seed=seed,
                    by_lot=by_lot,
                ),
            ),
            outcome=row.outcome,
            is_walkover=row.is_walkover,
            score=_score(row),
            match_format=_match_format(
                knockout.phase, rounds_by_no[match.key.round_no], row
            ),
            field_number=on_field.get(row.id),
            next_number=numbers.get(knockout.rows[later[0]].id) if later else None,
            result_locked=bool(
                locked_by(knockout.bracket, match.key, knockout.outcomes)
            ),
        )

    count = knockout.bracket.round_count
    return BracketView(
        phase_id=knockout.phase.id,
        size=knockout.bracket.size,
        third_place_match=knockout.bracket.third_place_match,
        has_group_phase=_group_phase(tournament) is not None,
        match_format=knockout.phase.match_format,
        final_match_format=knockout.phase.final_match_format,
        rounds=tuple(
            BracketRoundView(
                round_no=round_no,
                name=round_name(round_no, count),
                matches=tuple(
                    view(played[key])
                    for key in knockout.bracket.keys
                    if key.round_no == round_no
                ),
            )
            for round_no in range(1, count + 1)
        ),
    )


def _decided_by_lot(
    tournament: Tournament, knockout: KnockoutBracket
) -> frozenset[UUID]:
    """The knockout entries a lot placed or took through the cut (BR-074, ADR-009).

    Nothing is stored (ADR-010): the cut is computed again from the group
    phase, whose results are locked since the start (BR-053), so it is the one
    that was drawn.
    """
    group = _group_phase(tournament)
    if group is None or group.format not in PLAYED_GROUP_FORMATS:
        return frozenset()
    entries = [e for e in tournament.entries if e.stage is EntryStage.KNOCKOUT]
    cut = _cut(
        tournament,
        group_standings(tournament, group),
        qualifiers=len(entries),
        third_place_match=knockout.bracket.third_place_match,
    )
    return frozenset(
        entry.id for entry in entries if entry.source_entry_id in cut.decided_by_lot
    )


def _side_view(
    entry_id: EntryId | None,
    *,
    is_bye: bool,
    seed: dict[UUID, int | None],
    by_lot: frozenset[UUID],
) -> BracketSideView:
    return BracketSideView(
        entry_id=entry_id,
        seed=None if entry_id is None else seed[entry_id],
        is_bye=is_bye,
        decided_by_lot=entry_id in by_lot,
    )


def _state(match: BracketMatch, field_number: int | None) -> MatchState:
    if match.has_bye:
        return "bye"
    if match.outcome is not None:
        return "played"
    if not match.is_playable:
        return "waiting"
    return "ready" if field_number is None else "on_field"


def _score(match: Match) -> tuple[int, int] | None:
    """Side 1's score: a BO1 game's goals, else the games won; None before a result."""
    if match.outcome is None or not match.games:
        return None
    first = match.games[0]
    if (
        len(match.games) == 1
        and first.score_1 is not None
        and first.score_2 is not None
    ):
        return (first.score_1, first.score_2)
    return (
        sum(game.winner is Outcome.SIDE_1 for game in match.games),
        sum(game.winner is Outcome.SIDE_2 for game in match.games),
    )


def read_shared_bracket(
    session: Session, *, share_token: str, tournament_id: UUID
) -> BracketView:
    """Return a knockout through the share link (FR-070, ADR-008).

    The league is found by its token first (404 `share_link_not_found`); a
    tournament in setup is 404 `tournament_not_found`, like an unknown one.
    """
    league = _shared_league(session, share_token=share_token)
    return view_bracket(
        session, league=league, tournament_id=tournament_id, past_setup=True
    )
