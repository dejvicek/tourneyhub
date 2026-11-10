from collections.abc import Callable
from datetime import datetime
from uuid import uuid7

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tourneyhub.db.models.entries import Entry, EntryMember, PlayerHalf
from tourneyhub.db.models.leagues import League, Player
from tourneyhub.db.models.tournaments import (
    Field,
    Tournament,
    TournamentPhase,
    TournamentPlayer,
)
from tourneyhub.engine.dyp import DypHalf
from tourneyhub.engine.tournaments import (
    EntryKind,
    EntryStage,
    KnockoutMatchFormat,
    MatchFormat,
    PhaseFormat,
    PhaseKind,
    TournamentType,
)


def _check_now(session: Session) -> None:
    """Run the deferred checks, as a commit would (DATA-MODEL §2)."""
    session.flush()
    session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    session.execute(text("SET CONSTRAINTS ALL DEFERRED"))


def _append[T](session: Session, rows: list[T], row: T) -> None:
    rows.append(row)
    session.flush()


def _set_seed(session: Session, entry: Entry, seed: int) -> None:
    entry.seed = seed
    _check_now(session)


def _execute_and_check(session: Session, statement: str, **params: object) -> None:
    session.execute(text(statement), params)
    _check_now(session)


def _pick(
    session: Session, tournament: Tournament, players: list[Player], now: datetime
) -> None:
    for player in players:
        session.add(
            TournamentPlayer(
                tournament_id=tournament.id, player_id=player.id, created_at=now
            )
        )
    session.flush()


def _entry(
    session: Session,
    tournament: Tournament,
    players: list[Player],
    now: datetime,
    *,
    seed: int | None = None,
) -> Entry:
    entry = Entry(
        id=uuid7(),
        tournament_id=tournament.id,
        stage=EntryStage.MAIN,
        kind=EntryKind.PLAYER if len(players) == 1 else EntryKind.PAIR,
        seed=seed,
        created_at=now,
    )
    session.add(entry)
    session.flush()
    for player in players:
        session.add(
            EntryMember(
                entry_id=entry.id,
                player_id=player.id,
                tournament_id=tournament.id,
                stage=EntryStage.MAIN,
                created_at=now,
            )
        )
    session.flush()
    return entry


@pytest.mark.parametrize(
    ("assignments", "constraint"),
    [
        pytest.param(
            "position = 2", "ck_tournament_phases_position", id="D9-group-at-2"
        ),
        pytest.param(
            "format = 'single_elimination'",
            "ck_tournament_phases_format_kind",
            id="FR-031-group-plays-a-knockout",
        ),
        pytest.param(
            "round_robin_legs = NULL",
            "ck_tournament_phases_round_robin_legs",
            id="BR-050-round-robin-without-legs",
        ),
        pytest.param(
            "round_robin_legs = 3",
            "ck_tournament_phases_round_robin_legs",
            id="BR-050-three-legs",
        ),
        pytest.param(
            "sit_out_points = NULL",
            "ck_tournament_phases_sit_out_points",
            id="FR-039-group-without-sit-out-points",
        ),
        pytest.param(
            "sit_out_points = 2",
            "ck_tournament_phases_sit_out_points",
            id="FR-039-two-sit-out-points",
        ),
        pytest.param(
            "tiebreakers = ARRAY['bh1']",
            "ck_tournament_phases_tiebreakers",
            id="FR-043-tiebreakers-in-a-round-robin",
        ),
        pytest.param(
            "third_place_match = false",
            "ck_tournament_phases_third_place_match",
            id="BR-044-third-place-in-a-group",
        ),
        pytest.param(
            "qualifiers = 4",
            "ck_tournament_phases_qualifiers",
            id="FR-045-qualifiers-in-a-group",
        ),
        pytest.param(
            "monster_knockout_mode = 'singles'",
            "ck_tournament_phases_monster_knockout_mode_kind",
            id="FR-045-mode-in-a-group",
        ),
        pytest.param(
            "final_match_format = 'bo3'",
            "ck_tournament_phases_final_match_format_kind",
            id="BR-120-final-in-a-group",
        ),
        pytest.param(
            "match_format = 'bo4'",
            "ck_tournament_phases_match_format",
            id="BR-120-unknown-format",
        ),
    ],
)
def test_d9_the_checks_refuse_a_group_phase_with_settings_that_do_not_fit(
    session: Session,
    make_tournament: Callable[..., Tournament],
    assignments: str,
    constraint: str,
) -> None:
    [phase] = make_tournament().phases

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        session.execute(
            text(f"UPDATE tournament_phases SET {assignments} WHERE id = :id"),  # noqa: S608
            {"id": phase.id},
        )

    assert constraint in str(raised.value)


