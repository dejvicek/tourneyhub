"""The domain values of tournaments and their phases (DATA-MODEL §4.3, §4.4)."""

from enum import StrEnum


class TournamentType(StrEnum):
    """What a tournament plays (FR-030)."""

    SINGLES = "singles"
    DOUBLES = "doubles"
    DYP = "dyp"
    MONSTER_DYP = "monster_dyp"


class TournamentState(StrEnum):
    """Where a tournament is in its life (ADR-009, DATA-MODEL §4.3)."""

    SETUP = "setup"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"


class SeedingMethod(StrEnum):
    """How the first phase is seeded (FR-034, BR-021, BR-022)."""

    RANKING = "ranking"
    RANDOM = "random"


class HalvesMethod(StrEnum):
    """How a DYP tournament's halves are made (FR-033, BR-032)."""

    RANKING = "ranking"
    BY_HAND = "by_hand"


class GroupPhase(StrEnum):
    """The group phase chosen in setup, or none (FR-031).

    Monster DYP always plays `monster_dyp`, and the other types never do.
    """

    ROUND_ROBIN = "round_robin"
    SWISS = "swiss"
    MONSTER_DYP = "monster_dyp"
    NONE = "none"


class PhaseKind(StrEnum):
    """A phase is a group phase or a knockout (DATA-MODEL §4.3, D9)."""

    GROUP = "group"
    KNOCKOUT = "knockout"


class PhaseFormat(StrEnum):
    """How a phase is played: one of the group formats, or the knockout's."""

    ROUND_ROBIN = "round_robin"
    SWISS = "swiss"
    MONSTER_DYP = "monster_dyp"
    SINGLE_ELIMINATION = "single_elimination"


class MatchFormat(StrEnum):
    """Best of how many games a match is (BR-120); BO2 only in group phases (BR-121)."""

    BO1 = "bo1"
    BO2 = "bo2"
    BO3 = "bo3"
    BO5 = "bo5"


class KnockoutMatchFormat(StrEnum):
    """A match format a knockout and its final can play: never BO2 (BR-121)."""

    BO1 = "bo1"
    BO3 = "bo3"
    BO5 = "bo5"


class Tiebreaker(StrEnum):
    """A tie-breaker of a Swiss or Monster DYP phase (FR-043, BR-073)."""

    SCORE_DIFFERENCE = "score_difference"
    BH1 = "bh1"
    BH2 = "bh2"


DEFAULT_TIEBREAKERS: tuple[Tiebreaker, ...] = (
    Tiebreaker.BH1,
    Tiebreaker.BH2,
    Tiebreaker.SCORE_DIFFERENCE,
)
"""The tie-breakers of a new Swiss or Monster DYP phase, in order (FR-043)."""


class MatchOutcome(StrEnum):
    """A match's result: a side won, or a draw (DATA-MODEL `matches.outcome`, D11)."""

    SIDE_1 = "side_1"
    SIDE_2 = "side_2"
    DRAW = "draw"


class MonsterKnockoutMode(StrEnum):
    """How the knockout after Monster DYP rounds is formed (FR-045, BR-081 to BR-084)."""

    SEEDED_PAIRS = "seeded_pairs"
    SINGLES = "singles"
    A_LITTLE_MERCY = "a_little_mercy"
    LORD_HAVE_MERCY = "lord_have_mercy"


class EntryStage(StrEnum):
    """Which phase an entry plays: the first (`main`) or a later knockout (D4)."""

    MAIN = "main"
    KNOCKOUT = "knockout"


class EntryKind(StrEnum):
    """An entry is one player or a pair (glossary "Entry", BR-030)."""

    PLAYER = "player"
    PAIR = "pair"


class MatchKind(StrEnum):
    """A bracket has one third-place match; every other match is standard (BR-044)."""

    STANDARD = "standard"
    THIRD_PLACE = "third_place"


class Outcome(StrEnum):
    """A match's result, or a game's winner: one side, or a draw (BR-090, D11)."""

    SIDE_1 = "side_1"
    SIDE_2 = "side_2"
    DRAW = "draw"


class Participation(StrEnum):
    """Why an entry did or did not play a group-phase round (D5, BR-064, BR-067)."""

    PLAYED = "played"
    SAT_OUT = "sat_out"
    DISABLED = "disabled"
    NOT_JOINED = "not_joined"


DEFAULT_SIT_OUT_POINTS = 0
"""The default points for sitting out in Swiss and Monster DYP (FR-039).

The organizer picks 0, 1 or 2 in setup (BR-075); a round robin has none (BR-071).
"""


def group_phase_format(choice: GroupPhase) -> PhaseFormat | None:
    """Return the group phase's format for a setup choice; None without one (FR-031)."""
    return None if choice is GroupPhase.NONE else PhaseFormat(choice.value)


def entry_kind(tournament_type: TournamentType) -> EntryKind:
    """Return the kind of a tournament's main entries (BR-030).

    Singles and Monster DYP enter players; Monster DYP forms its teams per round
    (D2). Doubles and DYP enter pairs.
    """
    if tournament_type in {TournamentType.DOUBLES, TournamentType.DYP}:
        return EntryKind.PAIR
    return EntryKind.PLAYER


def is_seeded(tournament_type: TournamentType) -> bool:
    """Whether setup seeds the first phase (FR-034); Monster DYP has no seeds."""
    return tournament_type is not TournamentType.MONSTER_DYP
