class EngineError(Exception):
    """The base of every rule the engine refuses (ADR-009).

    Each subclass names one refusal and carries its parameters as keyword-only
    fields, such as `NotEnoughEntriesError(minimum=4, given=3)`, never English
    text. Services catch `EngineError` and translate it into a
    `RuleViolationError` whose `detail` carries the same fields
    (docs/python-style.md §4.4).
    """
