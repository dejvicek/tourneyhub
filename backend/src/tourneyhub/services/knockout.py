"""The knockout after a group phase: preview, start, final format, delete, bracket.

FR-045, FR-046, FR-054, BR-040 to BR-044, BR-080 to BR-083, BR-085 to BR-087,
BR-094, BR-120. Every write locks the league row, then the tournament row
(ADR-008). Starting creates the knockout's entries and every bracket match at
once, with the first round's sides stored; later sides are derived on read
(D4). An entry continues a qualifying group-phase entry (`source_entry_id`,
BR-085, BR-082), or is a pair of two qualifying players formed after Monster
DYP rounds, without a source (BR-081, BR-083, DATA-MODEL §4.4). Results
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
from tourneyhub.engine.monster_dyp import select_monster_knockout
from tourneyhub.engine.tournaments import (
    EntryKind,
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
from tourneyhub.services.tournaments.play import _player_of, monster_standings_of
from tourneyhub.services.tournaments.results import _match_format
from tourneyhub.services.tournaments.shared import (
    _current_phase,
    _group_phase,
    _load_tournament,
    _lock_tournament,
    _main_entries,
    _match_slots,
    _played,
    _require_open_season,
    final_round_no,
    knockout_phase,
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
    `draw_counter` is the tournament's, which the start must name (ADR-008).
    """

    problem: KnockoutProblem | None
    draw_counter: int
    max_qualifiers: int
    qualifiers: int
    entries: tuple[PreviewEntry, ...]
    first_round: tuple[tuple[int, int | None], ...]
    bracket_size: int | None
    locks_round_no: int | None
    skipped_entry_ids: tuple[UUID, ...]
    is_cut_by_lot: bool


_KNOCKOUT_GROUP_FORMATS = PLAYED_GROUP_FORMATS | {PhaseFormat.MONSTER_DYP}


def _knockout_group(tournament: Tournament) -> TournamentPhase:
    """The round robin, Swiss or Monster DYP rounds a knockout follows (FR-045).

    Without a group phase it is 422 `format_not_supported` (detail `format`).
    """
    group = _group_phase(tournament)
    if group is None or group.format not in _KNOCKOUT_GROUP_FORMATS:
        format_ = tournament.phases[0].format if group is None else group.format
        raise RuleViolationError(ErrorCode.FORMAT_NOT_SUPPORTED, format=format_)
    return group


def _require_mode(
    group: TournamentPhase, mode: MonsterKnockoutMode | None
) -> MonsterKnockoutMode | None:
    """The mode that forms the knockout's entries (FR-045, BR-081 to BR-084).

    After a round robin or a Swiss a mode is 422 `knockout_mode_not_applicable`
    (detail `format`). After Monster DYP rounds every mode goes through, Seeded
    pairs, Singles, A little mercy and Lord have mercy; no mode is 422
    `knockout_mode_required` (detail `format`).
    """
    if group.format is not PhaseFormat.MONSTER_DYP:
        if mode is not None:
            raise RuleViolationError(
                ErrorCode.KNOCKOUT_MODE_NOT_APPLICABLE, format=group.format
            )
        return None
    if mode is None:
        raise RuleViolationError(ErrorCode.KNOCKOUT_MODE_REQUIRED, format=group.format)
    return mode


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


@dataclass(frozen=True, slots=True, kw_only=True)
class _DrawnEntry:
    """A knockout entry the draw forms, by seed (BR-081 to BR-083, BR-085).

    `sources` are the group-phase entries behind it, the better-placed first:
    one after a round robin, a Swiss or in the Singles mode, the main entries
    of a pair's two players otherwise. `decided_by_lot` says a lot drew the
    partner or the seed, placed a source among those level with it, or took
    it through the cut (BR-074, ADR-009).
    """

    seed: int
    sources: tuple[UUID, ...]
    decided_by_lot: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class _Draw:
    """The knockout's entries, seed 1 first, the same for every group phase.

    `skipped` are the main entries of disabled players placed above the last
    qualifier, whom the next ones replaced (BR-080). `is_cut_by_lot` says the
    cut fell inside a shared place (BR-074).
    """

    entries: tuple[_DrawnEntry, ...]
    skipped: tuple[UUID, ...]
    is_cut_by_lot: bool

    @property
    def qualifier_ids(self) -> tuple[UUID, ...]:
        """Every source in seed order, as the start expects them (ADR-008)."""
        return tuple(source for entry in self.entries for source in entry.sources)


