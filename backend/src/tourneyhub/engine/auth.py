from enum import StrEnum


class AuthAttemptKind(StrEnum):
    """What an `auth_attempts` row counts (DATA-MODEL §4.1)."""

    LOGIN_EMAIL = "login_email"
    LOGIN_IP = "login_ip"
    SIGNUP_IP = "signup_ip"
