from collections.abc import Iterable
from typing import NewType
from uuid import UUID

PlayerId = NewType("PlayerId", UUID)
"""A league player's stable id (DATA-MODEL §4.2)."""

EntryId = NewType("EntryId", UUID)
"""A tournament entry's stable id: one player or one pair (DATA-MODEL §4.4)."""


def ensure_distinct(ids: Iterable[UUID]) -> None:
    """Refuse an id given twice: a caller bug, never an organizer's (ADR-009).

    Raises:
        ValueError: An id appears more than once.
    """
    seen: set[UUID] = set()
    for id_ in ids:
        if id_ in seen:
            msg = f"{id_} is given twice"
            raise ValueError(msg)
        seen.add(id_)