def _draw(
    tournament: Tournament,
    group: TournamentPhase,
    *,
    qualifiers: int,
    third_place_match: bool,
    mode: MonsterKnockoutMode | None,
) -> _Draw:
    """The one draw the preview shows and the start writes (FR-045, BR-080).

    A round robin's or a Swiss's best entries go through as they are
    (BR-085); after Monster DYP rounds the mode forms the entries from the
    best players (BR-081 to BR-083), and `qualifiers` counts players. Out of
    range is 422 (BR-080).
    """
    if group.format is not PhaseFormat.MONSTER_DYP:
        cut = _cut(
            tournament,
            group_standings(tournament, group),
            qualifiers=qualifiers,
            third_place_match=third_place_match,
        )
        return _Draw(
            entries=tuple(
                _DrawnEntry(
                    seed=seed,
                    sources=(entry_id,),
                    decided_by_lot=entry_id in cut.decided_by_lot,
                )
                for seed, entry_id in enumerate(cut.seeds, start=1)
            ),
            skipped=tuple(cut.skipped),
            is_cut_by_lot=cut.is_cut_by_lot,
        )
    if mode is None:
        msg = "a knockout after Monster DYP rounds needs a mode"
        raise ValueError(msg)
    return _monster_cut(
        tournament,
        group,
        qualifiers=qualifiers,
        third_place_match=third_place_match,
        mode=mode,
    )


