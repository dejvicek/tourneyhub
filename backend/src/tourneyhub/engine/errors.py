class EngineError(Exception):
    """The base of every rule the engine refuses (ADR-009).

    Each subclass names one refusal and carries its parameters as keyword-only
    fields, such as `NotEnoughEntriesError(minimum=4, given=3)`, never English
    text. Services catch `EngineError` and translate it into a
    `RuleViolationError` whose `detail` carries the same fields
    (docs/python-style.md §4.4).
    """


class NotEnoughPlayersError(EngineError):
    """A DYP tournament has fewer players than it needs (BR-031)."""

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
