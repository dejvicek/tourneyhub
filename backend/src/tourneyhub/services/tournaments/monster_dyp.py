"""Monster DYP: the top players and the draw of a round (FR-041, BR-060 to BR-064).

The standings and the stored rounds as the engine reads them are in `play`,
next to the Swiss's: the standings' reads need them, and `play` cannot import
this module, which reads the league ranking through `places`.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID, uuid7

from sqlalchemy.orm import Session

from tourneyhub.db.models.tournaments import Tournament, TournamentPhase
from tourneyhub.engine.errors import EngineError
from tourneyhub.engine.fields import MatchSlot
from tourneyhub.engine.ids import MatchId, PlayerId
from tourneyhub.engine.monster_dyp import MonsterDraw, draw_monster_round
from tourneyhub.engine.ranking import RankedPlayer
from tourneyhub.engine.tournaments import (
    EntryStage,
    MatchKind,
    Participation,
    TournamentType,
)
from tourneyhub.errors import ConflictError, ErrorCode, RuleViolationError
from tourneyhub.services.engine_errors import to_app_error
from tourneyhub.services.tournaments.entries import _require_type
from tourneyhub.services.tournaments.places import _ranking
from tourneyhub.services.tournaments.play import (
    _player_of,
    monster_rounds,
    monster_standings_of,
)
from tourneyhub.services.tournaments.shared import (
    _lock_setup,
    _main_entries,
    _ScheduleRows,
)
from tourneyhub.services.tournaments.views import TournamentSetup, _setup_of

_PLAYERS_PER_MATCH = 4


def set_top_players(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    player_ids: Sequence[UUID],
) -> TournamentSetup:
    """Mark the top players the organizer picks, the target state (FR-041).

    Every marked player must be picked (409 `player_not_picked`). At most one
    per match of round 1, so at most the player count // 4 (422
    `too_many_top_players`, detail `max`). A player not listed loses the mark.
    The marks are filled up from the league ranking when a round is drawn
    (BR-061), not here.
    """
    league, tournament = _lock_setup(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    _require_type(tournament, TournamentType.MONSTER_DYP)
    picked = {row.player_id for row in tournament.players}
    if not set(player_ids) <= picked:
        missing = sorted(set(player_ids) - picked)
        raise ConflictError(ErrorCode.PLAYER_NOT_PICKED, player_id=str(missing[0]))
    maximum = len(picked) // _PLAYERS_PER_MATCH
    if len(player_ids) > maximum:
        raise RuleViolationError(ErrorCode.TOO_MANY_TOP_PLAYERS, max=maximum)
    marked = set(player_ids)
    for entry in tournament.entries:
        if entry.stage is EntryStage.MAIN:
            entry.is_top_player = any(m.player_id in marked for m in entry.members)
    session.flush()
    return _setup_of(
        tournament, _ranking(session, league=league, tournament=tournament)
    )


def _league_order(
    tournament: Tournament, ranking: Sequence[RankedPlayer]
) -> list[PlayerId]:
    """The tournament's players in league-ranking order, #1 first (BR-020)."""
    players = {_player_of(entry) for entry in _main_entries(tournament)}
    return [
        ranked.player_id
        for ranked in sorted(ranking, key=lambda ranked: ranked.position)
        if ranked.player_id in players
    ]


def ranked_entry_ids(
    tournament: Tournament, ranking: Sequence[RankedPlayer]
) -> list[UUID]:
    """The main entries in league-ranking order: what round 1 is drawn from (BR-060).

    A Monster DYP has no seeds (FR-034), so the preview shows this order and
    the start carries it back as its seed order (ADR-008): a ranking that
    changed in between is a stale start.
    """
    entry_of = {_player_of(entry): entry.id for entry in _main_entries(tournament)}
    return [entry_of[player_id] for player_id in _league_order(tournament, ranking)]


def draw_monster(
    tournament: Tournament,
    group: TournamentPhase,
    *,
    ranking: Sequence[RankedPlayer],
) -> MonsterDraw:
    """Draw the group's next round (FR-041, FR-042, BR-060 to BR-064).

    Round 1 groups the players by the league ranking, a later round by the
    standings' positions (BR-060). In rounds 1 and 2 the top players are the
    organizer's marks, then the others, each in league-ranking order, one per
    match (BR-061); disabled players are not drawn (BR-064). `ranking` is the
    league's as of now (`_ranking` in setup, `_current_ranking` after); only the
    tournament's players count. The draw is
    the same on every call, so the preview shows the round the start stores
    (ADR-010). Fewer than 4 players who are not disabled is 422
    `not_enough_players`.
    """
    main = _main_entries(tournament)
    league_order = _league_order(tournament, ranking)
    rounds = monster_rounds(tournament, group)
    standing = (
        [row.player_id for row in monster_standings_of(tournament, group)]
        if rounds
        else league_order
    )
    try:
        return draw_monster_round(
            standing,
            rounds,
            league_ranking=league_order,
            rng_seed=tournament.rng_seed,
            marked_top_players=[_player_of(e) for e in main if e.is_top_player],
            disabled=[_player_of(e) for e in main if e.is_disabled],
        )
    except EngineError as err:
        raise to_app_error(err) from err


def monster_schedule_rows(
    group: TournamentPhase,
    draw: MonsterDraw,
    entries: Mapping[PlayerId, UUID],
    now: datetime,
) -> _ScheduleRows:
    """The rows of a drawn Monster DYP round, for `_insert_schedule` (D2, D5).

    A group's match puts its 1st and 4th on side 1 and its 2nd and 3rd on
    side 2 (BR-060); a side has no entry and lists its two players (D2).
    `entries` maps each player to their main entry, and every main entry gets
    one participation row (D5): `played`, `sat_out` (BR-063), or `disabled`
    for a player the draw left out (BR-064). The slots are the matches as the
    field queue sees them, so no row needs loading to fill the fields.
    """
    rows = _ScheduleRows(
        rounds=[], matches=[], sides=[], side_players=[], participation=[], slots=[]
    )
    round_id = uuid7()
    rows.rounds.append(
        {
            "id": round_id,
            "phase_id": group.id,
            "round_no": draw.round_no,
            "created_at": now,
        }
    )
    for position, drawn in enumerate(draw.groups, start=1):
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
        for side, team in ((1, drawn.team_1), (2, drawn.team_2)):
            rows.sides.append(
                {
                    "match_id": match_id,
                    "side": side,
                    "entry_id": None,
                    "is_bye": False,
                    "created_at": now,
                }
            )
            rows.side_players.extend(
                {
                    "match_id": match_id,
                    "side": side,
                    "player_id": player_id,
                    "created_at": now,
                }
                for player_id in team
            )
        rows.slots.append(
            MatchSlot(
                match_id=MatchId(match_id),
                phase_position=group.position,
                round_no=draw.round_no,
                kind=MatchKind.STANDARD,
                position=position,
                player_ids=frozenset((*drawn.team_1, *drawn.team_2)),
                has_bye=False,
                has_result=False,
                requeued_at=None,
            )
        )
    playing = {p for drawn in draw.groups for p in (*drawn.team_1, *drawn.team_2)}
    sitting_out = set(draw.sitting_out)
    rows.participation.extend(
        {
            "round_id": round_id,
            "entry_id": entry_id,
            "status": Participation.PLAYED
            if player_id in playing
            else Participation.SAT_OUT
            if player_id in sitting_out
            else Participation.DISABLED,
            "created_at": now,
        }
        for player_id, entry_id in sorted(entries.items(), key=lambda item: item[1])
    )
    return rows