def _monster_cut(
    tournament: Tournament,
    group: TournamentPhase,
    *,
    qualifiers: int,
    third_place_match: bool,
    mode: MonsterKnockoutMode,
) -> _Draw:
    """The engine's entries after Monster DYP rounds (BR-080 to BR-083).

    The engine names players; each is named here by their main entry. The
    lot is `<mode>:<draw_counter>` over the tournament's seed (ADR-010).
    """
    main = _main_entries(tournament)
    entry_of = {_player_of(entry): entry.id for entry in main}
    try:
        knockout = select_monster_knockout(
            monster_standings_of(tournament, group),
            qualifiers=qualifiers,
            mode=mode,
            rng_seed=tournament.rng_seed,
            draw_counter=tournament.draw_counter,
            third_place_match=third_place_match,
            disabled=[_player_of(entry) for entry in main if entry.is_disabled],
        )
    except EngineError as err:
        raise to_app_error(err) from err
    return _Draw(
        entries=tuple(
            _DrawnEntry(
                seed=entry.seed,
                sources=tuple(entry_of[player] for player in entry.player_ids),
                decided_by_lot=entry.is_drawn_by_lot,
            )
            for entry in knockout.entries
        ),
        skipped=tuple(entry_of[player] for player in knockout.skipped),
        is_cut_by_lot=knockout.is_cut_by_lot,
    )


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

    Read without a lock. The draw and the bracket are the start's own, so a
    preview that can start is what the start writes while the results and
    the draw counter stay. The number asked for is kept within what a
    knockout can take, so the screen can always show one; a refusal of the
    start comes back as the `problem`, not as an error. After Monster DYP
    rounds `qualifiers` counts players, and a pair mode keeps it even and at
    least twice the fewest entries (BR-080); without a mode there are no
    entries.
    """
    league = get_league(session, league_id=league_id, user_id=user_id)
    tournament = _load_tournament(session, league=league, tournament_id=tournament_id)
    problem = _start_problem(league, tournament, mode=mode)
    group = _group_phase(tournament)
    is_monster = group is not None and group.format is PhaseFormat.MONSTER_DYP
    if (
        group is None
        or group.format not in _KNOCKOUT_GROUP_FORMATS
        or (is_monster and mode is None)
    ):
        return _empty_preview(
            tournament, problem, max_qualifiers=0, qualifiers=qualifiers, locks=None
        )
    team_size = 2 if is_monster and mode is not MonsterKnockoutMode.SINGLES else 1
    eligible = sum(
        not entry.is_disabled
        for entry in tournament.entries
        if entry.stage is EntryStage.MAIN
    )
    eligible -= eligible % team_size  # a pair mode takes an even number (BR-080)
    minimum = team_size * minimum_qualifiers(third_place_match=third_place_match)
    shown = max(minimum, min(qualifiers, eligible))
    shown -= shown % team_size
    locks = group.rounds[-1].round_no if group.rounds else None
    if eligible < minimum:
        return _empty_preview(
            tournament, problem, max_qualifiers=eligible, qualifiers=shown, locks=locks
        )
    draw = _draw(
        tournament,
        group,
        qualifiers=shown,
        third_place_match=third_place_match,
        mode=mode,
    )
    place = {row.entry_id: row.place for row in group_standings(tournament, group)}
    # No knockout entry exists yet: each drawn entry is keyed by its first source.
    keys = [EntryId(entry.sources[0]) for entry in draw.entries]
    bracket = draw_bracket(keys, third_place_match=third_place_match)
    seed_of = {key: entry.seed for key, entry in zip(keys, draw.entries, strict=True)}
    return KnockoutPreview(
        problem=problem,
        draw_counter=tournament.draw_counter,
        max_qualifiers=eligible,
        qualifiers=shown,
        entries=tuple(
            PreviewEntry(
                seed=entry.seed,
                members=tuple(
                    PreviewMember(entry_id=source, place=place[EntryId(source)])
                    for source in entry.sources
                ),
                decided_by_lot=entry.decided_by_lot,
            )
            for entry in draw.entries
        ),
        first_round=tuple(_seed_pair(match, seed_of) for match in bracket.first_round),
        bracket_size=bracket.size,
        locks_round_no=locks,
        skipped_entry_ids=draw.skipped,
        is_cut_by_lot=draw.is_cut_by_lot,
    )


def _empty_preview(
    tournament: Tournament,
    problem: KnockoutProblem | None,
    *,
    max_qualifiers: int,
    qualifiers: int,
    locks: int | None,
) -> KnockoutPreview:
    """A preview without entries: no knockout can be drawn now (FR-045)."""
    return KnockoutPreview(
        problem=problem,
        draw_counter=tournament.draw_counter,
        max_qualifiers=max_qualifiers,
        qualifiers=qualifiers,
        entries=(),
        first_round=(),
        bracket_size=None,
        locks_round_no=locks,
        skipped_entry_ids=(),
        is_cut_by_lot=False,
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
    if knockout_phase(tournament) is not None:
        current = _current_phase(tournament)
        return KnockoutProblem(
            code=ErrorCode.CURRENT_PHASE_CHANGED,
            detail={"current_phase_id": None if current is None else str(current.id)},
        )
    try:
        group = _knockout_group(tournament)
        _require_mode(group, mode)
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
    are the group-phase entries the preview showed going through, every
    member of every entry in seed order (the cut, the pairs and the seeding,
    which fix the bracket). `expected_draw_counter` is the tournament's
    counter the preview showed. `mode` forms the entries after Monster DYP
    rounds (BR-081 to BR-084), where `qualifiers` counts players.
    """

    expected_current_phase_id: UUID
    expected_draw_counter: int
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
    """Draw the knockout after a group phase and start it (FR-045).

    The request carries the phase the screen saw as the current one, the
    group phase: once the knockout exists it is 409 `current_phase_changed`
    (detail `current_phase_id`), so a repeat draws nothing (ADR-008). A stale
    `expected_draw_counter` is 409 `draw_counter_changed` (detail
    `draw_counter`, the current one), checked right after the phase. A
    tournament not in progress is 409 `tournament_not_in_progress`, a closed
    season 409 `season_closed`. A tournament without a group phase is 422
    `format_not_supported`; Monster DYP without a mode is 422
    `knockout_mode_required` (detail `format`), a mode after another group phase 422
    `knockout_mode_not_applicable`, a group-phase match without a result 422
    `group_phase_not_done`, an odd number of qualifiers in a pair mode 422
    `qualifiers_odd` (detail `given`) and a number out of range 422
    `qualifiers_out_of_range` (detail `minimum`, `maximum`, `given`; BR-080).
    The request also carries the qualifying entries in seed order that the
    preview showed; a group result that changed the cut or the seeds since is
    409 `qualifiers_changed` (detail `entry_ids`, the current ones), so the
    organizer sees the new draw before it is written (ADR-008).

    After a round robin or a Swiss the best entries of the standings go
    through as they are and are seeded by their place; entries still level
    are ordered by the lot `knockout-seeding` (BR-074, BR-085). After Monster
    DYP rounds the best players go through and the mode forms the entries:
    Seeded pairs (BR-081), Singles (BR-082), A little mercy (BR-083) or Lord
    have mercy (BR-084), whose lot is `<mode>:<draw_counter>` (ADR-010). An entry of one player
    continues its main entry (`source_entry_id`); a pair has its two players
    as members and no source (DATA-MODEL §4.4), and stays together for the
    whole knockout (BR-086). Every bracket match is created, the byes for the
    top seeds in round 1 (BR-040 to BR-042), with the third-place match in
    the final's round (BR-044); Lord have mercy stores only round 1, as its
    later rounds are drawn when the round before is complete (BR-084, D4). The phase gets its match format, the league's
    default unless the request names one, the final its own or none (BR-120),
    and the mode. The first matches take the free fields (BR-130), and the
    group phase's results are locked from now on (BR-053, BR-065).
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
    if tournament.draw_counter != start.expected_draw_counter:
        raise ConflictError(
            ErrorCode.DRAW_COUNTER_CHANGED, draw_counter=tournament.draw_counter
        )
    group = _knockout_group(tournament)
    mode = _require_mode(group, start.mode)
    _require_group_done(group)
    draw = _draw(
        tournament,
        group,
        qualifiers=start.qualifiers,
        third_place_match=start.third_place_match,
        mode=mode,
    )
    if draw.qualifier_ids != start.expected_qualifier_ids:
        raise ConflictError(
            ErrorCode.QUALIFIERS_CHANGED,
            entry_ids=[str(i) for i in draw.qualifier_ids],
        )
    _write_knockout(
        session, league, tournament, start=start, draw=draw, mode=mode, now=clock()
    )
    return read_tournament(
        session, league_id=league_id, tournament_id=tournament.id, user_id=user_id
    )


def draw_knockout_again(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    expected_draw_counter: int,
    clock: Clock,
) -> int:
    """Draw the knockout's pairs again after Monster DYP rounds; the new counter.

    The lots of the pair modes come from the draw counter, so counting it up
    gives the next preview a new draw (FR-045, BR-083, ADR-010). The server
    accepts it in every Monster DYP mode; the screen offers it in the lot modes.
    A closed season is 409 `season_closed`, a tournament not in progress 409
    `tournament_not_in_progress`, a knockout that exists 409
    `current_phase_changed` (detail `current_phase_id`), a group phase that is
    not Monster DYP 422 `knockout_mode_not_applicable` (detail `format`), and a
    stale `expected_draw_counter` 409 `draw_counter_changed` (detail
    `draw_counter`), so a repeat never draws twice (ADR-008).
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
    if knockout_phase(tournament) is not None:
        current = _current_phase(tournament)
        raise ConflictError(
            ErrorCode.CURRENT_PHASE_CHANGED,
            current_phase_id=None if current is None else str(current.id),
        )
    group = _group_phase(tournament)
    if group is None or group.format is not PhaseFormat.MONSTER_DYP:
        format_ = tournament.phases[0].format if group is None else group.format
        raise RuleViolationError(ErrorCode.KNOCKOUT_MODE_NOT_APPLICABLE, format=format_)
    if tournament.draw_counter != expected_draw_counter:
        raise ConflictError(
            ErrorCode.DRAW_COUNTER_CHANGED, draw_counter=tournament.draw_counter
        )
    tournament.draw_counter += 1
    tournament.updated_at = clock()
    return tournament.draw_counter


