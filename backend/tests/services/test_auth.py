import hashlib
import threading
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from uuid import UUID, uuid7

import argon2
import pytest
from argon2 import PasswordHasher
from pydantic import SecretStr
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import AuthAttempt, RefreshToken, User
from tourneyhub.engine.auth import AuthAttemptKind
from tourneyhub.errors import ErrorCode, NotAuthenticatedError, TooManyAttemptsError
from tourneyhub.services import auth as auth_service

KEY = SecretStr("x" * 32)


def _fail(session: Session, times: int, *, email: str, ip: str, at: datetime) -> None:
    """Add failed attempts directly, all at one time."""
    for _ in range(times):
        session.add_all(
            [
                AuthAttempt(
                    kind=AuthAttemptKind.LOGIN_EMAIL,
                    key=email,
                    succeeded=False,
                    created_at=at,
                ),
                AuthAttempt(
                    kind=AuthAttemptKind.LOGIN_IP,
                    key=ip,
                    succeeded=False,
                    created_at=at,
                ),
            ]
        )
    session.flush()


def _retry_after(session: Session, *, email: str, ip: str, now: datetime) -> int:
    """0 if the attempt is let through, else the seconds of its 429."""
    with session.begin_nested():
        try:
            auth_service.start_login_attempt(session, email=email, ip=ip, now=now)
        except TooManyAttemptsError as refused:
            return refused.retry_after
        return 0


@pytest.mark.parametrize(
    ("failures", "seconds"),
    [
        pytest.param(2, 0, id="free-failures"),
        pytest.param(3, 1, id="first-delay"),
        pytest.param(5, 4, id="doubling"),
        pytest.param(9, 8, id="capped"),
        pytest.param(200, 8, id="capped-without-overflow"),
    ],
)
def test_adr006_the_waiting_period_grows_with_failures_for_the_email(
    session: Session, now: datetime, failures: int, seconds: int
) -> None:
    _fail(session, failures, email="ana@example.test", ip="192.0.2.1", at=now)

    retry_after = _retry_after(
        session, email="Ana@Example.test", ip="192.0.2.99", now=now
    )

    assert retry_after == seconds


def test_adr006_an_attempt_after_the_waiting_period_is_checked(
    session: Session, now: datetime
) -> None:
    _fail(session, 5, email="ana@example.test", ip="192.0.2.1", at=now)

    retry_after = _retry_after(
        session,
        email="ana@example.test",
        ip="192.0.2.1",
        now=now + timedelta(seconds=4),
    )

    assert retry_after == 0


def test_adr006_a_refused_attempt_is_not_counted(
    session: Session, now: datetime
) -> None:
    _fail(session, 3, email="ana@example.test", ip="192.0.2.1", at=now)

    for _ in range(5):
        _retry_after(session, email="ana@example.test", ip="192.0.2.1", now=now)

    assert (
        _retry_after(session, email="ana@example.test", ip="192.0.2.1", now=now) == 1
    )  # still the delay of 3 failures


def test_adr006_failures_are_counted_per_client_ip(
    session: Session, now: datetime
) -> None:
    _fail(session, 3, email="a@example.test", ip="192.0.2.7", at=now)

    retry_after = _retry_after(
        session, email="other@example.test", ip="192.0.2.7", now=now
    )

    assert retry_after == 1


@pytest.mark.parametrize(
    ("other_ip", "seconds"),
    [
        pytest.param("2001:db8:0:1:ffff:ffff:ffff:ffff", 1, id="same-64"),
        pytest.param("2001:db8:0:2::1", 0, id="other-64"),
    ],
)
def test_adr006_an_ipv6_client_is_counted_per_64(
    session: Session, now: datetime, other_ip: str, seconds: int
) -> None:
    for number in range(3):
        auth_service.start_login_attempt(
            session, email=f"{number}@example.test", ip="2001:db8:0:1::1", now=now
        )

    retry_after = _retry_after(
        session, email="other@example.test", ip=other_ip, now=now
    )

    assert retry_after == seconds


