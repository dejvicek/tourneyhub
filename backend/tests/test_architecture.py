"""Rules of docs/style/python-style.md that ruff, mypy and import-linter cannot see.

Each test reads the source with `ast`, or the models through SQLAlchemy's mappers,
and names the guide section a violation breaks.
"""

import ast
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import TypeIs

from sqlalchemy.orm import RelationshipDirection, RelationshipProperty

import tourneyhub.db.models  # noqa: F401  (registers every model on Base)
from tourneyhub.db.base import Base

BACKEND = Path(__file__).parents[1]
SRC = BACKEND / "src" / "tourneyhub"
TESTS = BACKEND / "tests"

# Where the exceptions live, each with the reason it may.
DEPENDENCY_ALIASES = "api/deps.py"  # defines SessionDep, NowDep and the other aliases
ERROR_HANDLERS = "api/errors.py"  # maps IntegrityError to 409 or 500 (§4.4)
CLOCK_READERS = {
    "api/deps.py": "get_now and get_clock behind NowDep",
    "cli.py": "the CLI reads the time once per command",
}
ASYNC_MODULES = {
    "api/errors.py": "exception handlers",
    "app.py": "middleware and the lifespan",
}
APP_STATE_READERS = {
    "api/deps.py": "the dependencies read the settings and the session factory",
    "app.py": "create_app() puts them there",
}
DEFERRED_TARGETS = {"players", "entries"}  # DATA-MODEL §2


def _modules(*packages: str) -> Iterator[tuple[str, ast.Module]]:
    """Each module under the given packages of `src/tourneyhub`, or all of them."""
    roots = [SRC / package for package in packages] or [SRC]
    for root in roots:
        files = [root] if root.suffix == ".py" else sorted(root.rglob("*.py"))
        for path in files:
            yield path.relative_to(SRC).as_posix(), ast.parse(path.read_text())


def _where(module: str, node: ast.expr | ast.stmt | ast.alias) -> str:
    return f"src/tourneyhub/{module}:{node.lineno}"


def _called_name(call: ast.Call) -> str | None:
    match call.func:
        case ast.Attribute(attr=name) | ast.Name(id=name):
            return name
        case _:
            return None


def _fail(rule: str, places: list[str], section: str) -> str:
    return f"{rule}: {', '.join(places)}. Read docs/style/python-style.md {section}."


def test_services_never_commit() -> None:
    """python-style §3: the request or the CLI owns the transaction, not a service."""
    calls = {"commit", "rollback", "begin", "begin_nested"}

    places = [
        _where(module, node)
        for module, tree in _modules("services", "db/models", "engine")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _called_name(node) in calls
    ]

    assert not places, _fail("a transaction is opened or ended", places, "§3, §5")


def test_only_the_api_error_handler_knows_integrity_error() -> None:
    """python-style §4.4: services never catch IntegrityError; api/errors.py maps it."""
    places = [
        _where(module, node)
        for module, tree in _modules()
        if module != ERROR_HANDLERS
        for node in ast.walk(tree)
        if (isinstance(node, ast.Name) and node.id == "IntegrityError")
        or (isinstance(node, ast.Attribute) and node.attr == "IntegrityError")
        or (isinstance(node, ast.alias) and node.name.endswith("IntegrityError"))
    ]

    assert not places, _fail("IntegrityError outside api/errors.py", places, "§4.4")


def _router_wide_dependencies(tree: ast.Module) -> set[ast.AST]:
    """`Depends` calls in `APIRouter(dependencies=[...])`, which guard every route."""
    return {
        inner
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _called_name(node) == "APIRouter"
        for keyword in node.keywords
        if keyword.arg == "dependencies"
        for inner in ast.walk(keyword.value)
    }


def test_endpoints_use_the_dependency_aliases() -> None:
    """python-style §5: dependencies are `Annotated` aliases from api/deps.py.

    `APIRouter(dependencies=[Depends(...)])` may guard every route of a router.
    """
    places = [
        _where(module, node)
        for module, tree in _modules()
        if module != DEPENDENCY_ALIASES
        for router_wide in [_router_wide_dependencies(tree)]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _called_name(node) == "Depends"
        and node not in router_wide
    ]

    assert not places, _fail("an inline Depends(...)", places, "§5")


def _relationships() -> Iterator[RelationshipProperty[object]]:
    for mapper in Base.registry.mappers:
        yield from mapper.relationships


def _relationship_where(relationship: RelationshipProperty[object]) -> str:
    """The `file:line` of the relationship's annotated attribute."""
    cls = relationship.parent.class_
    path = Path(str(sys.modules[cls.__module__].__file__))
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ClassDef) and node.name == cls.__name__:
            for statement in node.body:
                if (
                    isinstance(statement, ast.AnnAssign)
                    and isinstance(statement.target, ast.Name)
                    and statement.target.id == relationship.key
                ):
                    return f"{path.relative_to(BACKEND)}:{statement.lineno}"
    return f"{path.relative_to(BACKEND)} ({relationship})"


def test_relationships_raise_on_lazy_load() -> None:
    """python-style §7: relationships use `lazy="raise"`; each query names its loads."""
    places = [
        _relationship_where(relationship)
        for relationship in _relationships()
        if relationship.lazy != "raise"
    ]

    assert not places, _fail('a relationship without lazy="raise"', places, "§7")


def _expected_passive_deletes(
    relationship: RelationshipProperty[object],
) -> bool | str | None:
    """What the foreign key under a one-to-many relationship asks for, if anything."""
    parent = relationship.parent.local_table
    constraints = [
        key.constraint
        for column in relationship.remote_side
        for key in column.foreign_keys
        if key.column.table is parent and key.constraint is not None
    ]
    if any(constraint.deferrable for constraint in constraints):
        return "all" if parent.description in DEFERRED_TARGETS else None
    if any(constraint.ondelete == "CASCADE" for constraint in constraints):
        return True
    return None