def _write_knockout(
    session: Session,
    league: League,
    tournament: Tournament,
    *,
    start: KnockoutStart,
    draw: _Draw,
    mode: MonsterKnockoutMode | None,
    now: datetime,
) -> None:
    """Store the knockout phase, its entries and every bracket match (D4)."""
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
        monster_knockout_mode=mode,
        match_format=MatchFormat(
            start.match_format or league.default_match_format.value
        ),
        final_match_format=start.final_match_format,
        created_at=now,
        rounds=[],
    )
    tournament.phases.append(phase)
    seeds = _knockout_entries(tournament, draw, now=now)
    session.flush()  # the entries and the phase exist before the matches name them
    members = {entry.id: entry.members for entry in seeds}
    bracket = draw_bracket(
        [EntryId(entry.id) for entry in seeds],
        third_place_match=start.third_place_match,
    )
    rounds = _bracket_rounds(bracket, members, now)
    # Lord have mercy draws each later round once the one before is complete (D4).
    lord_have_mercy = mode is MonsterKnockoutMode.LORD_HAVE_MERCY
    phase.rounds.extend(rounds[:1] if lord_have_mercy else rounds)
    tournament.updated_at = now
    session.flush()  # the matches exist before a field references one
    _fill_fields(tournament, _match_slots(tournament), now)
    session.flush()


