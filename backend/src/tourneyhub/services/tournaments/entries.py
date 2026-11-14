"""Entries of a tournament: players, pairs, halves, seeding and draws."""

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid7

from sqlalchemy import select
from sqlalchemy.orm import Session

from tourneyhub.db.models.entries import Entry, EntryMember, PlayerHalf
from tourneyhub.db.models.leagues import League, Player
from tourneyhub.db.models.tournaments import Tournament, TournamentPlayer
from tourneyhub.engine.doubles import pair_the_rest
from tourneyhub.engine.dyp import (
    DypHalf,
    DypHalves,
    check_hand_halves,
    draw_partners,
    split_halves_by_ranking,
)
from tourneyhub.engine.errors import EngineError, NotEnoughPlayersError
from tourneyhub.engine.ids import EntryId, PlayerId
from tourneyhub.engine.ranking import RankedPlayer
from tourneyhub.engine.seeding import SeedingEntry, seed_by_lot, seed_by_ranking
from tourneyhub.engine.tournaments import (
    EntryKind,
    EntryStage,
    HalvesMethod,
    SeedingMethod,
    TournamentType,
    is_seeded,
)
from tourneyhub.errors import (
    ConflictError,
    ErrorCode,
    NotFoundError,
    RuleViolationError,
)
from tourneyhub.services.engine_errors import to_app_error
from tourneyhub.services.tournaments.places import _ranking
from tourneyhub.services.tournaments.shared import Clock, _lock_setup
from tourneyhub.services.tournaments.views import TournamentSetup, _setup_of


class DrawTarget(StrEnum):
    """What "draw again" draws: the pairs (DYP, Doubles) or the seeds (shuffle)."""

    PAIRS = "pairs"
    SEEDS = "seeds"


def _discard_entries(session: Session, tournament: Tournament) -> None:
    for entry in list(tournament.entries):
        tournament.entries.remove(entry)
    session.flush()  # the members' players are free before new entries take them


def _new_entry(
    tournament: Tournament, player_ids: Iterable[UUID], now: datetime
) -> Entry:
    entry_id = uuid7()
    members = sorted(player_ids)
    entry = Entry(
        id=entry_id,
        tournament_id=tournament.id,
        stage=EntryStage.MAIN,
        kind=EntryKind.PLAYER if len(members) == 1 else EntryKind.PAIR,
        created_at=now,
        members=[
            EntryMember(
                entry_id=entry_id,
                player_id=player_id,
                tournament_id=tournament.id,
                stage=EntryStage.MAIN,
                created_at=now,
            )
            for player_id in members
        ],
    )
    tournament.entries.append(entry)
    return entry


def _set_entries(
    session: Session,
    tournament: Tournament,
    groups: Iterable[frozenset[UUID]],
    now: datetime,
) -> None:
    """Make the main entries exactly `groups`, keeping the entries that stay."""
    wanted = set(groups)
    kept: set[frozenset[UUID]] = set()
    for entry in list(tournament.entries):
        players = frozenset(member.player_id for member in entry.members)
        if players in wanted and entry.stage is EntryStage.MAIN:
            kept.add(players)
        else:
            tournament.entries.remove(entry)
    session.flush()  # the members' players are free before new entries take them
    for players in sorted(wanted - kept, key=sorted):
        _new_entry(tournament, players, now)
    session.flush()


def _halves_of(tournament: Tournament) -> DypHalves | None:
    """The DYP halves when every picked player has one and they are valid (BR-032)."""
    halves = {PlayerId(row.player_id): row.half for row in tournament.halves}
    if len(halves) != len(tournament.players):
        return None
    try:
        return check_hand_halves(halves)
    except EngineError:
        return None


def _set_ranking_halves(
    tournament: Tournament, ranking: Sequence[RankedPlayer], now: datetime
) -> None:
    """Split the picked players by the league ranking (BR-032), or clear the halves.

    With fewer than 4 players there are no halves yet (BR-031).
    """
    picked = {row.player_id for row in tournament.players}
    try:
        split = split_halves_by_ranking(
            (ranked for ranked in ranking if ranked.player_id in picked),
            rng_seed=tournament.rng_seed,
            draw_counter=tournament.draw_counter,
        )
    except NotEnoughPlayersError:
        target: dict[UUID, DypHalf] = {}
    else:
        target = dict.fromkeys(split.top, DypHalf.TOP)
        target |= dict.fromkeys(split.bottom, DypHalf.BOTTOM)
        if split.left_out is not None:
            target[split.left_out] = DypHalf.LEFT_OUT
    _write_halves(tournament, target, now)