@pytest.mark.parametrize(
    ("ip", "key"),
    [
        pytest.param("192.0.2.7", "192.0.2.7", id="ipv4"),
        pytest.param("2001:db8:0:1:2:3:4:5", "2001:db8:0:1::/64", id="ipv6"),
        pytest.param("::ffff:192.0.2.7", "192.0.2.7", id="ipv4-mapped"),
        pytest.param("testclient", "testclient", id="not-an-address"),
    ],
)
def test_adr006_the_ip_key_is_the_ipv4_address_or_the_ipv6_64(
    session: Session, now: datetime, ip: str, key: str
) -> None:
    auth_service.start_login_attempt(session, email="a@example.test", ip=ip, now=now)

    keys = session.scalars(
        select(AuthAttempt.key).where(AuthAttempt.kind == AuthAttemptKind.LOGIN_IP)
    ).all()
    assert keys == [key]


def test_fr002_the_throttle_folds_the_email_as_the_login_does(
    session: Session, now: datetime
) -> None:
    # str.lower() folds the final capital sigma to U+03C2, PostgreSQL to U+03C3.
    auth_service.start_login_attempt(
        session, email="ΟΔΟΣ@example.test", ip="192.0.2.1", now=now
    )

    key = session.scalars(
        select(AuthAttempt.key).where(AuthAttempt.kind == AuthAttemptKind.LOGIN_EMAIL)
    ).one()
    assert key == "οδοσ@example.test"
    assert key != "ΟΔΟΣ@example.test".lower()


def test_adr006_failures_outside_the_window_do_not_count(
    session: Session, now: datetime
) -> None:
    _fail(
        session, 5, email="a@example.test", ip="192.0.2.8", at=now - timedelta(hours=1)
    )

    retry_after = _retry_after(session, email="a@example.test", ip="192.0.2.8", now=now)

    assert retry_after == 0


def test_fr002_log_in_folds_the_email_as_the_unique_index_does(
    session: Session, make_user: Callable[..., User], now: datetime
) -> None:
    # str.lower() folds the final capital sigma to U+03C2, PostgreSQL to U+03C3.
    user = make_user(email="ΟΔΟΣ@example.test", password="a passphrase of 15+")

    tokens = auth_service.log_in(
        session,
        attempt=auth_service.Attempt(attempt_ids=()),
        email="ΟΔΟΣ@example.test",
        password="a passphrase of 15+",
        key=KEY,
        now=now,
    )

    claims = auth_service.read_access_token(tokens.access_token, key=KEY, now=now)
    assert claims.user_id == user.id


