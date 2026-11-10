import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from tourneyhub.app import create_app
from tourneyhub.db.models.accounts import User
from tourneyhub.db.models.leagues import League, Player
from tourneyhub.engine.accounts import Language
from tourneyhub.services import leagues as league_service
from tourneyhub.services import players as player_service
from tourneyhub.settings import Settings


def _players_url(league: League | UUID) -> str:
    league_id = league.id if isinstance(league, League) else league
    return f"/api/v1/leagues/{league_id}/players"


def _add(
    client: TestClient, league: League, name: str, headers: dict[str, str]
) -> dict[str, Any]:
    response = client.post(_players_url(league), json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def _put(
    client: TestClient,
    league: League,
    player_id: str,
    what: str,
    body: dict[str, object],
    headers: dict[str, str],
) -> tuple[int, dict[str, Any]]:
    response = client.put(
        f"{_players_url(league)}/{player_id}/{what}", json=body, headers=headers
    )
    result: dict[str, Any] = response.json()
    return response.status_code, result


def test_fr012_post_adds_a_player_and_get_lists_them(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()
    headers = auth_header(league.owner_user_id)

    response = client.post(
        _players_url(league), json={"name": "  Čeněk  "}, headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body == {"id": body["id"], "name": "Čeněk", "removed_at": None}
    assert UUID(body["id"]).version == 7
    listed = client.get(_players_url(league), headers=headers)
    assert listed.status_code == 200
    assert listed.json() == [body]


def test_fr012_get_leaves_out_removed_players_unless_asked(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
    travel: Callable[[timedelta], datetime],
) -> None:
    league = make_league()
    headers = auth_header(league.owner_user_id)
    ana = _add(client, league, "Ana", headers)
    travel(timedelta(minutes=1))
    bob = _add(client, league, "Bob", headers)
    travel(timedelta(minutes=2))
    status, removed = _put(
        client, league, ana["id"], "removed", {"removed": True}, headers
    )
    assert status == 200

    default = client.get(_players_url(league), headers=headers).json()
    without = client.get(
        _players_url(league), params={"include_removed": "false"}, headers=headers
    ).json()
    with_removed = client.get(
        _players_url(league), params={"include_removed": "true"}, headers=headers
    ).json()

    assert default == without == [bob]
    assert with_removed == [removed, bob]
    assert removed["removed_at"] is not None


def test_fr012_get_with_a_malformed_include_removed_is_a_validation_failure(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()

    response = client.get(
        _players_url(league),
        params={"include_removed": "maybe"},
        headers=auth_header(league.owner_user_id),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
    assert {"loc": ["query", "include_removed"], "type": "bool_parsing"} in (
        response.json()["detail"]["errors"]
    )


@pytest.mark.parametrize(
    ("name", "error_type"),
    [
        pytest.param("", "string_too_short", id="FR-012-empty"),
        pytest.param("   ", "string_too_short", id="FR-012-blank"),
        pytest.param("x" * 101, "string_too_long", id="FR-012-too-long"),
        pytest.param("An\u200ba", "invisible_characters", id="BR-001-zero-width"),
    ],
)
def test_fr012_post_refuses_a_name_that_is_not_a_name(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
    name: str,
    error_type: str,
) -> None:
    league = make_league()

    response = client.post(
        _players_url(league),
        json={"name": name},
        headers=auth_header(league.owner_user_id),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
    [problem] = response.json()["detail"]["errors"]
    assert (problem["loc"], problem["type"]) == (["body", "name"], error_type)


def test_br001_post_refuses_a_name_in_another_case_with_the_holder(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()
    headers = auth_header(league.owner_user_id)
    ana = _add(client, league, "Ana", headers)

    response = client.post(_players_url(league), json={"name": "aNA"}, headers=headers)

    assert response.status_code == 422
    assert response.json() == {
        "code": "player_name_taken",
        "detail": {"player_id": ana["id"], "name": "Ana", "removed": False},
    }
    assert len(client.get(_players_url(league), headers=headers).json()) == 1


def test_br001_post_refuses_the_name_of_a_removed_player_until_restored(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()
    headers = auth_header(league.owner_user_id)
    ana = _add(client, league, "Čeněk", headers)
    _put(client, league, ana["id"], "removed", {"removed": True}, headers)

    taken = client.post(_players_url(league), json={"name": "čENĚK"}, headers=headers)
    restored = _put(client, league, ana["id"], "removed", {"removed": False}, headers)

    assert taken.status_code == 422
    assert taken.json() == {
        "code": "player_name_taken",
        "detail": {"player_id": ana["id"], "name": "Čeněk", "removed": True},
    }
    assert restored == (200, ana)
    again = client.post(_players_url(league), json={"name": "čeněk"}, headers=headers)
    assert again.json()["detail"]["removed"] is False


def test_br001_two_leagues_of_one_organizer_can_have_the_same_name(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    first = make_league()
    second = make_league(owner_user_id=first.owner_user_id)
    headers = auth_header(first.owner_user_id)

    _add(client, first, "Ana", headers)
    _add(client, second, "Ana", headers)


def test_fr012_put_name_renames_a_player(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()
    headers = auth_header(league.owner_user_id)
    ana = _add(client, league, "Ana", headers)

    renamed = _put(client, league, ana["id"], "name", {"name": " Anna "}, headers)
    repeated = _put(client, league, ana["id"], "name", {"name": "Anna"}, headers)

    assert renamed == (200, {**ana, "name": "Anna"})
    assert repeated == renamed
    [listed] = client.get(_players_url(league), headers=headers).json()
    assert listed["name"] == "Anna"


def test_br001_put_name_accepts_a_change_of_case_only(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()
    headers = auth_header(league.owner_user_id)
    ana = _add(client, league, "ana", headers)

    status, body = _put(client, league, ana["id"], "name", {"name": "ANA"}, headers)

    assert (status, body["name"]) == (200, "ANA")


@pytest.mark.parametrize("holder_removed", [False, True])
def test_br001_put_name_refuses_the_name_of_any_other_player(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
    holder_removed: bool,
) -> None:
    league = make_league()
    headers = auth_header(league.owner_user_id)
    ana = _add(client, league, "Ana", headers)
    bob = _add(client, league, "Bob", headers)
    if holder_removed:
        _put(client, league, bob["id"], "removed", {"removed": True}, headers)

    status, body = _put(client, league, ana["id"], "name", {"name": "BOB"}, headers)

    assert (status, body) == (
        422,
        {
            "code": "player_name_taken",
            "detail": {
                "player_id": bob["id"],
                "name": "Bob",
                "removed": holder_removed,
            },
        },
    )
    listed = client.get(
        _players_url(league), params={"include_removed": "true"}, headers=headers
    ).json()
    assert [player["name"] for player in listed] == ["Ana", "Bob"]


def test_br002_put_name_refuses_a_removed_player_until_restored(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()
    headers = auth_header(league.owner_user_id)
    ana = _add(client, league, "Ana", headers)
    _put(client, league, ana["id"], "removed", {"removed": True}, headers)

    refused = _put(client, league, ana["id"], "name", {"name": "Anna"}, headers)
    _put(client, league, ana["id"], "removed", {"removed": False}, headers)
    renamed = _put(client, league, ana["id"], "name", {"name": "Anna"}, headers)

    assert refused == (422, {"code": "player_removed", "detail": {}})
    assert renamed[0] == 200
    assert renamed[1]["name"] == "Anna"


def test_br002_put_removed_removes_and_restores_the_same_player(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
    travel: Callable[[timedelta], datetime],
) -> None:
    league = make_league()
    owner_id = league.owner_user_id
    ana = _add(client, league, "Ana", auth_header(owner_id))
    removed_at = travel(timedelta(minutes=1))
    status, removed = _put(
        client,
        league,
        ana["id"],
        "removed",
        {"removed": True},
        auth_header(owner_id, issued_at=removed_at),
    )
    later = travel(timedelta(minutes=2))
    headers = auth_header(owner_id, issued_at=later)

    repeated = _put(client, league, ana["id"], "removed", {"removed": True}, headers)

    assert status == 200
    assert removed == {
        **ana,
        "removed_at": removed_at.isoformat().replace("+00:00", "Z"),
    }
    assert repeated == (200, removed)  # the first removal time stays
    restored = _put(client, league, ana["id"], "removed", {"removed": False}, headers)
    on_list = _put(client, league, ana["id"], "removed", {"removed": False}, headers)
    assert restored == on_list == (200, ana)
    assert client.get(_players_url(league), headers=headers).json() == [ana]


def test_br002_a_removed_player_keeps_the_row_and_the_name(
    client: TestClient,
    session: Session,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()
    headers = auth_header(league.owner_user_id)
    ana = _add(client, league, "Ana", headers)

    _put(client, league, ana["id"], "removed", {"removed": True}, headers)

    player = session.scalars(select(Player).where(Player.id == UUID(ana["id"]))).one()
    assert (player.name, player.removed_at is not None) == ("Ana", True)


def test_br011_players_work_in_a_league_with_a_closed_season(
    client: TestClient,
    session: Session,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
    now: datetime,
) -> None:
    league = make_league()
    headers = auth_header(league.owner_user_id)
    ana = _add(client, league, "Ana", headers)
    league_service.start_season(
        session,
        league_id=league.id,
        user_id=league.owner_user_id,
        expected_current_number=1,
        now=now,
    )

    bob = _add(client, league, "Bob", headers)
    renamed = _put(client, league, ana["id"], "name", {"name": "Anna"}, headers)
    removed = _put(client, league, bob["id"], "removed", {"removed": True}, headers)

    assert (renamed[0], removed[0]) == (200, 200)
    listed = client.get(_players_url(league), headers=headers).json()
    assert [player["name"] for player in listed] == ["Anna"]


def test_owasp_api1_another_organizers_league_is_not_found_on_every_route(
    client: TestClient,
    make_league: Callable[..., League],
    make_user: Callable[..., User],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()
    ana = _add(client, league, "Ana", auth_header(league.owner_user_id))
    stranger = auth_header(make_user().id)
    gone = {"code": "league_not_found", "detail": {}}

    listed = client.get(_players_url(league), headers=stranger)
    added = client.post(_players_url(league), json={"name": "Bob"}, headers=stranger)
    renamed = _put(client, league, ana["id"], "name", {"name": "Bob"}, stranger)
    removed = _put(client, league, ana["id"], "removed", {"removed": True}, stranger)

    assert (listed.status_code, listed.json()) == (404, gone)
    assert (added.status_code, added.json()) == (404, gone)
    assert renamed == (404, gone)
    assert removed == (404, gone)
    owner = auth_header(league.owner_user_id)
    assert client.get(_players_url(league), headers=owner).json() == [ana]


def test_owasp_api1_a_player_of_another_league_is_not_found(
    client: TestClient,
    make_league: Callable[..., League],
    make_user: Callable[..., User],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    owner = make_user()
    mine, other = (
        make_league(owner_user_id=owner.id),
        make_league(owner_user_id=owner.id),
    )
    headers = auth_header(owner.id)
    foreign = _add(client, other, "Ana", headers)
    gone = {"code": "player_not_found", "detail": {}}

    renamed = _put(client, mine, foreign["id"], "name", {"name": "Bob"}, headers)
    removed = _put(client, mine, foreign["id"], "removed", {"removed": True}, headers)
    unknown = _put(client, mine, str(uuid7()), "removed", {"removed": True}, headers)

    assert renamed == removed == unknown == (404, gone)
    assert client.get(_players_url(other), headers=headers).json() == [foreign]


def test_adr006_a_request_without_an_access_token_is_not_authenticated(
    client: TestClient,
) -> None:
    league_id = uuid7()

    responses = [
        client.get(_players_url(league_id)),
        client.post(_players_url(league_id), json={"name": "Ana"}),
        client.put(f"{_players_url(league_id)}/{uuid7()}/name", json={"name": "A"}),
        client.put(
            f"{_players_url(league_id)}/{uuid7()}/removed", json={"removed": True}
        ),
    ]

    assert [r.status_code for r in responses] == [401] * 4


def test_adr008_the_removal_and_the_rename_take_only_their_field(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()
    headers = auth_header(league.owner_user_id)
    ana = _add(client, league, "Ana", headers)

    missing = _put(client, league, ana["id"], "removed", {}, headers)
    extra = _put(
        client, league, ana["id"], "name", {"name": "B", "removed": True}, headers
    )

    assert missing[0] == extra[0] == 422
    assert missing[1]["code"] == extra[1]["code"] == "validation_failed"


def _commit_league(engine: Engine, now: datetime, email: str) -> tuple[UUID, UUID]:
    """Commit an owner and a league with Season 1; return their ids."""
    with Session(engine) as setup:
        owner = User(
            email=email,
            display_name="Racer",
            password_hash="!",
            language=Language.EN,
            created_at=now,
        )
        setup.add(owner)
        setup.flush()
        league = league_service.create_league(
            setup, league_id=uuid7(), owner_user_id=owner.id, name="Race", now=now
        )
        setup.commit()
        return owner.id, league.id


@pytest.mark.concurrency
def test_br001_an_add_racing_a_rename_to_the_same_name_is_a_conflict(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    owner_id, league_id = _commit_league(committing_engine, now, "add@example.test")
    with Session(committing_engine) as setup:
        temp = player_service.add_player(
            setup, league_id=league_id, user_id=owner_id, name="Temp", now=now
        )
        setup.commit()
        temp_id = temp.id
    outcome: list[tuple[int, object]] = []

    with (
        Session(committing_engine) as first,
        TestClient(create_app(committing_settings)) as client,
    ):
        # A write without the league lock, which the app never makes: a rename
        # that is flushed, not committed. The add below does not see it, so only
        # the unique index can stop it. (An insert would take a share lock on the
        # league row, which the add's league lock would wait for.)
        first.get_one(Player, temp_id).name = "Ana"
        first.flush()

        def add_second() -> None:
            response = client.post(
                _players_url(league_id),
                json={"name": "ANA"},
                # The app reads the system clock here, not the test's `now`.
                headers=auth_header(owner_id, issued_at=datetime.now(UTC)),
            )
            outcome.append((response.status_code, response.json()))

        second = threading.Thread(target=add_second)
        second.start()
        wait_for_a_lock_wait()  # its INSERT waits on the first one's row
        first.commit()
        second.join()

    assert outcome == [(409, {"code": "player_name_taken", "detail": {}})]
    with Session(committing_engine) as check:
        assert check.scalars(select(Player.name)).all() == ["Ana"]


@pytest.mark.concurrency
def test_br001_a_rename_racing_a_rename_to_the_same_name_is_a_conflict(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    owner_id, league_id = _commit_league(committing_engine, now, "rename@example.test")
    with Session(committing_engine) as setup:
        temp = player_service.add_player(
            setup, league_id=league_id, user_id=owner_id, name="Temp", now=now
        )
        bob = player_service.add_player(
            setup, league_id=league_id, user_id=owner_id, name="Bob", now=now
        )
        setup.commit()
        temp_id, bob_id = temp.id, bob.id
    outcome: list[tuple[int, object]] = []

    with (
        Session(committing_engine) as first,
        TestClient(create_app(committing_settings)) as client,
    ):
        first.get_one(Player, temp_id).name = "Ana"  # without the league lock
        first.flush()

        def rename_second() -> None:
            response = client.put(
                f"{_players_url(league_id)}/{bob_id}/name",
                json={"name": "ana"},
                headers=auth_header(owner_id, issued_at=datetime.now(UTC)),
            )
            outcome.append((response.status_code, response.json()))

        second = threading.Thread(target=rename_second)
        second.start()
        wait_for_a_lock_wait()  # its UPDATE waits on the first one's row
        first.commit()
        second.join()

    assert outcome == [(409, {"code": "player_name_taken", "detail": {}})]
    with Session(committing_engine) as check:
        names = check.scalars(select(Player.name).order_by(Player.name)).all()
    assert names == ["Ana", "Bob"]


@pytest.mark.concurrency
def test_adr008_two_adds_of_one_name_under_the_league_lock_leave_one_player(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    owner_id, league_id = _commit_league(committing_engine, now, "lock@example.test")
    outcome: list[tuple[int, object]] = []

    with (
        Session(committing_engine) as first,
        TestClient(create_app(committing_settings)) as client,
    ):
        ana = player_service.add_player(
            first, league_id=league_id, user_id=owner_id, name="Ana", now=now
        )

        def add_second() -> None:
            response = client.post(
                _players_url(league_id),
                json={"name": "ana"},
                headers=auth_header(owner_id, issued_at=datetime.now(UTC)),
            )
            outcome.append((response.status_code, response.json()))

        second = threading.Thread(target=add_second)
        second.start()
        wait_for_a_lock_wait()  # it waits for the league lock the first one holds
        ana_id = ana.id
        first.commit()
        second.join()

    assert outcome == [
        (
            422,
            {
                "code": "player_name_taken",
                "detail": {"player_id": str(ana_id), "name": "Ana", "removed": False},
            },
        )
    ]


@pytest.mark.concurrency
def test_br002_a_rename_racing_a_removal_is_refused_after_the_removal(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    owner_id, league_id = _commit_league(committing_engine, now, "remove@example.test")
    with Session(committing_engine) as setup:
        ana = player_service.add_player(
            setup, league_id=league_id, user_id=owner_id, name="Ana", now=now
        )
        setup.commit()
        ana_id = ana.id
    outcome: list[tuple[int, object]] = []

    with (
        Session(committing_engine) as first,
        TestClient(create_app(committing_settings)) as client,
    ):
        player_service.set_player_removed(
            first,
            league_id=league_id,
            player_id=ana_id,
            user_id=owner_id,
            removed=True,
            now=now,
        )

        def rename_second() -> None:
            response = client.put(
                f"{_players_url(league_id)}/{ana_id}/name",
                json={"name": "Anna"},
                headers=auth_header(owner_id, issued_at=datetime.now(UTC)),
            )
            outcome.append((response.status_code, response.json()))

        second = threading.Thread(target=rename_second)
        second.start()
        wait_for_a_lock_wait()  # it waits for the league lock the removal holds
        first.commit()
        second.join()

    assert outcome == [(422, {"code": "player_removed", "detail": {}})]
    with Session(committing_engine) as check:
        assert check.scalars(select(Player.name)).all() == ["Ana"]
