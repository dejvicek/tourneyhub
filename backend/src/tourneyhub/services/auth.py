import contextlib
import functools
import hashlib
import ipaddress
import math
import secrets
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid7

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from pydantic import SecretStr
from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import AuthAttempt, RefreshToken, User
from tourneyhub.engine.auth import AuthAttemptKind
from tourneyhub.errors import ErrorCode, NotAuthenticatedError, TooManyAttemptsError

ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)
REFRESH_TOKEN_LIFETIME = timedelta(days=90)  # restarted by every refresh
REUSE_WINDOW = timedelta(seconds=60)


@dataclass(frozen=True, slots=True)
class _Limits:
    """How failed attempts of one kind add up to a waiting period (ADR-006)."""

    window: timedelta  # failures older than this are forgotten
    free_failures: int
    max_delay: timedelta


# Guessing a password is slowed by Argon2 as well; guessing the sign-up code is
# not, so its limits are stricter and its window longer.
_LOGIN_LIMITS = _Limits(
    window=timedelta(minutes=15), free_failures=3, max_delay=timedelta(seconds=8)
)
_SIGNUP_LIMITS = _Limits(
    window=timedelta(hours=1), free_failures=5, max_delay=timedelta(minutes=15)
)
# Older rows count for nothing and are deleted by `tourneyhub cleanup`.
ATTEMPT_RETENTION = max(_LOGIN_LIMITS.window, _SIGNUP_LIMITS.window)

# argon2-cffi's defaults (RFC 9106's low-memory profile) take 64 MiB per hash. One
# process-wide semaphore lets at most 4 run at once (ADR-006, §10).
_hasher = PasswordHasher()
_hash_slots = threading.BoundedSemaphore(4)
# Refuses HS256 keys shorter than 32 bytes.
_jwt = jwt.PyJWT(options={"enforce_minimum_key_length": True})


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    """A new access token and the refresh token that goes into the cookie."""

    access_token: str
    refresh_token: str


@dataclass(frozen=True, slots=True)
class Attempt:
    """The `auth_attempts` rows of one login or sign-up: failed until it succeeds."""

    attempt_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class AccessClaims:
    """What an access token says: the user and the refresh-token family."""

    user_id: UUID
    family_id: UUID


def hash_password(password: str) -> str:
    """Hash a password with Argon2id under the hashing semaphore (ADR-006)."""
    with _hash_slots:
        return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Check a password under the hashing semaphore (ADR-006).

    A hash that is not an Argon2 hash, such as the "!" that the migration gave
    existing accounts, matches no password. The dummy hash is verified instead,
    so such an account answers as slowly as any other.
    """
    dummy_hash = _dummy_hash()  # first: making it takes a slot of its own
    with _hash_slots:
        try:
            return _hasher.verify(password_hash, password)
        except VerificationError:
            return False
        except InvalidHashError:
            with contextlib.suppress(VerifyMismatchError):
                _hasher.verify(dummy_hash, password)
            return False


@functools.cache
def _dummy_hash() -> str:
    # Hashed once, with the parameters of the real hashes, so that an unknown
    # email costs as much as a wrong password (§10).
    return hash_password(secrets.token_urlsafe(32))


def start_login_attempt(
    session: Session, *, email: str, ip: str, now: datetime
) -> Attempt:
    """Count a login before its password is checked, or refuse it (ADR-006).

    Attempts are counted per email and per client IP. Each key is locked with a
    transaction-level advisory lock, then its failures are counted and the new
    attempt is inserted as a failure, so parallel attempts count each other.
    Beyond the free failures, each failure in the window doubles a waiting
    period from the newest failure, up to a maximum. An attempt inside it is
    refused with `TooManyAttemptsError`, is not counted and never reaches the
    password check. Nothing sleeps, and the account is never locked.
    """
    return _start_attempt(
        session,
        keys={
            # As the login's lookup folds it, with PostgreSQL's lower() (FR-002).
            AuthAttemptKind.LOGIN_EMAIL: session.scalars(
                select(func.lower(email))
            ).one(),
            AuthAttemptKind.LOGIN_IP: _ip_key(ip),
        },
        limits=_LOGIN_LIMITS,
        now=now,
    )


def start_signup_attempt(session: Session, *, ip: str, now: datetime) -> Attempt:
    """Count a sign-up before its code is checked, or refuse it (ADR-006).

    Counted per client IP, like a login, with the stricter limits of sign-up.
    """
    return _start_attempt(
        session,
        keys={AuthAttemptKind.SIGNUP_IP: _ip_key(ip)},
        limits=_SIGNUP_LIMITS,
        now=now,
    )


def _start_attempt(
    session: Session,
    *,
    keys: dict[AuthAttemptKind, str],
    limits: _Limits,
    now: datetime,
) -> Attempt:
    for lock_id in sorted(_lock_id(kind, key) for kind, key in keys.items()):
        session.execute(select(func.pg_advisory_xact_lock(lock_id)))
    wait = max(
        _wait(session, kind=kind, key=key, limits=limits, now=now)
        for kind, key in keys.items()
    )
    if wait > timedelta(0):
        raise TooManyAttemptsError(retry_after=math.ceil(wait.total_seconds()))
    attempts = [
        AuthAttempt(kind=kind, key=key, succeeded=False, created_at=now)
        for kind, key in keys.items()
    ]
    session.add_all(attempts)
    session.flush()
    return Attempt(attempt_ids=tuple(attempt.id for attempt in attempts))


def mark_attempt_succeeded(session: Session, *, attempt: Attempt) -> None:
    """Stop counting `attempt` as a failure."""
    session.execute(
        update(AuthAttempt)
        .where(AuthAttempt.id.in_(attempt.attempt_ids))
        .values(succeeded=True)
    )


def _ip_key(ip: str) -> str:
    """The client IP as `auth_attempts.key`: an IPv6 address counts per /64."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ip  # not an address, e.g. the test client's "testclient"
    if isinstance(address, ipaddress.IPv4Address):
        return str(address)
    if address.ipv4_mapped is not None:  # one IPv4 client, not a /64 of them
        return str(address.ipv4_mapped)
    return str(ipaddress.IPv6Network((address, 64), strict=False))


