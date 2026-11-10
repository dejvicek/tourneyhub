from enum import StrEnum


class Language(StrEnum):
    """The UI language an account remembers (FR-081, DATA-MODEL §4.1)."""

    EN = "en"
    CS = "cs"