def test_adr006_an_unknown_email_is_verified_against_a_dummy_hash(
    session: Session,
    make_user: Callable[..., User],
    now: datetime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user()
    verified: list[str] = []
    real_verify = PasswordHasher.verify

    def spy(self: PasswordHasher, password_hash: str, password: str) -> bool:
        verified.append(password_hash)
        return real_verify(self, password_hash, password)

    monkeypatch.setattr(PasswordHasher, "verify", spy)

    with pytest.raises(NotAuthenticatedError) as raised:
        auth_service.log_in(
            session,
            attempt=auth_service.Attempt(attempt_ids=()),
            email="nobody@example.test",
            password="x" * 15,
            key=KEY,
            now=now,
        )

    assert raised.value.code is ErrorCode.NOT_AUTHENTICATED
    assert len(verified) == 1
    assert verified[0] != user.password_hash
    assert argon2.extract_parameters(verified[0]) == argon2.extract_parameters(
        user.password_hash
    )


def test_adr006_passwords_are_hashed_with_argon2id_defaults() -> None:
    password_hash = auth_service.hash_password("a passphrase of 15+")

    assert password_hash.startswith("$argon2id$")
    assert argon2.extract_parameters(password_hash) == argon2.Parameters(
        type=argon2.Type.ID,
        version=19,
        salt_len=16,
        hash_len=32,
        time_cost=3,
        memory_cost=64 * 1024,
        parallelism=4,
    )


@pytest.mark.parametrize(
    "password_hash",
    [pytest.param("!", id="migrated-account"), pytest.param("", id="empty")],
)
def test_adr006_a_hash_that_is_not_argon2_matches_no_password(
    password_hash: str,
) -> None:
    assert auth_service.verify_password(password_hash, "!") is False


def test_adr006_at_most_four_hashes_and_verifications_run_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = threading.Lock()
    running = 0
    most = 0

    def slow(*_args: object) -> str:
        nonlocal running, most
        with lock:
            running += 1
            most = max(most, running)
        time.sleep(0.05)
        with lock:
            running -= 1
        return "$argon2id$"

    monkeypatch.setattr(PasswordHasher, "hash", slow)
    monkeypatch.setattr(PasswordHasher, "verify", slow)
    workers = [
        threading.Thread(target=auth_service.hash_password, args=("x",))
        for _ in range(6)
    ] + [
        threading.Thread(target=auth_service.verify_password, args=("h", "x"))
        for _ in range(6)
    ]

    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert most == 4


def test_adr006_an_access_token_carries_the_user_and_the_family(
    now: datetime,
) -> None:
    user_id, family_id = uuid7(), uuid7()
    token = auth_service.issue_access_token(
        user_id=user_id, family_id=family_id, key=KEY, now=now
    )

    claims = auth_service.read_access_token(token, key=KEY, now=now)

    assert (claims.user_id, claims.family_id) == (user_id, family_id)


def test_adr006_an_expired_access_token_is_token_expired(now: datetime) -> None:
    token = auth_service.issue_access_token(
        user_id=uuid7(), family_id=uuid7(), key=KEY, now=now
    )

    with pytest.raises(NotAuthenticatedError) as raised:
        auth_service.read_access_token(token, key=KEY, now=now + timedelta(minutes=15))

    assert raised.value.code is ErrorCode.TOKEN_EXPIRED


def test_adr006_an_account_without_an_argon2_hash_still_verifies_a_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verified: list[str] = []
    real_verify = PasswordHasher.verify

    def spy(self: PasswordHasher, password_hash: str, password: str) -> bool:
        verified.append(password_hash)
        return real_verify(self, password_hash, password)

    monkeypatch.setattr(PasswordHasher, "verify", spy)

    assert auth_service.verify_password("!", "a passphrase of 15+") is False

    assert verified[0] == "!"
    assert len(verified) == 2
    assert verified[1].startswith("$argon2id$")  # the dummy, as for an unknown email


def test_adr006_a_rehash_does_not_overwrite_a_hash_changed_meanwhile(
    session: Session,
    make_user: Callable[..., User],
    now: datetime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=8 * 1024, parallelism=1)
    user = make_user(password_hash=weak.hash("a passphrase of 15+"))
    user_id = user.id
    real_hash = auth_service.hash_password

    def hash_while_the_password_changes(password: str) -> str:
        session.execute(  # a password change committing meanwhile
            update(User).where(User.id == user_id).values(password_hash="changed")
        )
        return real_hash(password)

    monkeypatch.setattr(auth_service, "hash_password", hash_while_the_password_changes)

    auth_service.log_in(
        session,
        attempt=auth_service.Attempt(attempt_ids=()),
        email=user.email,
        password="a passphrase of 15+",
        key=KEY,
        now=now,
    )

    session.expire_all()
    assert session.get_one(User, user_id).password_hash == "changed"


def test_adr006_a_token_deleted_between_the_read_and_the_lock_is_refused(
    session: Session,
    make_user: Callable[..., User],
    now: datetime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user(password="a passphrase of 15+")
    tokens = auth_service.log_in(
        session,
        attempt=auth_service.Attempt(attempt_ids=()),
        email=user.email,
        password="a passphrase of 15+",
        key=KEY,
        now=now,
    )
    real_lock = auth_service._lock_family

    def lock_after_a_cleanup(
        session: Session, *, family_id: UUID
    ) -> Sequence[RefreshToken]:
        session.execute(delete(RefreshToken).where(RefreshToken.family_id == family_id))
        return real_lock(session, family_id=family_id)

    monkeypatch.setattr(auth_service, "_lock_family", lock_after_a_cleanup)

    with pytest.raises(NotAuthenticatedError) as raised:
        auth_service.refresh_session(
            session, refresh_token=tokens.refresh_token, key=KEY, now=now
        )

    assert raised.value.code is ErrorCode.NOT_AUTHENTICATED


def _token_row(session: Session, token: str) -> RefreshToken:
    return session.scalars(
        select(RefreshToken).where(
            RefreshToken.token_hash == hashlib.sha256(token.encode()).digest()
        )
    ).one()


def _fail_signups(session: Session, times: int, *, ip: str, at: datetime) -> None:
    session.add_all(
        AuthAttempt(
            kind=AuthAttemptKind.SIGNUP_IP, key=ip, succeeded=False, created_at=at
        )
        for _ in range(times)
    )
    session.flush()


def _signup_retry_after(session: Session, *, ip: str, now: datetime) -> int:
    with session.begin_nested():
        try:
            auth_service.start_signup_attempt(session, ip=ip, now=now)
        except TooManyAttemptsError as refused:
            return refused.retry_after
        return 0


@pytest.mark.parametrize(
    ("failures", "seconds"),
    [
        pytest.param(4, 0, id="free-failures"),
        pytest.param(5, 1, id="first-delay"),
        pytest.param(8, 8, id="doubling"),
        pytest.param(14, 512, id="doubling-on"),
        pytest.param(15, 900, id="capped-at-15-minutes"),
        pytest.param(200, 900, id="capped-without-overflow"),
    ],
)
def test_adr006_the_sign_up_waiting_period_grows_with_failures_per_ip(
    session: Session, now: datetime, failures: int, seconds: int
) -> None:
    _fail_signups(session, failures, ip="192.0.2.1", at=now)

    assert _signup_retry_after(session, ip="192.0.2.1", now=now) == seconds


def test_adr006_sign_up_failures_are_forgotten_after_an_hour(
    session: Session, now: datetime
) -> None:
    _fail_signups(session, 20, ip="192.0.2.1", at=now)

    assert (
        _signup_retry_after(session, ip="192.0.2.1", now=now + timedelta(hours=1)) == 0
    )
    assert (
        _signup_retry_after(session, ip="192.0.2.1", now=now + timedelta(minutes=59))
        > 0
    )


def test_adr006_sign_up_failures_of_another_ip_and_of_logins_do_not_count(
    session: Session, now: datetime
) -> None:
    _fail_signups(session, 20, ip="192.0.2.99", at=now)
    _fail(session, 20, email="ana@example.test", ip="192.0.2.1", at=now)

    assert _signup_retry_after(session, ip="192.0.2.1", now=now) == 0


def test_adr006_sign_up_counts_an_ipv6_client_per_64(
    session: Session, now: datetime
) -> None:
    _fail_signups(session, 5, ip="2001:db8:1:2::/64", at=now)

    assert _signup_retry_after(session, ip="2001:db8:1:2:aaaa::7", now=now) == 1
    assert _signup_retry_after(session, ip="2001:db8:1:3::7", now=now) == 0


def test_adr006_a_password_change_revokes_every_family_but_the_kept_one(
    session: Session, make_user: Callable[..., User], now: datetime
) -> None:
    user = make_user()
    other = make_user()
    later = now + timedelta(minutes=1)
    families = [
        auth_service.start_session(session, user_id=user.id, key=KEY, now=now)
        for _ in range(3)
    ]
    foreign = auth_service.start_session(session, user_id=other.id, key=KEY, now=now)
    rows = {
        token.refresh_token: _token_row(session, token.refresh_token)
        for token in [*families, foreign]
    }
    already = rows[families[2].refresh_token]
    already.revoked_at = now
    session.flush()

    auth_service.revoke_other_families(
        session,
        user_id=user.id,
        keep_family_id=rows[families[0].refresh_token].family_id,
        now=later,
    )

    session.expire_all()
    assert [rows[token.refresh_token].revoked_at for token in [*families, foreign]] == [
        None,
        later,
        now,
        None,
    ]