def _write_halves(
    tournament: Tournament, target: Mapping[UUID, DypHalf], now: datetime
) -> None:
    """Make the halves rows exactly `target`, updating rows in place."""
    for row in list(tournament.halves):
        if row.player_id not in target:
            tournament.halves.remove(row)
        else:
            row.half = target[row.player_id]
    have = {row.player_id for row in tournament.halves}
    for player_id in sorted(set(target) - have):
        tournament.halves.append(
            PlayerHalf(
                tournament_id=tournament.id,
                player_id=player_id,
                half=target[player_id],
                created_at=now,
            )
        )


def _redraw(
    session: Session,
    tournament: Tournament,
    ranking: Sequence[RankedPlayer],
    now: datetime,
) -> None:
    """Make the entries from the picks and draw again where the inputs are complete.

    ADR-010: Singles and Monster DYP enter each picked player; Doubles keeps the
    pairs whose players are both still picked; DYP splits the halves by the
    ranking (or keeps the hand-set ones) and draws the partners once the halves
    are complete and valid. The seeds follow the seeding method; a hand order is
    discarded. Call it after incrementing the draw counter.
    """
    picked = {row.player_id for row in tournament.players}
    groups: list[frozenset[UUID]] = []
    if tournament.type is TournamentType.DOUBLES:
        groups = [
            players
            for entry in tournament.entries
            if (players := frozenset(m.player_id for m in entry.members)) <= picked
            and len(players) == 2  # noqa: PLR2004  (a pair, BR-030)
        ]
    elif tournament.type is TournamentType.DYP:
        if tournament.halves_method is HalvesMethod.RANKING:
            _set_ranking_halves(tournament, ranking, now)
        halves = _halves_of(tournament)
        if halves is not None:
            groups = [
                frozenset({pair.top, pair.bottom})
                for pair in draw_partners(
                    halves,
                    rng_seed=tournament.rng_seed,
                    draw_counter=tournament.draw_counter,
                )
            ]
    else:
        groups = [frozenset({player_id}) for player_id in picked]
    _set_entries(session, tournament, groups, now)
    _seed(tournament, ranking)


def _seed(tournament: Tournament, ranking: Sequence[RankedPlayer]) -> None:
    """Seed the main entries by the tournament's method (FR-034, BR-021, BR-022)."""
    main = [entry for entry in tournament.entries if entry.stage is EntryStage.MAIN]
    if not is_seeded(tournament.type):
        for entry in main:
            entry.seed = None
        return
    if tournament.seeding_method is SeedingMethod.RANKING:
        order = seed_by_ranking(
            (
                SeedingEntry(
                    entry_id=EntryId(entry.id),
                    player_ids=tuple(PlayerId(m.player_id) for m in entry.members),
                )
                for entry in main
            ),
            ranking,
        )
    else:
        order = seed_by_lot(
            (EntryId(entry.id) for entry in main),
            rng_seed=tournament.rng_seed,
            draw_counter=tournament.draw_counter,
        )
    seeds = {entry_id: seed for seed, entry_id in enumerate(order, start=1)}
    for entry in main:
        entry.seed = seeds[EntryId(entry.id)]


def _new_draw(
    session: Session,
    tournament: Tournament,
    ranking: Sequence[RankedPlayer],
    now: datetime,
) -> None:
    tournament.draw_counter += 1
    tournament.updated_at = now
    _redraw(session, tournament, ranking, now)


def _league_players(
    session: Session, *, league: League, player_ids: Iterable[UUID]
) -> list[Player]:
    """Load players through the league: an id of another league is 404 (ADR-008)."""
    ids = set(player_ids)
    players = list(
        session.scalars(
            select(Player).where(Player.league_id == league.id, Player.id.in_(ids))
        )
    )
    if len(players) != len(ids):
        raise NotFoundError(ErrorCode.PLAYER_NOT_FOUND)
    return players


