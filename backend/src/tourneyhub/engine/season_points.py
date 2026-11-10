"""Season points from final places (BR-110, BR-111)."""

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from tourneyhub.engine.ids import EntryId, PlayerId, ensure_distinct
from tourneyhub.engine.places import EntryPlace


@dataclass(frozen=True, slots=True, kw_only=True)
class PlayerPoints:
    """The placement points one player earns in a tournament (BR-110).

    Attributes:
        player_id: The player.
        entry_id: The entry the player placed with.
        place: The entry's place (BR-100).
        points: The player's points: the whole entry's, not a share of them.
    """

    player_id: PlayerId
    entry_id: EntryId
    place: int
    points: int


def shared_place_points(*, place: int, entry_count: int, table: Sequence[int]) -> int:
    """Return the points each of `entry_count` entries sharing `place` gets (BR-111).

    The entries cover the places `place` to `place + entry_count - 1`. Each
    gets the average of those places' points in `table`, rounded down. A
    place beyond the table is worth 0 (BR-110). With the default table
    10, 8, 6, 4, 2, two entries sharing 3rd get (6 + 4) / 2 = 5, and four
    sharing 5th get (2 + 0 + 0 + 0) / 4 = 0.5, rounded down to 0.

    `table` is the season's placement points table: whole numbers, none
    negative, none above the place before it (FR-011).

    Raises:
        ValueError: `place` or `entry_count` is less than 1.
    """
    if place < 1 or entry_count < 1:
        msg = f"place {place} and entry count {entry_count} must be at least 1"
        raise ValueError(msg)
    covered = table[place - 1 : place - 1 + entry_count]
    return sum(covered) // entry_count


def season_points(
    places: Iterable[EntryPlace], table: Sequence[int]
) -> tuple[PlayerPoints, ...]:
    """Compute the placement points of every player in a tournament (BR-110, BR-111).

    Every player of an entry gets the entry's points, so a pair's two players
    each get the full amount and nobody splits it (BR-100, BR-111). Entries
    sharing a place get the average of the places they cover, rounded down
    (`shared_place_points`). The tournament's season standings add these up
    (BR-112) and rank players by the total (BR-113); that is not done here.

    Returns:
        One `PlayerPoints` per player, best place first and by player id
        within a place.

    Raises:
        ValueError: A caller bug: an entry or a player is given twice, a place
            is below 1, or the places are not what BR-104 produces: from 1,
            each shared place followed by the one that skips its entries.
    """
    entries = tuple(places)
    ensure_distinct(entry.entry_id for entry in entries)
    ensure_distinct(player_id for entry in entries for player_id in entry.player_ids)
    sharing = Counter(entry.place for entry in entries)
    expected = 1
    for place in sorted(sharing):
        if place != expected:
            msg = f"place {place} follows a gap: expected {expected}"
            raise ValueError(msg)
        expected += sharing[place]

    points = {
        place: shared_place_points(place=place, entry_count=count, table=table)
        for place, count in sharing.items()
    }
    return tuple(
        sorted(
            (
                PlayerPoints(
                    player_id=player_id,
                    entry_id=entry.entry_id,
                    place=entry.place,
                    points=points[entry.place],
                )
                for entry in entries
                for player_id in entry.player_ids
            ),
            key=lambda row: (row.place, row.player_id.int),
        )
    )
