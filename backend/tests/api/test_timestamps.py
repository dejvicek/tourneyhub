from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import uuid7

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import User
from tourneyhub.services import leagues as league_service


def test_created_at_and_updated_at_come_from_one_clock(
    client: TestClient, session: Session, make_user: Callable[..., User], now: datetime
) -> None:
    owner = make_user()
    league_id = uuid7()
    client.post(
        "/api/v1/leagues",
        json={"id": str(league_id), "name": "Old"},
        headers={"X-User-Id": str(owner.id)},
    )

    league = league_service.rename_league(
        session,
        league_id=league_id,
        user_id=owner.id,
        expected_name="Old",
        name="New",
        now=now + timedelta(minutes=1),
    )

    assert league.created_at == now
    assert league.updated_at == now + timedelta(minutes=1)
