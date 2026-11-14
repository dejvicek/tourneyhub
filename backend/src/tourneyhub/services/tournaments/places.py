"""Places, season points and the league ranking of a tournament."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from tourneyhub.db.models.entries import Entry
from tourneyhub.db.models.leagues import League, Player, Season
from tourneyhub.db.models.matches import Match
from tourneyhub.db.models.tournaments import Tournament, TournamentPhase
from tourneyhub.engine.ids import EntryId, PlayerId
from tourneyhub.engine.knockout import RoundName, knockout_results, round_name
from tourneyhub.engine.places import EntryPlace, PlacingEntry, place_entries
from tourneyhub.engine.ranking import PlayerRecord, RankedPlayer, rank_league
from tourneyhub.engine.season_points import PlayerPoints, season_points
from tourneyhub.engine.season_standings import SeasonStandingRow, season_standings
from tourneyhub.engine.tournaments import Outcome, PhaseFormat, TournamentState
from tourneyhub.errors import ErrorCode, RuleViolationError
from tourneyhub.services.leagues import get_league
from tourneyhub.services.tournaments.play import (
    GroupStandingRow,
    group_standings,
    tie_groups,
)
from tourneyhub.services.tournaments.shared import (
    _ROUNDS_IN_FULL,
    PLAYED_GROUP_FORMATS,
    KnockoutBracket,
    _group_phase,
    _load_tournament,
    knockout_bracket,
)


def _standings_by_player(
    session: Session, season: Season
) -> dict[PlayerId, SeasonStandingRow]:
    """A season's standings by player: its finished tournaments, added up (BR-112)."""
    points = finished_season_points(session, season=season)
    return {row.player_id: row for row in season_standings(points.values())}


def _previous_season(league: League, season: Season) -> Season | None:
    """The season that started before this one, the latest of them, if any."""
    earlier = [s for s in league.seasons if s.number < season.number]
    return max(earlier, key=lambda s: s.number, default=None)


def _ranking(
    session: Session, *, league: League, tournament: Tournament
) -> tuple[RankedPlayer, ...]:
    """The league ranking of the players on the list, for this tournament (BR-020).

    The final lot uses the tournament's seed (ADR-010). While the tournament is
    in setup, the season points and wins are those of the tournament's season
    and `last_season_place` is the place in the previous season's standings,
    all from finished tournaments (BR-112), as of now. Once it has started, the
    ranking only orders the names inside an entry: seeds and halves are stored,
    and the order must not shift as other tournaments finish. So a started
    tournament skips the standings, which are two reads of every finished
    tournament of two seasons on each poll of a viewer, and ranks everyone
    equal, by lot. A draw that needs the standings of now, as a later round of
    a Monster DYP does, asks `_current_ranking`.
    """
    return _rank_league(
        session,
        league=league,
        tournament=tournament,
        with_standings=tournament.state is TournamentState.SETUP,
    )


def _current_ranking(
    session: Session, *, league: League, tournament: Tournament
) -> tuple[RankedPlayer, ...]:
    """The league ranking as of now, whatever the tournament's state (BR-020).

    The same ranking a setup shows and the start draws round 1 from, but read
    again from the finished tournaments: a Monster DYP picks the top players of
    each of its first rounds from it (BR-061).
    """
    return _rank_league(
        session, league=league, tournament=tournament, with_standings=True
    )


def _rank_league(
    session: Session,
    *,
    league: League,
    tournament: Tournament,
    with_standings: bool,
) -> tuple[RankedPlayer, ...]:
    """The league's players ranked, by the standings or all equal, by lot."""
    player_ids = session.scalars(
        select(Player.id).where(
            Player.league_id == league.id, Player.removed_at.is_(None)
        )
    ).all()
    current: dict[PlayerId, SeasonStandingRow] = {}
    last: dict[PlayerId, SeasonStandingRow] = {}
    if with_standings:
        season = _season_of(league, tournament.season_id)
        current = _standings_by_player(session, season)
        previous = _previous_season(league, season)
        if previous is not None:
            last = _standings_by_player(session, previous)
    records: list[PlayerRecord] = []
    for player_id in player_ids:
        key = PlayerId(player_id)
        now = current.get(key)
        before = last.get(key)
        records.append(
            PlayerRecord(
                player_id=key,
                season_points=0 if now is None else now.points,
                tournament_wins=0 if now is None else now.tournament_wins,
                last_season_place=None if before is None else before.place,
            )
        )
    return rank_league(records, rng_seed=tournament.rng_seed)