def test_relationships_leave_deletes_to_postgresql() -> None:
    """python-style §7: `passive_deletes=True` along ON DELETE CASCADE, "all" along
    the deferred foreign keys to players and entries."""
    one_to_many = [
        relationship
        for relationship in _relationships()
        if relationship.direction is RelationshipDirection.ONETOMANY
    ]

    places = [
        f"{_relationship_where(relationship)} wants passive_deletes={expected!r}"
        for relationship in one_to_many
        if (expected := _expected_passive_deletes(relationship)) is not None
        and relationship.passive_deletes != expected
    ]

    assert not places, _fail("wrong passive_deletes", places, "§7")


def test_now_is_read_once_per_request() -> None:
    """python-style §4.3: "now" comes from NowDep or the CLI and is passed down."""
    places = [
        _where(module, node)
        for module, tree in _modules()
        if module not in CLOCK_READERS
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "now"
    ]

    assert not places, _fail("a clock read outside NowDep and the CLI", places, "§4.3")


def test_the_engine_makes_no_ids() -> None:
    """python-style §8: the engine is pure; services generate the ids."""
    places = [
        _where(module, node)
        for module, tree in _modules("engine")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _called_name(node) in {"uuid1", "uuid4", "uuid7"}
    ]

    assert not places, _fail("an id generated in the engine", places, "§8")


ENGINE_VALUE_ARGUMENTS = ("frozen", "slots", "kw_only")


def _dataclass_arguments(decorator: ast.expr) -> set[str] | None:
    """The arguments set to True in a `dataclass` decorator, or None for another."""
    match decorator:
        case ast.Name(id="dataclass") | ast.Attribute(attr="dataclass"):
            return set()
        case ast.Call(func=ast.Name(id="dataclass") | ast.Attribute(attr="dataclass")):
            return {
                keyword.arg
                for keyword in decorator.keywords
                if keyword.arg is not None
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
            }
        case _:
            return None


def test_engine_values_are_frozen_slotted_and_keyword_only() -> None:
    """python-style §4.3: engine values are
    `@dataclass(frozen=True, slots=True, kw_only=True)`."""
    places = [
        f"{_where(module, node)} {node.name}"
        for module, tree in _modules("engine")
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        for decorator in node.decorator_list
        if (arguments := _dataclass_arguments(decorator)) is not None
        and not arguments.issuperset(ENGINE_VALUE_ARGUMENTS)
    ]

    assert not places, _fail(
        "a dataclass without frozen, slots and kw_only", places, "§4.3"
    )


def test_hypothesis_only_tests_the_engine() -> None:
    """python-style §9: property tests use Hypothesis on the pure engine only."""
    places = [
        f"{path.relative_to(BACKEND)}:{node.lineno}"
        for path in sorted(TESTS.rglob("*.py"))
        if not path.is_relative_to(TESTS / "engine")
        for node in ast.walk(ast.parse(path.read_text()))
        if (
            isinstance(node, ast.Import)
            and any(alias.name.split(".")[0] == "hypothesis" for alias in node.names)
        )
        or (
            isinstance(node, ast.ImportFrom)
            and (node.module or "").split(".")[0] == "hypothesis"
        )
    ]

    assert not places, _fail("Hypothesis outside tests/engine", places, "§9")


def test_endpoints_and_dependencies_are_sync() -> None:
    """python-style §5: endpoints and dependencies are `def`; FastAPI runs them in
    its thread pool. Only exception handlers and middleware are `async def`."""
    places = [
        _where(module, node)
        for module, tree in _modules()
        if module not in ASYNC_MODULES
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
    ]

    assert not places, _fail("an async def", places, "§5")


def _reads_app_state(node: ast.AST) -> TypeIs[ast.Attribute]:
    """`request.app`, `app.state` or `self.app.state`."""
    match node:
        case ast.Attribute(attr="app"):
            return True
        case ast.Attribute(
            attr="state", value=ast.Name(id="app") | ast.Attribute(attr="app")
        ):
            return True
        case _:
            return False


def test_only_the_dependencies_read_app_state() -> None:
    """python-style §5: only api/deps.py reads `app.state`."""
    places = [
        _where(module, node)
        for module, tree in _modules()
        if module not in APP_STATE_READERS
        for node in ast.walk(tree)
        if _reads_app_state(node)
    ]

    assert not places, _fail("app.state read outside api/deps.py", places, "§5")


def test_only_settings_read_the_environment() -> None:
    """python-style §5: nothing reads environment variables except `Settings`."""
    names = {"environ", "getenv"}

    places = [
        _where(module, node)
        for module, tree in _modules()
        for node in ast.walk(tree)
        if (isinstance(node, ast.Attribute) and node.attr in names)
        or (isinstance(node, ast.alias) and node.name in names)
    ]

    assert not places, _fail("an environment variable read", places, "§5")


def _raised_name(node: ast.Raise) -> str | None:
    match node.exc:
        case ast.Call() as call:
            return _called_name(call)
        case ast.Name(id=name):
            return name
        case _:
            return None


def test_api_validators_raise_pydantic_custom_errors() -> None:
    """python-style §6: a validator raises `PydanticCustomError`, never English text
    in a `ValueError` or `TypeError`."""
    places = [
        _where(module, node)
        for module, tree in _modules("api")
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise)
        and _raised_name(node) in {"ValueError", "TypeError"}
    ]

    assert not places, _fail("a ValueError or TypeError in api/", places, "§6")
