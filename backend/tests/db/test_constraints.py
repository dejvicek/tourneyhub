from collections.abc import Callable

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import User


def test_fr002_two_users_cannot_share_an_email_in_another_case(
    session: Session, make_user: Callable[..., User]
) -> None:
    make_user(email="ana@example.test")

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        make_user(email="Ana@Example.TEST")

    assert "uq_users_lower_email" in str(raised.value)
