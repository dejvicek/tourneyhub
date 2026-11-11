from enum import StrEnum


class AdminActionSource(StrEnum):
    """Where an admin action came from (DATA-MODEL §4.1, ADR-007)."""

    WEB = "web"
    CLI = "cli"


class AdminActionKind(StrEnum):
    """What an `admin_actions` row records (DATA-MODEL §4.1)."""

    SET_SIGNUP_CODE = "set_signup_code"  # web and cli; setting, changing or clearing
    RESET_PASSWORD = "reset_password"  # noqa: S105 (web; not a password)
    CREATE_ADMIN = "create_admin"  # cli
    GRANT_ADMIN = "grant_admin"  # cli
    REVOKE_ADMIN = "revoke_admin"  # cli
