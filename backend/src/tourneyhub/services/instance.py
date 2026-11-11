import secrets
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import InstanceSettings

# The code is typed by organizers on a phone and guessed by strangers: not too
# short. The maximum is what the sign-up request accepts.
SIGNUP_CODE_MIN_LENGTH = 12
SIGNUP_CODE_MAX_LENGTH = 256


def set_signup_code(session: Session, *, code: str | None, now: datetime) -> None:
    """Set the sign-up code, or close sign-up with None (ADR-007).

    Existing accounts are not affected (FR-005). The one row comes from the
    migration. The code is never logged.
    """
    session.execute(
        update(InstanceSettings)
        .where(InstanceSettings.id == 1)
        .values(signup_code=code, updated_at=now)
    )


def generate_signup_code() -> str:
    """A random code of 22 URL-safe characters, 128 bits (ADR-007)."""
    return secrets.token_urlsafe(16)


def read_signup_code(session: Session) -> InstanceSettings:
    """The one settings row; the admin sees and shares the code (ADR-007)."""
    return session.get_one(InstanceSettings, 1)
