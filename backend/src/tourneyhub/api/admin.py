from datetime import datetime
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import StringConstraints
from sqlalchemy.orm import Session

from tourneyhub.api.deps import AdminDep, NowDep, SessionDep, get_admin
from tourneyhub.api.schemas import (
    ErrorResponse,
    NewPassword,
    RequestModel,
    ResponseModel,
)
from tourneyhub.engine.admin import AdminActionSource
from tourneyhub.services import admin as admin_service
from tourneyhub.services.instance import (
    SIGNUP_CODE_MAX_LENGTH,
    SIGNUP_CODE_MIN_LENGTH,
)

# The server checks the admin flag on every route of this router, from the user's
# row, never from the token (ADR-007). A route cannot be added without the check.
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_admin)],
    responses={
        HTTPStatus.UNAUTHORIZED: {"model": ErrorResponse},
        HTTPStatus.FORBIDDEN: {"model": ErrorResponse},
    },
)

# A code or a password in a response must not be kept by a cache or the browser.
_NO_STORE = "no-store"


class SignupCodeRead(ResponseModel):
    """The sign-up code, which the admin may see and share; null: sign-up is closed."""

    signup_code: str | None
    updated_at: datetime | None


class SignupCodeUpdate(RequestModel):
    """The new code, or null to close sign-up (FR-005)."""

    signup_code: (
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True,
                min_length=SIGNUP_CODE_MIN_LENGTH,
                max_length=SIGNUP_CODE_MAX_LENGTH,
            ),
        ]
        | None
    )


class OrganizerRead(ResponseModel):
    """An account in the admin's list."""

    id: UUID
    email: str
    display_name: str
    is_admin: bool
    must_change_password: bool
    created_at: datetime


class PasswordReset(RequestModel):
    """A temporary password the admin chose, or null to have one generated."""

    temporary_password: NewPassword | None = None


class PasswordResetRead(ResponseModel):
    """The generated temporary password, shown once; null if the admin chose one."""

    temporary_password: str | None


def _read_code(session: Session, response: Response) -> SignupCodeRead:
    response.headers["Cache-Control"] = _NO_STORE
    settings = admin_service.get_signup_settings(session)
    return SignupCodeRead.model_validate(settings)


@router.get("/signup-code")
def read_signup_code(session: SessionDep, response: Response) -> SignupCodeRead:
    """The current sign-up code, or null while sign-up is closed (FR-005)."""
    return _read_code(session, response)


@router.put("/signup-code")
def set_signup_code(
    admin: AdminDep,
    body: SignupCodeUpdate,
    session: SessionDep,
    now: NowDep,
    response: Response,
) -> SignupCodeRead:
    """Set or change the code, or close sign-up with null (FR-005).

    Existing accounts are not affected. The action is recorded without the code.
    """
    admin_service.set_signup_code(
        session,
        source=AdminActionSource.WEB,
        admin_user_id=admin.id,
        code=body.signup_code,
        now=now,
    )
    return _read_code(session, response)


@router.post("/signup-code/generate")
def generate_signup_code(
    admin: AdminDep, session: SessionDep, now: NowDep, response: Response
) -> SignupCodeRead:
    """Make a random code, store it and return it (FR-005)."""
    admin_service.generate_signup_code(session, admin_user_id=admin.id, now=now)
    return _read_code(session, response)


@router.get("/organizers")
def list_organizers(session: SessionDep, response: Response) -> list[OrganizerRead]:
    """Every account by email, admins included (ADR-007); not cached."""
    response.headers["Cache-Control"] = _NO_STORE
    users = admin_service.list_organizers(session)
    return [OrganizerRead.model_validate(user) for user in users]


@router.post(
    "/organizers/{user_id}/password-reset",
    responses={
        HTTPStatus.NOT_FOUND: {"model": ErrorResponse},
        HTTPStatus.UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    },
)
def reset_password(
    admin: AdminDep,
    user_id: UUID,
    body: PasswordReset,
    session: SessionDep,
    now: NowDep,
    response: Response,
) -> PasswordResetRead:
    """Give an organizer a temporary password (FR-006, ADR-006).

    Every login of the account is revoked and its next login must choose a new
    password. With no `temporary_password` a random one is generated and returned
    once. 422 `own_account` for the admin's own account, 422 `admin_target` for
    another admin's (the CLI handles admins); 404 `user_not_found`.
    """
    response.headers["Cache-Control"] = _NO_STORE
    generated = admin_service.reset_password(
        session,
        admin=admin,
        user_id=user_id,
        temporary_password=(
            None
            if body.temporary_password is None
            else body.temporary_password.get_secret_value()
        ),
        now=now,
    )
    return PasswordResetRead(temporary_password=generated)
