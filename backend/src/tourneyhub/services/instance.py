from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import InstanceSettings


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
