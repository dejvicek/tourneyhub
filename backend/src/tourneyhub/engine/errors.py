from uuid import UUID


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
    """Too few entries to start a tournament or play a new round (FR-032, FR-044)."""

    def __init__(self, *, minimum: int, given: int) -> None:
        super().__init__(minimum, given)
        self.minimum = minimum
        self.given = given


class GameScoreMismatchError(EngineError):
    """A game has one score without the other, or its winner lost on score (BR-092)."""

    def __init__(self, *, game_no: int) -> None:
        super().__init__(game_no)
        self.game_no = game_no


class ScoresRequiredError(EngineError):
    """A game of a Swiss or Monster DYP round has no score (BR-092)."""

    def __init__(self, *, game_no: int) -> None:
        super().__init__(game_no)
        self.game_no = game_no


class DrawNotAllowedError(EngineError):
    """A draw in a knockout, or in a league without draws (BR-090)."""


class ResultDoesNotFitFormatError(EngineError):
    """The games do not make a result in the match's format (BR-121).

    Too few or too many games, a drawn game where only BO1 can draw, a game
    after the series is decided, or a series nobody won.
    """

    def __init__(self, *, match_format: str, games: int) -> None:
        super().__init__(match_format, games)
        self.match_format = match_format
        self.games = games


class PlayerOnAnotherFieldError(EngineError):
    """A placement by hand would put a player on two fields at once (BR-131).

    `player_ids` are the players, `field_ids` every field that would hold
    them, lowest number first.
    """

    def __init__(
        self, *, player_ids: tuple[UUID, ...], field_ids: tuple[UUID, ...]
    ) -> None:
        super().__init__(player_ids, field_ids)
        self.player_ids = player_ids
        self.field_ids = field_ids