type PlaceKind = Literal[
    "won_final",
    "lost_final",
    "won_third_place",
    "lost_third_place",
    "lost_in_round",
    "group_place",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class PlaceView:
    """An entry's final place and what each of its players earns (BR-100, BR-110).

    `kind` says why: the final, the third-place match, the knockout round the
    entry went out in (`round`, with the `score` of that match from the
    entry's side and the `opponent_entry_id`), or, for an entry that did not
    go through, its place in the group phase (BR-102, BR-103). `group_place`
    is the entry's place in the group-phase standings, a knockout entry's
    that of the entry it continues; null without a group phase, and for a
    pair after Monster DYP rounds, which continues no single entry (BR-081).
    """

    place: int
    entry_id: UUID
    points_per_player: int
    kind: PlaceKind
    round: RoundName | None
    score: tuple[int, int] | None
    opponent_entry_id: UUID | None
    group_place: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class PlacesView:
    """The places of a finished tournament; none before it finishes."""

    complete: bool
    group_format: PhaseFormat | None
    rows: tuple[PlaceView, ...]


def _require_played_group(tournament: Tournament) -> TournamentPhase:
    """The round robin, Swiss or Monster DYP of a tournament, with or without a knockout.

    The shared `PLAYED_GROUP_FORMATS` leaves Monster DYP out, so it is
    added here.
    """
    group = _group_phase(tournament)
    if group is None or group.format not in PLAYED_GROUP_FORMATS | {
        PhaseFormat.MONSTER_DYP
    }:
        last = tournament.phases[-1]
        raise RuleViolationError(ErrorCode.FORMAT_NOT_SUPPORTED, format=last.format)
    return group


def _placing_entries(tournament: Tournament) -> list[PlacingEntry]:
    return [
        PlacingEntry(
            entry_id=EntryId(entry.id),
            player_ids=tuple(PlayerId(m.player_id) for m in entry.members),
            seed=entry.seed,
        )
        for entry in tournament.entries
    ]


def knockout_places(
    tournament: Tournament,
    standings: Sequence[GroupStandingRow],
    knockout: KnockoutBracket,
) -> tuple[EntryPlace, ...]:
    """Place a tournament whose knockout has every result (BR-102, BR-103).

    The knockout entries take the top places, and the entries that did not go
    through follow in their group-phase order, numbered after them.
    """
    return place_entries(
        _placing_entries(tournament),
        standing=tie_groups(standings),
        knockout=knockout_results(knockout.played.values()),
        third_place_match=knockout.bracket.third_place_match,
    )


def _score_for(match: Match, entry_side: int) -> tuple[int, int] | None:
    """A result from one side's view: a BO1 game's goals, else the games won.

    A walkover has no score (BR-124), nor a BO1 game without one.
    """
    if match.is_walkover or not match.games:
        return None
    own, other = (Outcome.SIDE_1, Outcome.SIDE_2)[:: 1 if entry_side == 1 else -1]
    if len(match.games) == 1:
        game = match.games[0]
        if game.score_1 is None or game.score_2 is None:
            return None
        goals = (game.score_1, game.score_2)
        return goals if entry_side == 1 else (goals[1], goals[0])
    return (
        sum(game.winner is own for game in match.games),
        sum(game.winner is other for game in match.games),
    )


def _knockout_reason(
    entry_id: UUID, knockout: KnockoutBracket
) -> tuple[PlaceKind, RoundName, tuple[int, int] | None, UUID | None]:
    """Why a knockout entry has its place: the last match it played (BR-102)."""
    last = max(
        (
            match
            for match in knockout.played.values()
            if entry_id in {match.winner, match.loser} and match.loser is not None
        ),
        key=lambda match: match.key,
    )
    won = last.winner == entry_id
    if last.key.is_third_place:
        kind: PlaceKind = "won_third_place" if won else "lost_third_place"
    elif last.key == knockout.bracket.final:
        kind = "won_final" if won else "lost_final"
    else:
        kind = "lost_in_round"
    side = 1 if last.side_1.entry_id == entry_id else 2
    opponent = (last.side_2 if side == 1 else last.side_1).entry_id
    return (
        kind,
        round_name(last.key.round_no, knockout.bracket.round_count),
        _score_for(knockout.rows[last.key], side),
        opponent,
    )


def read_places(
    session: Session, *, league_id: UUID, tournament_id: UUID, user_id: UUID
) -> PlacesView:
    """Return the places and season points of a finished tournament (§7.13, §7.14).

    See `view_places`.
    """
    league = get_league(session, league_id=league_id, user_id=user_id)
    return view_places(session, league=league, tournament_id=tournament_id)


@dataclass(frozen=True, slots=True, kw_only=True)
class _Placed:
    """A finished tournament's group standings, places and season points."""

    group: TournamentPhase | None
    standings: tuple[GroupStandingRow, ...]
    knockout: KnockoutBracket | None
    places: tuple[EntryPlace, ...]
    points: tuple[PlayerPoints, ...]


def _placed(tournament: Tournament, placement_points: Sequence[int]) -> _Placed:
    """Place a finished tournament's entries and give them the table's points.

    Without a knockout the group phase's standings are the places (BR-101,
    BR-103; a Swiss's by BR-072 to BR-074); with one, the knockout entries
    take the top places by BR-102 and the rest follow in their group-phase
    order (BR-103). A knockout without a group phase places every entry by
    BR-102 alone (FR-031). Each player earns the placement points of their
    place, entries sharing a place the average of the places they cover,
    rounded down (BR-110, BR-111). A Monster DYP's places are one player's
    each, by their main entry (BR-100, BR-103).
    """
    group = _group_phase(tournament)
    knockout = knockout_bracket(tournament)
    if group is None and knockout is not None:
        standings: tuple[GroupStandingRow, ...] = ()  # a knockout from the start
    else:
        group = _require_played_group(tournament)
        standings = group_standings(tournament, group)
    if knockout is None:
        places = place_entries(
            _placing_entries(tournament), standing=tie_groups(standings)
        )
    else:
        places = knockout_places(tournament, standings, knockout)
    return _Placed(
        group=group,
        standings=standings,
        knockout=knockout,
        places=places,
        points=season_points(places, placement_points),
    )


def _season_of(league: League, season_id: UUID) -> Season:
    return next(s for s in league.seasons if s.id == season_id)


def view_places(
    session: Session,
    *,
    league: League,
    tournament_id: UUID,
    past_setup: bool = False,
) -> PlacesView:
    """Return the places and season points of one of the league's tournaments.

    Read without a lock and computed on read (D1), with the season's table
    (BR-110, BR-111). A tournament not yet finished has no places. Without a
    knockout the group phase's standings are the places; with one, the knockout
    entries take the top places by BR-102 and the rest follow in their
    group-phase order (BR-103). With `past_setup`, a tournament in setup is 404
    `tournament_not_found`, like an unknown one (FR-070).
    """
    tournament = _load_tournament(
        session, league=league, tournament_id=tournament_id, past_setup=past_setup
    )
    if tournament.state is not TournamentState.FINISHED:
        return PlacesView(complete=False, group_format=None, rows=())
    placed = _placed(
        tournament, _season_of(league, tournament.season_id).placement_points
    )
    knockout = placed.knockout
    points = {row.entry_id: row.points for row in placed.points}
    group_place = {row.entry_id: row.place for row in placed.standings}
    source = {entry.id: entry.source_entry_id for entry in tournament.entries}
    # The entries the bracket drew: knockout entries after a group phase, the
    # main entries of a knockout without one (FR-031).
    in_bracket = (
        set()
        if knockout is None
        else {
            entry_id
            for match in knockout.bracket.first_round
            for entry_id in (match.side_1, match.side_2)
            if entry_id is not None
        }
    )

    def view(place: EntryPlace) -> PlaceView:
        entry_id = place.entry_id
        in_group = group_place.get(EntryId(source[entry_id] or entry_id))
        if knockout is None or entry_id not in in_bracket:
            return PlaceView(
                place=place.place,
                entry_id=entry_id,
                points_per_player=points.get(entry_id, 0),
                kind="group_place",
                round=None,
                score=None,
                opponent_entry_id=None,
                group_place=in_group,
            )
        kind, round_, score, opponent = _knockout_reason(entry_id, knockout)
        return PlaceView(
            place=place.place,
            entry_id=entry_id,
            points_per_player=points.get(entry_id, 0),
            kind=kind,
            round=round_,
            score=score,
            opponent_entry_id=opponent,
            group_place=in_group,
        )

    return PlacesView(
        complete=True,
        group_format=None if placed.group is None else placed.group.format,
        rows=tuple(view(place) for place in placed.places),
    )


def finished_season_points(
    session: Session, *, season: Season
) -> dict[UUID, tuple[PlayerPoints, ...]]:
    """The season points of each finished tournament of a season (BR-112).

    Keyed by tournament id, oldest first; computed with the season's table as
    it is now (BR-012). Tournaments that are not finished do not count.
    """
    tournaments = session.scalars(
        select(Tournament)
        .where(
            Tournament.season_id == season.id,
            Tournament.state == TournamentState.FINISHED,
        )
        .options(
            selectinload(Tournament.phases),
            selectinload(Tournament.entries).selectinload(Entry.members),
            _ROUNDS_IN_FULL,
        )
        .order_by(Tournament.date, Tournament.created_at, Tournament.id)
        .execution_options(populate_existing=True)
    ).all()
    return {
        tournament.id: _placed(tournament, season.placement_points).points
        for tournament in tournaments
    }
