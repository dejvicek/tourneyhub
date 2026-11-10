from http import HTTPStatus
from uuid import UUID

from fastapi import APIRouter

from tourneyhub.api.deps import AccountDep, CurrentUserDep, NowDep, SessionDep
from tourneyhub.api.schemas import (
    DisplayName,
    ErrorResponse,
    RequestModel,
    ResponseModel,
)
from tourneyhub.engine.accounts import Language
from tourneyhub.services import accounts as account_service

router = APIRouter(
    prefix="/me",
    tags=["me"],
    responses={HTTPStatus.UNAUTHORIZED: {"model": ErrorResponse}},
)


class UserRead(ResponseModel):
    """The caller's account."""

    id: UUID
    email: str
    display_name: str
    language: Language
    is_admin: bool
    # The frontend opens the new-password screen while this is set (ADR-006).
    must_change_password: bool


class ProfileUpdate(RequestModel):
    """The fields to change; a field left out or null stays as it is."""

    display_name: DisplayName | None = None
    language: Language | None = None


@router.get("")
def read_me(user: AccountDep) -> UserRead:
    """The caller's account; works while a new password is required (ADR-006)."""
    return UserRead.model_validate(user)


@router.patch("", responses={HTTPStatus.FORBIDDEN: {"model": ErrorResponse}})
def update_me(
    user: CurrentUserDep, body: ProfileUpdate, session: SessionDep, now: NowDep
) -> UserRead:
    """Change the display name and the remembered language (FR-081)."""
    updated = account_service.update_profile(
        session,
        user=user,
        display_name=body.display_name,
        language=body.language,
        now=now,
    )
    return UserRead.model_validate(updated)