def _lock_id(kind: AuthAttemptKind, key: str) -> int:
    digest = hashlib.sha256(f"{kind}:{key}".encode()).digest()
    return int.from_bytes(digest[:8], signed=True)  # pg_advisory_xact_lock's bigint


def _wait(
    session: Session,
    *,
    kind: AuthAttemptKind,
    key: str,
    limits: _Limits,
    now: datetime,
) -> timedelta:
    failures, newest = session.execute(
        select(func.count(), func.max(AuthAttempt.created_at)).where(
            AuthAttempt.kind == kind,
            AuthAttempt.key == key,
            AuthAttempt.succeeded.is_(False),
            AuthAttempt.created_at > now - limits.window,
        )
    ).one()
    if failures < limits.free_failures:
        return timedelta(0)
    delay = min(
        2 ** (failures - limits.free_failures), limits.max_delay.total_seconds()
    )
    return newest + timedelta(seconds=delay) - now


def log_in(
    session: Session,
    *,
    attempt: Attempt,
    email: str,
    password: str,
    key: SecretStr,
    now: datetime,
) -> IssuedTokens:
    """Check the password and start a new refresh-token family (ADR-006).

    An unknown email is verified against a dummy hash, so it takes as long as a
    wrong password and gets the same error. A hash made with older parameters is
    replaced, unless a password change replaced it meanwhile, and a login whose
    password a change replaced while it was verified is refused. A success marks
    `attempt`, counted as a failure so far, as succeeded. Login succeeds while
    `must_change_password` is set; the other routes refuse the account until
    the password is changed.

    The email is compared as the unique index `uq_users_lower_email` folds it,
    with PostgreSQL's `lower()` on both sides: Python's `str.lower()` folds a
    word-final capital sigma to U+03C2, PostgreSQL's `lower()` to U+03C3.
    """
    user = session.scalars(
        select(User).where(func.lower(User.email) == func.lower(email))
    ).one_or_none()
    password_hash = _dummy_hash() if user is None else user.password_hash
    verified = verify_password(password_hash, password)
    if user is None or not verified:
        raise NotAuthenticatedError(ErrorCode.NOT_AUTHENTICATED)
    # The verification ran without a lock. A password change may have committed
    # meanwhile, and revoked the families that existed then; this login's family
    # would survive it with the old password. The lock waits for a change that is
    # under way, NO KEY UPDATE as its UPDATE takes it (see `change_password`), and
    # the hash it then reads is the one the change left.
    current_hash = session.scalar(
        select(User.password_hash)
        .where(User.id == user.id)
        .with_for_update(key_share=True)
    )
    if current_hash != user.password_hash:
        raise NotAuthenticatedError(ErrorCode.NOT_AUTHENTICATED)
    if _hasher.check_needs_rehash(user.password_hash):
        session.execute(
            update(User)
            .where(User.id == user.id, User.password_hash == user.password_hash)
            .values(password_hash=hash_password(password), updated_at=now)
        )
    mark_attempt_succeeded(session, attempt=attempt)
    return start_session(session, user_id=user.id, key=key, now=now)


