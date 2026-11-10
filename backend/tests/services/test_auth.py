from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import User
from tourneyhub.services import auth as auth_service


def _fail(session: Session, times: int, *, email: str, ip: str, now: datetime) -> None:
    for _ in range(times):
        auth_service.record_login_attempt(
            session, email=email, ip=ip, succeeded=False, now=now
        )


@pytest.mark.parametrize(
    ("failures", "delay"),
    [
        pytest.param(2, timedelta(0), id="free-failures"),
        pytest.param(3, timedelta(seconds=1), id="first-delay"),
        pytest.param(5, timedelta(seconds=4), id="doubling"),
        pytest.param(9, timedelta(seconds=8), id="capped"),
    ],
)
def test_adr006_login_delay_grows_with_failures_for_the_email(
    session: Session, now: datetime, failures: int, delay: timedelta
) -> None:
    _fail(session, failures, email="Ana@Example.test", ip="192.0.2.1", now=now)

    result = auth_service.login_delay(
        session, email="ana@example.test", ip="192.0.2.99", now=now
    )

    assert result == delay


def test_adr006_login_delay_counts_failures_per_client_ip(
    session: Session, now: datetime
) -> None:
    _fail(session, 3, email="a@example.test", ip="192.0.2.7", now=now)

    result = auth_service.login_delay(
        session, email="other@example.test", ip="192.0.2.7", now=now
    )

    assert result == timedelta(seconds=1)


def test_adr006_login_delay_ignores_failures_outside_the_window(
    session: Session, now: datetime
) -> None:
    _fail(
        session, 5, email="a@example.test", ip="192.0.2.8", now=now - timedelta(hours=1)
    )

    result = auth_service.login_delay(
        session, email="a@example.test", ip="192.0.2.8", now=now
    )

    assert result == timedelta(0)


def test_fr002_log_in_folds_the_email_as_the_unique_index_does(
    session: Session, make_user: Callable[..., User]
) -> None:
    # str.lower() folds the final capital sigma to U+03C2, PostgreSQL to U+03C3.
    user = make_user(email="ΟΔΟΣ@example.test")

    found = auth_service.log_in(session, email="ΟΔΟΣ@example.test")

    assert found is user
