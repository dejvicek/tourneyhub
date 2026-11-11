from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    SecretStr,
    StringConstraints,
)
from pydantic_core import PydanticCustomError

from tourneyhub.engine.accounts import Language
from tourneyhub.engine.leagues import first_increase
from tourneyhub.errors import ErrorCode
from tourneyhub.services.accounts import (
    DISPLAY_NAME_MAX_LENGTH,
    EMAIL_MAX_LENGTH,
    EMAIL_PATTERN,
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    collapse_whitespace,
    compose_unicode,
    has_invisible_characters,
)
from tourneyhub.services.instance import SIGNUP_CODE_MAX_LENGTH

# The largest value of a PostgreSQL int column (DATA-MODEL §2: scores and points).
INT_MAX = 2_147_483_647


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)


type LeagueName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=DISPLAY_NAME_MAX_LENGTH,
    ),
]

type SeasonName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=DISPLAY_NAME_MAX_LENGTH,
    ),
]


def _check_non_increasing(points: list[int]) -> list[int]:
    index = first_increase(points)
    if index is not None:
        raise PydanticCustomError(
            "placement_points_increase",
            "place {place} is worth more than the place above it",
            {"place": index + 1},
        )
    return points


# FR-011, the rule of the database's placement_points_valid(): not empty, whole
# numbers, none negative, none worth more than the place above. At most 256
# places: the most entries a tournament is sized for (ADR-009).
type PlacementPoints = Annotated[
    list[Annotated[int, Field(ge=0, le=INT_MAX)]],
    Field(min_length=1, max_length=256),
    AfterValidator(_check_non_increasing),
]


type NewPassword = Annotated[
    SecretStr,
    StringConstraints(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH),
]


def _normalise_unicode(value: object) -> object:
    """Compose a string to NFC before strip and the length check.

    "Čeněk" typed as C + combining caron is then the same name as the composed
    one, and the same length (BR-001).
    """
    return compose_unicode(value) if isinstance(value, str) else value


def _reject_look_alikes(name: str) -> str:
    """Refuse characters that make two names look alike, and tidy the spaces.

    The rules are the service's, shared with the CLI's `create-admin`.
    """
    if has_invisible_characters(name):
        raise PydanticCustomError(
            "invisible_characters", "the name contains invisible characters"
        )
    return collapse_whitespace(name)


type DisplayName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=DISPLAY_NAME_MAX_LENGTH,
    ),
    AfterValidator(_reject_look_alikes),
    BeforeValidator(_normalise_unicode),
]
# A player's name looks like a person's: the same limits, the same NFC form and the
# same refusals, so that no two names look alike (BR-001).
type PlayerName = DisplayName
type Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, max_length=EMAIL_MAX_LENGTH, pattern=EMAIL_PATTERN
    ),
]


class LoginRequest(RequestModel):
    """An email and a password; `throttle_login` reads it too (ADR-006)."""

    email: Annotated[str, StringConstraints(max_length=320)]
    password: Annotated[SecretStr, StringConstraints(max_length=1024)]


class SignUpRequest(RequestModel):
    """A new account and the instance's sign-up code (FR-001); the throttle reads it."""

    signup_code: Annotated[
        SecretStr, StringConstraints(max_length=SIGNUP_CODE_MAX_LENGTH)
    ]
    email: Email
    display_name: DisplayName
    password: NewPassword
    language: Language = Language.EN


class ErrorResponse(ResponseModel):
    """The body of every error response (ADR-008)."""

    code: ErrorCode
    detail: dict[str, JsonValue]