def _knockout_entries(
    tournament: Tournament, draw: _Draw, *, now: datetime
) -> list[Entry]:
    """One knockout entry per drawn entry, seed 1 first (BR-081 to BR-085, D4).

    An entry of one source continues it (`source_entry_id`) with its kind
    and members; a pair after Monster DYP rounds has its two players as
    members and no source (DATA-MODEL §4.4).
    """
    by_id = {entry.id: entry for entry in tournament.entries}
    created: list[Entry] = []
    for drawn in draw.entries:
        sources = [by_id[source_id] for source_id in drawn.sources]
        single = sources[0] if len(sources) == 1 else None
        entry_id = uuid7()
        entry = Entry(
            id=entry_id,
            stage=EntryStage.KNOCKOUT,
            kind=EntryKind.PAIR if single is None else single.kind,
            seed=drawn.seed,
            source_entry_id=None if single is None else single.id,
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
                for source in sources
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
    the third-place match keeps the knockout's format. A Lord have mercy
    final is drawn last, and the format waits for it. The change is allowed
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
    phase = knockout_phase(tournament)
    if phase is None:
        raise NotFoundError(ErrorCode.KNOCKOUT_NOT_FOUND)
    final_no = final_round_no(phase)
    final = next(
        (
            match
            for round_ in phase.rounds
            if round_.round_no == final_no
            for match in round_.matches
            if match.kind is MatchKind.STANDARD
        ),
        None,  # a Lord have mercy final not drawn yet (D4)
    )
    if final is not None and final.outcome is not None:
        raise ConflictError(ErrorCode.MATCH_HAS_RESULT, match_id=str(final.id))
    now = clock()
    phase.final_match_format = final_match_format
    phase.updated_at = now
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
    that was drawn. After Monster DYP rounds that is the phase's own
    `qualifiers` and `monster_knockout_mode` with the tournament's draw
    counter, which draw again cannot change once the knockout exists (FR-045).
    """
    group = _group_phase(tournament)
    entries = [e for e in tournament.entries if e.stage is EntryStage.KNOCKOUT]
    if group is not None and group.format is PhaseFormat.MONSTER_DYP:
        phase = knockout.phase
        if phase.qualifiers is None or phase.monster_knockout_mode is None:
            msg = "a knockout after Monster DYP rounds stores its qualifiers and mode"
            raise ValueError(msg)
        draw = _draw(
            tournament,
            group,
            qualifiers=phase.qualifiers,
            third_place_match=knockout.bracket.third_place_match,
            mode=phase.monster_knockout_mode,
        )
        by_lot = {drawn.seed for drawn in draw.entries if drawn.decided_by_lot}
        return frozenset(entry.id for entry in entries if entry.seed in by_lot)
    if group is None or group.format not in PLAYED_GROUP_FORMATS:
        return frozenset()
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
