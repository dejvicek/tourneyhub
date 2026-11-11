from collections.abc import Callable
from datetime import datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import AdminAction, User
from tourneyhub.engine.admin import AdminActionKind, AdminActionSource


def _action(
    now: datetime,
    *,
    source: AdminActionSource,
    action: AdminActionKind,
    admin: User | None = None,
    target: User | None = None,
) -> AdminAction:
    return AdminAction(
        source=source,
        action=action,
        admin_user_id=admin and admin.id,
        target_user_id=target and target.id,
        created_at=now,
    )


def test_adr007_a_web_action_records_the_admin_and_the_target(
    session: Session, make_user: Callable[..., User], now: datetime
) -> None:
    admin, target = make_user(is_admin=True), make_user()
    session.add(
        _action(
            now,
            source=AdminActionSource.WEB,
            action=AdminActionKind.RESET_PASSWORD,
            admin=admin,
            target=target,
        )
    )
    session.flush()

    row = session.scalars(select(AdminAction)).one()
    assert (row.admin_user_id, row.target_user_id) == (admin.id, target.id)


def test_adr007_a_cli_action_has_no_admin(
    session: Session, make_user: Callable[..., User], now: datetime
) -> None:
    target = make_user()
    session.add(
        _action(
            now,
            source=AdminActionSource.CLI,
            action=AdminActionKind.GRANT_ADMIN,
            target=target,
        )
    )
    session.flush()

    assert session.scalars(select(AdminAction)).one().admin_user_id is None


def test_adr007_a_cli_action_cannot_name_an_admin(
    session: Session, make_user: Callable[..., User], now: datetime
) -> None:
    admin = make_user(is_admin=True)
    session.add(
        _action(
            now,
            source=AdminActionSource.CLI,
            action=AdminActionKind.GRANT_ADMIN,
            admin=admin,
            target=make_user(),
        )
    )

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        session.flush()

    assert "ck_admin_actions_cli_action_has_no_admin" in str(raised.value)


def test_adr007_setting_the_signup_code_has_no_target(
    session: Session, make_user: Callable[..., User], now: datetime
) -> None:
    admin = make_user(is_admin=True)
    session.add(
        _action(
            now,
            source=AdminActionSource.WEB,
            action=AdminActionKind.SET_SIGNUP_CODE,
            admin=admin,
            target=admin,
        )
    )

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        session.flush()

    assert "ck_admin_actions_signup_code_has_no_target" in str(raised.value)


def test_adr007_a_web_action_without_an_admin_is_allowed_for_a_deleted_account(
    session: Session, make_user: Callable[..., User], now: datetime
) -> None:
    # The CHECKs work in one direction only (DATA-MODEL §4.1), so SET NULL can
    # clear the admin of a web row when the admin's account is deleted.
    admin, target = make_user(is_admin=True), make_user()
    session.add(
        _action(
            now,
            source=AdminActionSource.WEB,
            action=AdminActionKind.RESET_PASSWORD,
            admin=admin,
            target=target,
        )
    )
    session.flush()

    session.execute(delete(User).where(User.id == admin.id))
    session.expire_all()

    row = session.scalars(select(AdminAction)).one()
    assert (row.source, row.admin_user_id, row.target_user_id) == (
        AdminActionSource.WEB,
        None,
        target.id,
    )


def test_adr007_deleting_the_target_clears_the_reference_and_keeps_the_row(
    session: Session, make_user: Callable[..., User], now: datetime
) -> None:
    admin, target = make_user(is_admin=True), make_user()
    session.add(
        _action(
            now,
            source=AdminActionSource.WEB,
            action=AdminActionKind.RESET_PASSWORD,
            admin=admin,
            target=target,
        )
    )
    session.flush()

    session.execute(delete(User).where(User.id == target.id))
    session.expire_all()

    row = session.scalars(select(AdminAction)).one()
    assert (row.admin_user_id, row.target_user_id) == (admin.id, None)


def test_adr007_the_record_has_no_column_for_the_signup_code() -> None:
    columns = {column.name for column in AdminAction.__table__.columns}

    assert columns == {
        "id",
        "source",
        "admin_user_id",
        "action",
        "target_user_id",
        "created_at",
    }