def start_session(
    session: Session, *, user_id: UUID, key: SecretStr, now: datetime
) -> IssuedTokens:
    """Log a user in on a new device: a new refresh-token family (ADR-006)."""
    return _issue_tokens(
        session, user_id=user_id, family_id=uuid7(), parent_id=None, key=key, now=now
    )


def refresh_session(
    session: Session, *, refresh_token: str | None, key: SecretStr, now: datetime
) -> IssuedTokens | None:
    """Exchange a refresh token for new tokens (ADR-006).

    The family's rows are locked before they are read, so presentations within
    one family are handled one at a time. The presented token decides:
    - unknown, revoked or expired: `NotAuthenticatedError`, nothing changes;
    - not yet rotated: it is rotated, and its unrotated siblings are revoked;
    - rotated less than 60 seconds ago: another new token, `rotated_at` stays;
    - rotated earlier: reuse. The whole family is revoked under the same locks
      and None is returned: the caller answers 401 without raising, so that
      the revocation commits (ADR-001).
    """
    if refresh_token is None:
        raise NotAuthenticatedError(ErrorCode.NOT_AUTHENTICATED)
    token_hash = _hash_token(refresh_token)
    family_id = session.scalar(  # never changes, so it is safe to read unlocked
        select(RefreshToken.family_id).where(RefreshToken.token_hash == token_hash)
    )
    if family_id is None:
        raise NotAuthenticatedError(ErrorCode.NOT_AUTHENTICATED)
    family = _lock_family(session, family_id=family_id)
    presented = next((row for row in family if row.token_hash == token_hash), None)
    if presented is None:  # deleted after the unlocked read
        raise NotAuthenticatedError(ErrorCode.NOT_AUTHENTICATED)
    if presented.revoked_at is not None or presented.expires_at <= now:
        raise NotAuthenticatedError(ErrorCode.NOT_AUTHENTICATED)
    if presented.rotated_at is None:
        presented.rotated_at = now
        for sibling in family:
            if (
                sibling.parent_id is not None
                and sibling.parent_id == presented.parent_id
                and sibling.rotated_at is None
                and sibling.revoked_at is None
                and sibling is not presented
            ):
                sibling.revoked_at = now
    elif now - presented.rotated_at >= REUSE_WINDOW:
        _revoke(family, now=now)
        return None
    return _issue_tokens(
        session,
        user_id=presented.user_id,
        family_id=family_id,
        parent_id=presented.id,
        key=key,
        now=now,
    )


def require_live_family(session: Session, *, claims: AccessClaims) -> None:
    """Refuse an access token whose refresh-token family has no unrevoked row.

    A reset, a logout, a password change on another device and a detected reuse
    revoke families; their access tokens stop working at once, not when they
    expire (ADR-006). The answer is the one for an expired token, so the SPA
    refreshes once, fails and logs out. One indexed lookup
    (`ix_refresh_tokens_live_family_id`). A rotation revokes nothing, and adds a
    row, so the family stays live.
    """
    live = session.scalar(
        select(
            exists().where(
                RefreshToken.family_id == claims.family_id,
                RefreshToken.revoked_at.is_(None),
            )
        )
    )
    if not live:
        raise NotAuthenticatedError(ErrorCode.TOKEN_EXPIRED)


def _revoke(family: Sequence[RefreshToken], *, now: datetime) -> None:
    for token in family:
        if token.revoked_at is None:
            token.revoked_at = now


def log_out(session: Session, *, refresh_token: str | None, now: datetime) -> None:
    """Revoke the family of the presented refresh token, if it is known (ADR-006).

    Logging out twice, or without a cookie, changes nothing and is no error.
    """
    if refresh_token is None:
        return
    family_id = session.scalar(
        select(RefreshToken.family_id).where(
            RefreshToken.token_hash == _hash_token(refresh_token)
        )
    )
    if family_id is not None:
        _revoke(_lock_family(session, family_id=family_id), now=now)
        session.flush()


