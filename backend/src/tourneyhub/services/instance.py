import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import InstanceSettings

# The code is typed by organizers on a phone and guessed by strangers: not too
# short. The maximum is what the sign-up request accepts.
SIGNUP_CODE_MIN_LENGTH = 12
SIGNUP_CODE_MAX_LENGTH = 256


def set_signup_code(session: Session, *, code: str | None, now: datetime) -> bool:
    """Set the sign-up code, or close sign-up with None (ADR-007).

    Existing accounts are not affected (FR-005). The one row comes from the
    migration and is locked, so that two changes at once are told apart. Returns
    False and changes nothing, `updated_at` included, when the code already has
    that value. The code is never logged.
    """
    settings = session.scalars(
        select(InstanceSettings)
        .where(InstanceSettings.id == 1)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if settings.signup_code == code:
        return False
    settings.signup_code = code
    settings.updated_at = now
    session.flush()
    return True


def generate_signup_code() -> str:
    """A random code of 22 URL-safe characters, 128 bits (ADR-007)."""
    return secrets.token_urlsafe(16)


def read_signup_code(session: Session) -> InstanceSettings:
    """The one settings row; the admin sees and shares the code (ADR-007)."""
    return session.get_one(InstanceSettings, 1)
