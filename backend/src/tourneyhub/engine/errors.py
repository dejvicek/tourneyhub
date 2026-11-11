class EngineError(Exception):
    """The base of every rule the engine refuses (ADR-009).

    Each subclass names one refusal and carries its parameters as keyword-only
    fields, such as `NotEnoughEntriesError(minimum=4, given=3)`, never English
    text. Services catch `EngineError` and translate it into a
    `RuleViolationError` whose `detail` carries the same fields
    (docs/python-style.md §4.4).
    """


class QualifierCountError(EngineError):
    """The organizer picked too few or too many knockout qualifiers (BR-080).

    `maximum` is the most that can qualify, the entries that are not disabled;
    it can be below `minimum`, and then no knockout is possible.
    """

    def __init__(self, *, minimum: int, maximum: int, given: int) -> None:
        super().__init__(minimum, maximum, given)
        self.minimum = minimum
        self.maximum = maximum
        self.given = given


class OddQualifierCountError(EngineError):
    """A Monster DYP pair knockout needs an even number of qualifiers (BR-080)."""

    def __init__(self, *, given: int) -> None:
        super().__init__(given)
        self.given = given


class NotEnoughPlayersError(EngineError):
    """A DYP or Monster DYP tournament has fewer players than it needs.

    DYP needs 4 players (BR-031); a Monster DYP round needs 4 players who are
    not disabled (FR-032, BR-063, BR-064).
    """

    def __init__(self, *, minimum: int, given: int) -> None:
        super().__init__(minimum, given)
        self.minimum = minimum
        self.given = given


class DypHalvesUnequalError(EngineError):
    """Hand-set DYP halves differ in size (BR-032)."""

    def __init__(self, *, top: int, bottom: int) -> None:
        super().__init__(top, bottom)
        self.top = top
        self.bottom = bottom


class TooManyLeftOutError(EngineError):
    """Hand-set DYP halves leave out more players than the rule allows (BR-032)."""

    def __init__(self, *, maximum: int, given: int) -> None:
        super().__init__(maximum, given)
        self.maximum = maximum
        self.given = given


class NotEnoughEntriesError(EngineError):
    """Too few entries can play a new round: none would have an opponent (FR-032, FR-044)."""

    def __init__(self, *, minimum: int, given: int) -> None:
        super().__init__(minimum, given)
        self.minimum = minimum
        self.given = given