def revoke_other_families(
    session: Session, *, user_id: UUID, keep_family_id: UUID, now: datetime
) -> None:
    """Revoke every family of the user but one: a password change (ADR-006)."""
    _revoke_user_families(
        session, user_id=user_id, keep_family_id=keep_family_id, now=now
    )


def revoke_all_families(session: Session, *, user_id: UUID, now: datetime) -> None:
    """Revoke every family of the user: an admin's password reset (ADR-006)."""
    _revoke_user_families(session, user_id=user_id, keep_family_id=None, now=now)


def _revoke_user_families(
    session: Session, *, user_id: UUID, keep_family_id: UUID | None, now: datetime
) -> None:
    """Revoke the user's families, all but `keep_family_id` if there is one.

    The rows are locked in id order, the order in which `_lock_family` takes
    them, so that a refresh holding one family cannot deadlock with this. A
    refresh that holds a family may add a token meanwhile. In READ COMMITTED
    the first pass does not see it, so a second pass, with a new snapshot,
    revokes it too (see `_lock_family`).
    """
    conditions = [RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)]
    if keep_family_id is not None:
        conditions.append(RefreshToken.family_id != keep_family_id)
    for _ in range(2):
        token_ids = session.scalars(
            select(RefreshToken.id)
            .where(*conditions)
            .order_by(RefreshToken.id)
            .with_for_update()
        ).all()
        session.execute(
            update(RefreshToken)
            .where(RefreshToken.id.in_(token_ids))
            .values(revoked_at=now)
        )


def _lock_family(session: Session, *, family_id: UUID) -> Sequence[RefreshToken]:
    query = (
        select(RefreshToken)
        .where(RefreshToken.family_id == family_id)
        .order_by(RefreshToken.id)  # one lock order for every request
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    # The first statement waits for a request that holds the family. In READ
    # COMMITTED it does not see a token that request added, so the rows are read
    # again by a second statement, under the locks already held.
    session.execute(query.with_only_columns(RefreshToken.id))
    return session.scalars(query).all()


def _issue_tokens(
    session: Session,
    *,
    user_id: UUID,
    family_id: UUID,
    parent_id: UUID | None,
    key: SecretStr,
    now: datetime,
) -> IssuedTokens:
    refresh_token = secrets.token_urlsafe(32)  # 256 bits
    session.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id,
            parent_id=parent_id,
            token_hash=_hash_token(refresh_token),
            expires_at=now + REFRESH_TOKEN_LIFETIME,
            created_at=now,
        )
    )
    session.flush()
    access_token = issue_access_token(
        user_id=user_id, family_id=family_id, key=key, now=now
    )
    return IssuedTokens(access_token=access_token, refresh_token=refresh_token)


def _hash_token(refresh_token: str) -> bytes:
    return hashlib.sha256(refresh_token.encode()).digest()


def issue_access_token(
    *, user_id: UUID, family_id: UUID, key: SecretStr, now: datetime
) -> str:
    """Sign an HS256 access token valid for 15 minutes (ADR-006)."""
    return _jwt.encode(
        {
            "sub": str(user_id),
            "fid": str(family_id),  # the refresh-token family
            "iat": now,
            "exp": now + ACCESS_TOKEN_LIFETIME,
        },
        key.get_secret_value(),
        algorithm="HS256",
    )


def read_access_token(token: str, *, key: SecretStr, now: datetime) -> AccessClaims:
    """Check an access token's signature and expiry (ADR-006).

    The algorithm list is fixed here, never read from the token. The expiry is
    compared with `now` (§4.3), so PyJWT's own checks against the system clock
    are switched off.
    """
    try:
        payload = _jwt.decode(
            token,
            key.get_secret_value(),
            algorithms=["HS256"],
            options={
                "require": ["exp", "iat", "sub", "fid"],
                "verify_exp": False,
                "verify_iat": False,
            },
        )
        claims = AccessClaims(
            user_id=UUID(payload["sub"]), family_id=UUID(str(payload["fid"]))
        )
        expires_at = int(payload["exp"])
    except jwt.InvalidTokenError, ValueError, TypeError:
        raise NotAuthenticatedError(ErrorCode.NOT_AUTHENTICATED) from None
    if expires_at <= now.timestamp():
        raise NotAuthenticatedError(ErrorCode.TOKEN_EXPIRED)
    return claims
