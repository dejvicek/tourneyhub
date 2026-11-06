from collections.abc import Callable
from uuid import uuid7

import pytest
from psycopg.errors import NotNullViolation
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import User
from tourneyhub.db.models.leagues import League


def test_a_row_without_created_at_fails_at_the_flush(
    session: Session, make_user: Callable[..., User]
) -> None:
    owner = make_user()

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        session.add(
            League(
                id=uuid7(),
                owner_user_id=owner.id,
                name="No clock",
            )
        )

    assert isinstance(raised.value.orig, NotNullViolation)