def set_tournament_players(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    player_ids: Sequence[UUID],
    clock: Clock,
) -> TournamentSetup:
    """Set the players picked for a tournament in setup, the target state (FR-032).

    A removed player cannot be picked (BR-002): 409 `player_removed`, because only a
    screen that was not reloaded after the removal offers one (ADR-008). A changed
    pick makes the entries again and increments the draw counter (ADR-010); a
    repeat changes nothing. The minimum number of entries is checked when the
    tournament is generated (FR-032, FR-035).
    """
    league, tournament = _lock_setup(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    players = _league_players(session, league=league, player_ids=player_ids)
    removed = sorted(player.id for player in players if player.removed_at is not None)
    if removed:
        raise ConflictError(ErrorCode.PLAYER_REMOVED, player_id=str(removed[0]))
    ranking = _ranking(session, league=league, tournament=tournament)
    wanted = set(player_ids)
    have = {row.player_id for row in tournament.players}
    if wanted == have:
        return _setup_of(tournament, ranking)
    now = clock()
    for half in [row for row in tournament.halves if row.player_id not in wanted]:
        tournament.halves.remove(half)
    for row in [row for row in tournament.players if row.player_id not in wanted]:
        tournament.players.remove(row)
    for player_id in sorted(wanted - have):
        tournament.players.append(
            TournamentPlayer(
                tournament_id=tournament.id, player_id=player_id, created_at=now
            )
        )
    session.flush()
    _new_draw(session, tournament, ranking, now)
    session.flush()
    return _setup_of(tournament, ranking)


def _require_type(tournament: Tournament, *types: TournamentType) -> None:
    """A write meant for another type comes from a stale screen: 409 (ADR-008)."""
    if tournament.type not in types:
        raise ConflictError(ErrorCode.TOURNAMENT_TYPE_CHANGED, type=tournament.type)


def _require_picked(tournament: Tournament, player_ids: Iterable[UUID]) -> None:
    """Every player must be picked; otherwise the screen is stale: 409 (ADR-008)."""
    picked = {row.player_id for row in tournament.players}
    missing = sorted(set(player_ids) - picked)
    if missing:
        raise ConflictError(ErrorCode.PLAYER_NOT_PICKED, player_id=str(missing[0]))


def set_doubles_pairs(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    pairs: Sequence[tuple[UUID, UUID]],
    clock: Clock,
) -> TournamentSetup:
    """Set a Doubles tournament's pairs, the target state (FR-033, BR-003, BR-030).

    Every player must be picked (409 `player_not_picked`); picked players left
    out of `pairs` have no partner yet. A change seeds again and increments the
    draw counter (ADR-010); a repeat changes nothing.
    """
    league, tournament = _lock_setup(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    _require_type(tournament, TournamentType.DOUBLES)
    _require_picked(tournament, (player for pair in pairs for player in pair))
    ranking = _ranking(session, league=league, tournament=tournament)
    wanted = {frozenset(pair) for pair in pairs}
    have = {
        frozenset(m.player_id for m in entry.members) for entry in tournament.entries
    }
    if wanted == have:
        return _setup_of(tournament, ranking)
    now = clock()
    _set_entries(session, tournament, wanted, now)
    _new_draw(session, tournament, ranking, now)
    session.flush()
    return _setup_of(tournament, ranking)


def set_dyp_halves(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    method: HalvesMethod,
    halves: Mapping[UUID, DypHalf],
    clock: Clock,
) -> TournamentSetup:
    """Set how a DYP tournament's halves are made, and by hand the halves (FR-033).

    `ranking` splits the picked players by the league ranking and ignores
    `halves` (BR-032). `by_hand` stores `halves` as the target state; every
    player in it must be picked (409 `player_not_picked`), and a picked player
    left out has no half yet. Once every picked player has a half and the halves
    are valid (BR-032), the partners are drawn (BR-033); until then there are no
    pairs. A change increments the draw counter (ADR-010); a repeat changes
    nothing.
    """
    league, tournament = _lock_setup(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    _require_type(tournament, TournamentType.DYP)
    ranking = _ranking(session, league=league, tournament=tournament)
    current = {row.player_id: row.half for row in tournament.halves}
    if method is HalvesMethod.BY_HAND:
        _require_picked(tournament, halves)
        if tournament.halves_method is method and current == dict(halves):
            return _setup_of(tournament, ranking)
    elif tournament.halves_method is method:
        return _setup_of(tournament, ranking)
    now = clock()
    tournament.halves_method = method
    if method is HalvesMethod.BY_HAND:
        _write_halves(tournament, halves, now)
    _new_draw(session, tournament, ranking, now)
    session.flush()
    return _setup_of(tournament, ranking)


def set_seeding_method(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    method: SeedingMethod,
    clock: Clock,
) -> TournamentSetup:
    """Seed by league ranking or by random shuffle, the target state (FR-034).

    Monster DYP has no seeds: 409 `tournament_type_changed`. A change seeds
    again, discarding a hand order, and increments the draw counter (ADR-010).
    """
    league, tournament = _lock_setup(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    _require_type(
        tournament, TournamentType.SINGLES, TournamentType.DOUBLES, TournamentType.DYP
    )
    ranking = _ranking(session, league=league, tournament=tournament)
    if tournament.seeding_method is method:
        return _setup_of(tournament, ranking)
    now = clock()
    tournament.seeding_method = method
    tournament.draw_counter += 1
    tournament.updated_at = now
    _seed(tournament, ranking)
    session.flush()
    return _setup_of(tournament, ranking)


def set_seed_order(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    entry_ids: Sequence[UUID],
    clock: Clock,
) -> TournamentSetup:
    """Reorder the seeds by hand: the full order, seed 1 first (FR-034, ADR-008).

    An order that does not list exactly the current main entries is 409
    `seed_order_changed`. It is not a draw, so the counter stays; the next
    change to the entries discards it (ADR-010).
    """
    league, tournament = _lock_setup(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    _require_type(
        tournament, TournamentType.SINGLES, TournamentType.DOUBLES, TournamentType.DYP
    )
    main = {e.id: e for e in tournament.entries if e.stage is EntryStage.MAIN}
    if len(entry_ids) != len(main) or set(entry_ids) != set(main):
        raise ConflictError(ErrorCode.SEED_ORDER_CHANGED)
    changed = False
    for seed, entry_id in enumerate(entry_ids, start=1):
        if main[entry_id].seed != seed:
            main[entry_id].seed = seed
            changed = True
    if changed:
        tournament.updated_at = clock()
    session.flush()
    return _setup_of(
        tournament, _ranking(session, league=league, tournament=tournament)
    )


def draw_again(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    target: DrawTarget,
    expected_draw_counter: int,
    clock: Clock,
) -> TournamentSetup:
    """Draw again: a new DYP draw, pairing the rest, or shuffling (FR-033, FR-034).

    The request carries the draw counter the screen showed; a stale one is 409
    `draw_counter_changed`, so a repeat never draws twice (ADR-008).

    - `pairs` in DYP draws the halves again when they come from the ranking, and
      the partners; hand-set halves must be complete and valid (422
      `dyp_halves_incomplete`, `dyp_halves_unequal`, `too_many_left_out`,
      `not_enough_players`).
    - `pairs` in Doubles pairs the players without a partner by lot; with fewer
      than two of them it is 422 `nothing_to_pair` and changes nothing.
    - `seeds` shuffles the seeds again; only with random seeding (409
      `seeding_method_changed`).
    """
    league, tournament = _lock_setup(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    if tournament.draw_counter != expected_draw_counter:
        raise ConflictError(
            ErrorCode.DRAW_COUNTER_CHANGED, draw_counter=tournament.draw_counter
        )
    ranking = _ranking(session, league=league, tournament=tournament)
    now = clock()
    if target is DrawTarget.SEEDS:
        _require_type(
            tournament,
            TournamentType.SINGLES,
            TournamentType.DOUBLES,
            TournamentType.DYP,
        )
        if tournament.seeding_method is not SeedingMethod.RANDOM:
            raise ConflictError(
                ErrorCode.SEEDING_METHOD_CHANGED,
                seeding_method=tournament.seeding_method,
            )
        tournament.draw_counter += 1
        tournament.updated_at = now
        _seed(tournament, ranking)
    elif tournament.type is TournamentType.DOUBLES:
        _pair_the_rest(session, tournament, ranking, now)
    else:
        _require_type(tournament, TournamentType.DYP)
        _check_dyp_draw(tournament)
        _new_draw(session, tournament, ranking, now)
    session.flush()
    return _setup_of(tournament, ranking)


def _check_dyp_draw(tournament: Tournament) -> None:
    """Refuse a new DYP draw that cannot make pairs (BR-031, BR-032)."""
    try:
        if tournament.halves_method is HalvesMethod.RANKING:
            if len(tournament.players) < 4:  # noqa: PLR2004  (BR-031)
                raise NotEnoughPlayersError(minimum=4, given=len(tournament.players))
            return
        missing = len(tournament.players) - len(tournament.halves)
        if missing:
            raise RuleViolationError(ErrorCode.DYP_HALVES_INCOMPLETE, missing=missing)
        check_hand_halves(
            {PlayerId(row.player_id): row.half for row in tournament.halves}
        )
    except EngineError as err:
        raise to_app_error(err) from err


def _pair_the_rest(
    session: Session,
    tournament: Tournament,
    ranking: Sequence[RankedPlayer],
    now: datetime,
) -> None:
    """Pair the Doubles players without a partner by lot (FR-033).

    Fewer than two of them leave nothing to pair: 422 `nothing_to_pair`, before the
    draw counter moves, so that the seeds stay as they were.
    """
    paired = {m.player_id for entry in tournament.entries for m in entry.members}
    rest = [
        PlayerId(row.player_id)
        for row in tournament.players
        if row.player_id not in paired
    ]
    if len(rest) < 2:  # noqa: PLR2004  (a pair)
        raise RuleViolationError(ErrorCode.NOTHING_TO_PAIR, unpaired=len(rest))
    tournament.draw_counter += 1
    tournament.updated_at = now
    for top, bottom in pair_the_rest(
        rest, rng_seed=tournament.rng_seed, draw_counter=tournament.draw_counter
    ):
        _new_entry(tournament, (top, bottom), now)
    session.flush()
    _seed(tournament, ranking)