def _knockout(session: Session, tournament: Tournament, **values: object) -> None:
    """Turn the tournament's group phase into a knockout without one (FR-031)."""
    phase = tournament.phases[0]
    phase.kind = PhaseKind.KNOCKOUT
    phase.format = PhaseFormat.SINGLE_ELIMINATION
    phase.round_robin_legs = None
    phase.sit_out_points = None
    phase.third_place_match = False
    for column, value in values.items():
        setattr(phase, column, value)
    session.flush()


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        pytest.param(
            {"match_format": "bo2"}, "ck_tournament_phases_bo2", id="BR-121-bo2"
        ),
        pytest.param(
            {"third_place_match": None},
            "ck_tournament_phases_third_place_match",
            id="BR-044-no-third-place-setting",
        ),
        pytest.param(
            {"qualifiers": 1},
            "ck_tournament_phases_qualifiers",
            id="FR-045-one-qualifier",
        ),
        pytest.param(
            {"position": 3}, "ck_tournament_phases_position", id="D9-knockout-at-3"
        ),
    ],
)
def test_d9_the_checks_refuse_a_knockout_with_settings_that_do_not_fit(
    session: Session,
    make_tournament: Callable[..., Tournament],
    values: dict[str, object],
    constraint: str,
) -> None:
    tournament = make_tournament()

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        _knockout(session, tournament, **values)

    assert constraint in str(raised.value)


def test_d9_a_knockout_after_the_group_phase_takes_position_2(
    session: Session, make_tournament: Callable[..., Tournament], now: datetime
) -> None:
    tournament = make_tournament()

    tournament.phases.append(
        TournamentPhase(
            position=2,
            kind=PhaseKind.KNOCKOUT,
            format=PhaseFormat.SINGLE_ELIMINATION,
            third_place_match=True,
            qualifiers=4,
            match_format=MatchFormat.BO3,
            final_match_format=KnockoutMatchFormat.BO5,
            created_at=now,
        )
    )
    session.flush()

    assert [phase.position for phase in tournament.phases] == [1, 2]


def test_d9_a_tournament_has_at_most_one_knockout(
    session: Session, make_tournament: Callable[..., Tournament], now: datetime
) -> None:
    tournament = make_tournament()
    _knockout(session, tournament)

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        _append(
            session,
            tournament.phases,
            TournamentPhase(
                position=2,
                kind=PhaseKind.KNOCKOUT,
                format=PhaseFormat.SINGLE_ELIMINATION,
                third_place_match=False,
                match_format=MatchFormat.BO1,
                created_at=now,
            ),
        )

    assert "uq_tournament_phases_tournament_id_kind" in str(raised.value)


@pytest.mark.parametrize(
    ("tiebreakers", "valid"),
    [
        pytest.param("{bh1,bh2,score_difference}", True, id="FR-043-default"),
        pytest.param("{score_difference}", True, id="FR-043-one"),
        pytest.param("{}", True, id="FR-043-all-off"),
        pytest.param("{bh1,bh1}", False, id="FR-043-twice"),
        pytest.param("{bh3}", False, id="FR-043-unknown"),
        pytest.param("{bh1,NULL}", False, id="FR-043-null"),
        pytest.param("{{bh1},{bh2}}", False, id="FR-043-two-dimensional"),
    ],
)
def test_fr043_the_check_keeps_the_tiebreakers_a_subset_without_repeats(
    session: Session,
    make_tournament: Callable[..., Tournament],
    tiebreakers: str,
    valid: bool,
) -> None:
    [phase] = make_tournament(tournament_type=TournamentType.MONSTER_DYP).phases
    update = text(
        "UPDATE tournament_phases SET tiebreakers = CAST(:value AS text[])"
        " WHERE id = :id"
    )

    if valid:
        session.execute(update, {"value": tiebreakers, "id": phase.id})
    else:
        with pytest.raises(IntegrityError) as raised, session.begin_nested():
            session.execute(update, {"value": tiebreakers, "id": phase.id})
        assert "ck_tournament_phases_tiebreakers" in str(raised.value)


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        pytest.param(
            "UPDATE tournaments SET rng_seed = '\\x00'::bytea",
            "ck_tournaments_rng_seed",
            id="ADR-010-short-seed",
        ),
        pytest.param(
            "UPDATE tournaments SET goals_per_game = 100",
            "ck_tournaments_goals_per_game",
            id="BR-123-too-many-goals",
        ),
        pytest.param(
            "UPDATE tournaments SET draw_counter = -1",
            "ck_tournaments_draw_counter",
            id="ADR-010-negative-counter",
        ),
        pytest.param(
            "UPDATE fields SET number = 33",
            "ck_fields_number",
            id="FR-090-field-33",
        ),
    ],
)
def test_fr030_the_checks_refuse_impossible_tournament_values(
    session: Session,
    make_tournament: Callable[..., Tournament],
    statement: str,
    constraint: str,
) -> None:
    make_tournament()

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        session.execute(text(statement))

    assert constraint in str(raised.value)


