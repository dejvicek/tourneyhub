import re
import secrets
import unicodedata
from datetime import datetime
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import InstanceSettings, User
from tourneyhub.engine.accounts import Language
from tourneyhub.errors import ErrorCode, NotAuthenticatedError, RuleViolationError
from tourneyhub.services import auth as auth_service

# NIST SP 800-63B-4 asks 15 characters for a password used alone (ADR-006). FR-002
# says 15 to 1024 characters, and the MVP checks no list of common or breached
# passwords (decided in #48). The maximum bounds the Argon2 input. Sign-up, password
# change, an admin's temporary password and `create-admin` share them.
MIN_PASSWORD_LENGTH = 15
MAX_PASSWORD_LENGTH = 1024

# No email-validator dependency: one @, no spaces, a dot in the domain.
EMAIL_MAX_LENGTH = 320
EMAIL_PATTERN = r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$"


# A display name (and a player's name, BR-001): NFC, 1 to 100 characters after strip,
# no invisible characters, runs of whitespace collapsed. The API's `DisplayName` and
# the CLI's `create-admin` share these rules.
DISPLAY_NAME_MAX_LENGTH = 100
# Control and format characters, and the line and paragraph separators, show
# nothing or break a line; U+3164 and U+2800 are letters and symbols that draw blank.
_INVISIBLE_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})
_BLANK_LOOKING = frozenset({"\u3164", "\u2800"})
_WHITESPACE_RUN = re.compile(r"\s+")


def compose_unicode(value: str) -> str:
    """NFC: a letter typed as a base letter and a combining mark is one letter."""
    return unicodedata.normalize("NFC", value)


def has_invisible_characters(name: str) -> bool:
    """Whether the name holds a character that shows nothing or draws blank.

    Control, format, line and paragraph separator characters (Unicode Cc, Cf, Zl,
    Zp), and the blank-looking U+3164 and U+2800.
    """
    return any(
        unicodedata.category(char) in _INVISIBLE_CATEGORIES or char in _BLANK_LOOKING
        for char in name
    )


def collapse_whitespace(name: str) -> str:
    """Every run of whitespace, a no-break space too, becomes one ASCII space."""
    return _WHITESPACE_RUN.sub(" ", name)


def clean_display_name(raw: str) -> str:
    """The display name as the API stores it, or a `ValueError` saying why not.

    The same steps as `DisplayName`: NFC, strip, 1 to 100 characters, no invisible
    characters, whitespace collapsed (BR-001).
    """
    name = compose_unicode(raw).strip()
    if not 1 <= len(name) <= DISPLAY_NAME_MAX_LENGTH:
        raise ValueError(
            f"The display name needs 1 to {DISPLAY_NAME_MAX_LENGTH} characters."
        )
    if has_invisible_characters(name):
        raise ValueError("The display name contains invisible characters.")
    return collapse_whitespace(name)


def load_user(session: Session, *, user_id: UUID) -> User:
    """Load the caller's row, which authorization reads on every request (ADR-006).

    The caller checks `must_change_password`: while it is set, only the auth
    routes and `GET /me` work.
    """
    user = session.get(User, user_id)
    if user is None:
        raise NotAuthenticatedError(ErrorCode.NOT_AUTHENTICATED)
    return user


def sign_up(
    session: Session,
    *,
    attempt: auth_service.Attempt,
    signup_code: str,
    email: str,
    display_name: str,
    password: str,
    language: Language,
    key: SecretStr,
    now: datetime,
) -> auth_service.IssuedTokens:
    """Create an organizer's account and log it in as a login does (FR-001).

    The code is checked first, so that a wrong code learns nothing about which
    emails have an account. Closed sign-up and a wrong code get one error.
    """
    stored = session.get_one(InstanceSettings, 1).signup_code
    if not _code_matches(stored, signup_code):
        raise RuleViolationError(ErrorCode.INVALID_SIGNUP_CODE)
    taken = session.scalar(
        select(User.id).where(func.lower(User.email) == func.lower(email))
    )
    if taken is not None:  # a parallel sign-up is caught by the unique index
        raise RuleViolationError(ErrorCode.EMAIL_TAKEN)
    user = User(
        email=email,
        display_name=display_name,
        password_hash=auth_service.hash_password(password),
        language=language,
        created_at=now,
    )
    session.add(user)
    session.flush()
    auth_service.mark_attempt_succeeded(session, attempt=attempt)
    return auth_service.start_session(session, user_id=user.id, key=key, now=now)


def _code_matches(stored: str | None, given: str) -> bool:
    """Compare in constant time on UTF-8 bytes; `str` would fail on a Czech letter.

    Both sides are normalized to NFC, so that a letter typed as a base letter and
    a combining mark, as some keyboards do, matches the one the admin set.
    NULL means sign-up is closed. It is compared with an empty code all the same,
    so that the time does not tell a closed sign-up from a wrong code.
    """
    expected = _normalize(stored or "").encode()
    matches = secrets.compare_digest(expected, _normalize(given).encode())
    return stored is not None and matches


def _normalize(code: str) -> str:
    return unicodedata.normalize("NFC", code.strip())


def start_password_change_attempt(
    session: Session, *, user_id: UUID, ip: str, now: datetime
) -> auth_service.Attempt:
    """Count a password change before its current password is checked (ADR-006).

    The check guesses the password like a login does, for someone with a stolen
    refresh cookie or access token, so it spends the budget of the login: the
    same kinds, `login_email` and `login_ip`, with the same limits.
    """
    email = session.scalar(select(User.email).where(User.id == user_id))
    if email is None:
        raise NotAuthenticatedError(ErrorCode.NOT_AUTHENTICATED)
    return auth_service.start_login_attempt(session, email=email, ip=ip, now=now)


def change_password(
    session: Session,
    *,
    attempt: auth_service.Attempt,
    user: User,
    keep_family_id: UUID,
    current_password: str,
    new_password: str,
    now: datetime,
) -> None:
    """Set a new password and log the user out everywhere else (FR-004, ADR-006).

    `attempt` is the throttle's count of this call, a failure until the current
    password is right. The login this request came from stays; every other
    family is revoked. The
    new password also ends `must_change_password` after an admin reset, and it
    has to differ from the current one, so that the admin's password does not
    survive the reset.
    """
    # Two changes at once are handled one at a time. NO KEY UPDATE, as the
    # UPDATE below takes it: unlike FOR UPDATE it does not conflict with the
    # FOR KEY SHARE that a refresh's insert of a token takes on this row, which
    # would deadlock with a refresh that holds its family (see below).
    locked = session.scalars(
        select(User)
        .where(User.id == user.id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    ).one()
    if not auth_service.verify_password(locked.password_hash, current_password):
        raise RuleViolationError(ErrorCode.WRONG_PASSWORD)
    if new_password == current_password:
        raise RuleViolationError(ErrorCode.PASSWORD_UNCHANGED)
    auth_service.mark_attempt_succeeded(session, attempt=attempt)
    locked.password_hash = auth_service.hash_password(new_password)
    locked.must_change_password = False
    locked.updated_at = now
    auth_service.revoke_other_families(
        session, user_id=locked.id, keep_family_id=keep_family_id, now=now
    )


def update_profile(
    session: Session,
    *,
    user: User,
    display_name: str | None,
    language: Language | None,
    now: datetime,
) -> User:
    """Change what is given: the display name and the language (FR-081)."""
    changes = {
        name: value
        for name, value in (("display_name", display_name), ("language", language))
        if value is not None and value != getattr(user, name)
    }
    for name, value in changes.items():
        setattr(user, name, value)
    if changes:
        user.updated_at = now
        session.flush()
    return user
