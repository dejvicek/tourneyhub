from http import HTTPStatus
from uuid import UUID

from fastapi import APIRouter

from tourneyhub.api.deps import LoginThrottleDep, SessionDep
from tourneyhub.api.schemas import ErrorResponse, LoginRequest, ResponseModel
from tourneyhub.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginResult(ResponseModel):
    """The account that logged in."""

    user_id: UUID


@router.post("/login", responses={HTTPStatus.UNAUTHORIZED: {"model": ErrorResponse}})
def log_in(
    _throttle: LoginThrottleDep, body: LoginRequest, session: SessionDep
) -> LoginResult:
    """Log in. Repeated failures make the answer slower; nothing is locked."""
    user = auth_service.log_in(session, email=body.email)
    return LoginResult(user_id=user.id)
