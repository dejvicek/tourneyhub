from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import InstanceSettings, User


def test_fr002_two_users_cannot_share_an_email_in_another_case(
    session: Session, make_user: Callable[..., User]
) -> None:
    make_user(email="ana@example.test")

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        make_user(email="Ana@Example.TEST")

    assert "uq_users_lower_email" in str(raised.value)


def test_adr007_the_migration_makes_the_one_row_with_sign_up_closed(
    session: Session,
) -> None:
    rows = session.scalars(select(InstanceSettings)).all()

    assert [(row.id, row.signup_code) for row in rows] == [(1, None)]


def test_adr007_instance_settings_cannot_get_a_second_row(session: Session) -> None:
    session.add(InstanceSettings(id=2))

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        session.flush()

    assert "ck_instance_settings_single_row" in str(raised.value)
