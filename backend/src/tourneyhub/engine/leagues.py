from enum import StrEnum


class LeagueStatus(StrEnum):
    """Where a league is in its life (DATA-MODEL §4.2)."""

    ACTIVE = "active"
    ARCHIVED = "archived"


_TRANSITIONS = frozenset(
    {
        (LeagueStatus.ACTIVE, LeagueStatus.ARCHIVED),
        (LeagueStatus.ARCHIVED, LeagueStatus.ACTIVE),
    }
)


def can_transition(current: LeagueStatus, target: LeagueStatus) -> bool:
    """Tell whether a league may move from `current` to `target`.

    An active league can be archived and an archived one restored; staying in
    the same status is not a transition (DATA-MODEL §4.2).
    """
    return (current, target) in _TRANSITIONS