def test_fr090_field_numbers_are_unique_per_tournament(
    session: Session, make_tournament: Callable[..., Tournament], now: datetime
) -> None:
    tournament = make_tournament()

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        _append(session, tournament.fields, Field(number=1, created_at=now))

    assert "uq_fields_tournament_id_number" in str(raised.value)


def test_br003_a_player_is_in_one_entry_per_stage(
    session: Session,
    make_tournament: Callable[..., Tournament],
    make_player: Callable[..., Player],
    now: datetime,
) -> None:
    tournament = make_tournament(tournament_type=TournamentType.DOUBLES)
    league = session.get_one(League, _league_id(session, tournament))
    ana, bob, cyd = (make_player(league=league) for _ in range(3))
    _pick(session, tournament, [ana, bob, cyd], now)
    _entry(session, tournament, [ana, bob], now)

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        _entry(session, tournament, [ana, cyd], now)

    assert "uq_entry_members_tournament_id_stage_player_id" in str(raised.value)


def test_fr034_seeds_can_be_swapped_and_are_unique_at_commit(
    session: Session,
    make_tournament: Callable[..., Tournament],
    make_player: Callable[..., Player],
    now: datetime,
) -> None:
    tournament = make_tournament()
    league = session.get_one(League, _league_id(session, tournament))
    ana, bob = make_player(league=league), make_player(league=league)
    _pick(session, tournament, [ana, bob], now)
    first = _entry(session, tournament, [ana], now, seed=1)
    second = _entry(session, tournament, [bob], now, seed=2)

    first.seed, second.seed = 2, 1
    _check_now(session)

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        _set_seed(session, first, 1)
    assert "uq_entries_tournament_id_stage_seed" in str(raised.value)


def test_d6_a_picked_player_is_not_deleted_on_their_own(
    session: Session,
    make_tournament: Callable[..., Tournament],
    make_player: Callable[..., Player],
    now: datetime,
) -> None:
    tournament = make_tournament()
    league = session.get_one(League, _league_id(session, tournament))
    ana = make_player(league=league)
    _pick(session, tournament, [ana], now)
    _entry(session, tournament, [ana], now, seed=1)

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        _execute_and_check(session, "DELETE FROM players WHERE id = :id", id=ana.id)

    assert "_player_id_players" in str(raised.value)


def test_d6_deleting_a_league_removes_its_tournaments_and_their_rows(
    session: Session,
    make_tournament: Callable[..., Tournament],
    make_player: Callable[..., Player],
    now: datetime,
) -> None:
    tournament = make_tournament(tournament_type=TournamentType.DYP)
    league = session.get_one(League, _league_id(session, tournament))
    ana, bob = make_player(league=league), make_player(league=league)
    _pick(session, tournament, [ana, bob], now)
    _entry(session, tournament, [ana, bob], now, seed=1)
    session.add_all(
        PlayerHalf(tournament_id=tournament.id, player_id=p.id, half=h, created_at=now)
        for p, h in ((ana, DypHalf.TOP), (bob, DypHalf.BOTTOM))
    )
    session.flush()

    session.execute(text("DELETE FROM leagues WHERE id = :id"), {"id": league.id})
    _check_now(session)

    for table in ("tournaments", "entries", "entry_members", "dyp_halves", "fields"):
        assert session.scalar(text(f"SELECT count(*) FROM {table}")) == 0  # noqa: S608


def test_fr038_deleting_a_tournament_keeps_its_players_on_the_list(
    session: Session,
    make_tournament: Callable[..., Tournament],
    make_player: Callable[..., Player],
    now: datetime,
) -> None:
    tournament = make_tournament()
    league = session.get_one(League, _league_id(session, tournament))
    ana = make_player(league=league)
    _pick(session, tournament, [ana], now)
    _entry(session, tournament, [ana], now, seed=1)

    session.execute(
        text("DELETE FROM tournaments WHERE id = :id"), {"id": tournament.id}
    )
    _check_now(session)

    assert session.scalar(select(Player.id).where(Player.id == ana.id)) == ana.id
    assert session.scalar(text("SELECT count(*) FROM tournament_players")) == 0


def test_br032_a_dyp_half_needs_a_picked_player(
    session: Session,
    make_tournament: Callable[..., Tournament],
    make_player: Callable[..., Player],
    now: datetime,
) -> None:
    tournament = make_tournament(tournament_type=TournamentType.DYP)
    league = session.get_one(League, _league_id(session, tournament))
    ana = make_player(league=league)

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        _append(
            session,
            tournament.halves,
            PlayerHalf(
                tournament_id=tournament.id,
                player_id=ana.id,
                half=DypHalf.TOP,
                created_at=now,
            ),
        )

    assert "fk_dyp_halves_tournament_id_tournament_players" in str(raised.value)


def _league_id(session: Session, tournament: Tournament) -> object:
    return session.scalar(
        text("SELECT league_id FROM seasons WHERE id = :id"),
        {"id": tournament.season_id},
    )
