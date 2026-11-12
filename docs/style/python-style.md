# Python Style Guide

| | |
|---|---|
| Status | Accepted |
| Date | 2026-11-03, revised 2026-11-05 after review and after the backend skeleton |
| Scope | All Python in `backend/`: the `tourneyhub` package, its tests and its migrations. It applies to people and to AI agents; the Claude Code skill `.claude/skills/python-style` points here. |

The ADRs decide what the backend is built from; this guide decides how its code is written. Where the two disagree, the ADR wins until it is changed; §11 lists the changes this guide proposes. Requirement IDs (FR-, BR-) refer to `PRD.md`.

## 1. Principles

- **The tools are the rulebook.** What ruff, mypy, import-linter and pytest check is configured in `backend/pyproject.toml` (§2). Prose mentions a tool-checked rule only to name its code; every other rule written here exists because no tool checks it.
- **Python 3.15 only.** No compatibility code for older versions, no `typing_extensions` for what the standard library has, no `from __future__ import annotations`.
- **Typed throughout.** `mypy --strict` passes on `src` and `tests`. No `Any` of our own; where a library's signature forces it (`type_annotation_map`, a decoded JWT payload), a comment says so. mypy's `disallow_any_explicit` checks this, except in `tourneyhub.db.base` and in `tests/conftest.py`, `tests/api`, `tests/db` and `tests/services`, whose factory fixtures are `Callable[..., X]` (§9). A `cast` or `# type: ignore[code]` carries a comment saying why it is safe.
- **One way per task.** Use the patterns this guide shows. A second way to do the same thing (another session helper, another base model) needs a reason in the pull request.
- **Business rules are cited.** Code and tests that implement a rule name its ID (`BR-056`, `FR-082`) in a docstring, comment or test name.
- **Changing a rule** is a pull request that changes this guide and the configuration together.

## 2. Toolchain

The configuration CI runs is [`backend/pyproject.toml`](../../backend/pyproject.toml). It gives lower bounds only; the exact versions live in `backend/uv.lock`.

| Tool | Role |
|---|---|
| uv | Python, environments, lock file |
| ruff | Lint and format, default line length of 88 |
| mypy | Type check, strict, with the Pydantic plugin |
| import-linter | Layer and purity contracts (§3) |
| pytest, Hypothesis, coverage | Tests (§9) |

Run every command from `backend/`, where the configuration lives. Since ruff 0.16, `ruff format` also formats Python blocks inside Markdown, so run from the repository root it would also reformat the samples in this guide with default settings.

```sh
uv sync --locked                      # exactly what uv.lock says
uv run ruff format && uv run ruff check --fix
uv run mypy
uv run lint-imports
uv run coverage run -m pytest && uv run coverage report
uv run coverage report --include="*/tourneyhub/engine/*" --fail-under=100
uv run python -W error -m tourneyhub.openapi > openapi.json && git diff --exit-code openapi.json
```

CI (`.github/workflows/ci.yml`) runs the same commands, with `uv run ruff format --check && uv run ruff check` in place of the two that change files, then `alembic upgrade head` and `alembic check` (§7) and `uv audit`.

`uv.lock` and `.python-version` (containing `3.15`) are committed. Dependabot (`package-ecosystem: "uv"`) and `uv audit --preview-features audit-command` (still a preview command) watch them. The engine gate runs from the start, since the skeleton has engine code. The gate for the whole package (90 %, ADR-012) is switched on with the first feature; until then `[tool.coverage.report]` has no `fail_under`.

Choices in the configuration that are not obvious:
- `required-version = ">=0.13.6"`: 0.13.6 is the first uv release that ships CPython 3.15.2.
- Three lower bounds carry a fix the guide relies on: `alembic>=1.20.1` (duplicate CHECKs with SQLAlchemy 2.1), `fastapi>=0.162` (`Depends(scope="function")` needs 0.121 or later, §5) and `sqlalchemy>=2.1.7` (a leaked pool slot on Python 3.15, #13738).
- `uvloop` is listed directly: `uvicorn[standard]` pulls PyYAML, which has no 3.15 wheel.
- `[build-system]` uses `uv_build`: the `tourneyhub` entry point (ADR-007) needs a build system.
- `select` names rule families instead of `ALL`, so a ruff upgrade does not switch on new rules unannounced.
- `TC` (imports only for type checking) stays off. Pydantic, FastAPI, SQLAlchemy and Hypothesis read annotations at runtime, and moving their imports under `if TYPE_CHECKING:` breaks them.
- `ban-lazy = "all"`: no PEP 810 lazy imports (§4.2).
- `random` is banned everywhere: lots use the stored seed (ADR-010), everything else uses `secrets`.
- mypy uses only the Pydantic plugin; SQLAlchemy 2.1 needs none. `explicit_package_bases = true` lets test modules with one file name coexist, such as `tests/api/test_leagues.py` and `tests/services/test_leagues.py`.
- import-linter's `include_external_packages = true` is needed to forbid third-party and standard-library modules in the engine contract. That contract forbids `tourneyhub.*`, which leaves out the engine itself.
- The contract "Routers and dependencies run no queries (§3)" sets `allow_indirect_imports = true`, because `api` → `services` → `db` is the normal path, and ignores one import, `tourneyhub.api.deps -> tourneyhub.db.models.accounts`: `CurrentUserDep` and `AdminDep` are typed with the `User` row (§5). import-linter reports an ignore that matches no import as an error, so the entry goes when that import goes.
- Alembic has no `alembic.ini`; `env.py` reads the database URL from `Settings`. `script_location = "tourneyhub:migrations"` is a package path, and the image runs `tourneyhub migrate` (§7), since the wheel ships no `pyproject.toml`.

## 3. Layout and layers

```text
backend/
├── pyproject.toml, uv.lock, .python-version
├── openapi.json          # exported by tourneyhub.openapi, committed, checked for drift (ADR-008)
├── src/tourneyhub/
│   ├── __init__.py       # empty
│   ├── app.py            # create_app()
│   ├── openapi.py        # prints the OpenAPI schema (§5)
│   ├── settings.py       # Settings
│   ├── errors.py         # ErrorCode and the AppError hierarchy
│   ├── logging_config.py # the dictConfig dictionary and the request-id filter (§4.6)
│   ├── cli.py            # the `tourneyhub` command: admin (ADR-007) and `migrate` (§7)
│   ├── api/              # one router module per area, plus:
│   │   ├── deps.py       #   the dependency aliases (§5)
│   │   ├── errors.py     #   the exception handlers (§5)
│   │   └── schemas.py    #   RequestModel, ResponseModel, ErrorResponse, shared type aliases (§6)
│   ├── services/         # use cases: locks, checks, engine calls
│   ├── db/               # Base, engine and session factory, models/ by DATA-MODEL §4 area
│   ├── engine/           # pure tournament rules (ADR-009)
│   └── migrations/       # Alembic, inside the package so the image ships it
└── tests/                # mirrors src/tourneyhub/
```

Every package and module above exists, empty where nothing lives in it yet: import-linter fails on a missing layer.

Layers, enforced by import-linter: `api` and `cli` → `services` → `db` → `engine`. A module imports from layers below it, never from above. `errors.py` and `settings.py` import nothing else from `tourneyhub`.

- **`engine`** imports nothing from the rest of `tourneyhub`, no framework and no source of time or chance (§2). It also holds the domain `StrEnum`s, so that `db` and `api` can use them.
- **`services`** are module-level functions in `services/<area>.py`, named verb first (`create_league`, `generate_round`). A service takes `session: Session` first, then keyword-only arguments: plain values, never request models, and `now: datetime` when it needs the time. It takes the locks and checks the expected state (§7), calls the engine and raises `AppError`s. It returns ORM rows or engine values with everything the response will read already loaded; a `lazy="raise"` error in a router is a bug in the service. Services never import FastAPI, never commit and never build response models. import-linter keeps `fastapi`, `starlette` and `http` out of `services`, `db`, `cli`, `errors` and `settings`, and `tests/test_architecture.py` checks that services, models and the engine never commit, roll back or begin a transaction.
- **`api`** turns requests into service calls and service results into response models. Routers and dependencies run no queries of their own; `CurrentUserDep`, for example, calls a service. import-linter keeps `tourneyhub.db` out of `api`, except the `User` model that `api/deps.py` needs as the type of `CurrentUserDep` and `AdminDep` (§2). It cannot keep out SQLAlchemy, which `api` needs for `Session` and `IntegrityError`, so a query that does not use the models, such as one through `text()`, is left to review.
- **`db/models/`** has one module per DATA-MODEL §4 area (`accounts`, `leagues`, `tournaments`, `entries`, `matches`); `db/models/__init__.py` imports them all, so Alembic sees the whole schema.
- One module per area in `api/` and `services/`: `api/leagues.py` calls `services/leagues.py`.

## 4. Python

### 4.1 Naming

- PEP 8, checked by ruff `N`. Names use the PRD's English terms: entry, seed, sit-out, bye, round, BH1, DYP. Column and JSON names follow DATA-MODEL §4 (`round_no`, `rng_seed`); any other abbreviation needs a reason in the pull request.
- Booleans read as statements: `is_admin`, `has_bye`, `must_change_password`. Collections are plural nouns (`entries`, not `entry_list`).
- Durations are `timedelta`, never a bare number of seconds.
- `_leading_underscore` for module internals. `__all__` only in an `__init__.py` that re-exports.

### 4.2 Types

- Annotate every function, including tests and fixtures (`-> None`).
- Write `X | None` and builtin generics, and import ABCs from `collections.abc`. Parameters take the widest type that works (`Iterable`, `Sequence`, `Mapping`); return values are concrete (`tuple`, `list`, `dict`).
- Use PEP 695 generics and `type` aliases: `def first[T](items: Sequence[T]) -> T`, `type Standing = tuple[RankedEntry, ...]`. Exception: FastAPI dependency aliases are plain assignments (`SessionDep = Annotated[...]`), so that all of them have one form.
- `Self`, `@override`, `Never`, `assert_never`, `TypeIs`, `ReadOnly` and `warnings.deprecated` come from the standard library.
- Use `NewType` for ids where two kinds of id meet in one signature, such as `EntryId` and `PlayerId` in the engine. A `NewType` used in a mapped column is registered in `type_annotation_map`. For one that is not, SQLAlchemy 2.1 raises `sqlalchemy.orm.exc.MappedAnnotationError` ("Could not locate SQLAlchemy Core type") when the model class is defined.
- Use `Protocol` for an interface with several implementations, and an ABC only to share implementation. `isinstance` on a protocol needs `@runtime_checkable`.
- Import for real every name used in an annotation that a library reads at runtime: Pydantic models, FastAPI signatures, SQLAlchemy models, dataclasses, Hypothesis strategies. `if TYPE_CHECKING:` is not used; an import cycle is fixed by moving code.
- No `lazy import` (PEP 810). A missing module should stop the app at startup, not fail the first request that needs it.
- Newer syntax is welcome: forward references without quotes (3.14), `except A, B:` without parentheses, which `ruff format` writes (3.14), `frozendict` and `sentinel()` (3.15). Not used: template strings (`t"…"`), since queries go through SQLAlchemy, and `TypedDict(extra_items=...)`, which mypy does not support yet.

### 4.3 Values

- Engine values are `@dataclass(frozen=True, slots=True, kw_only=True)` with `tuple`, `frozenset` or `frozendict` fields; `tests/test_architecture.py` checks the three arguments. Change them with `dataclasses.replace`.
- Closed sets of values are `StrEnum`s; the database stores their values (§7).
- `match` over enums and unions is exhaustive, through mypy's `exhaustive-match` or a final `case _: assert_never(value)`. Plain conditions use `if`.
- Instants are aware UTC datetimes: `datetime.now(UTC)`, never `utcnow()` (ruff `DTZ`).
- "Now" is read once per request and passed down. The API gets it from `NowDep` (§5), the CLI calls `datetime.now(UTC)` once per command, and services and the engine take `now: datetime` as an argument. Everything a rule compares against uses that value: the refresh token's 60-second window and 90-day expiry (ADR-006), and `auth_attempts.created_at`, which the abuse limits count in a time window (DATA-MODEL §4.1). So do every `created_at` and `updated_at` (DATA-MODEL §2): one clock keeps `updated_at` from falling before `created_at`, and a test that overrides `get_now` (§9) fixes both. `tests/test_architecture.py` checks that only `api/deps.py` and `cli.py` call `.now()`.
- Server-generated ids come from `uuid.uuid7()`.
- Where `None` is a valid value and "not given" must be told apart, use a `sentinel()`; in Pydantic models, `model_fields_set`.
- Flags and options are keyword-only parameters (`*, include_removed: bool = False`), checked by ruff `FBT`.

### 4.4 Errors

`tourneyhub/errors.py` defines `ErrorCode`, a `StrEnum` of every stable code, and `AppError`:

```python
class AppError(Exception):
    """An error the API reports as {"code": ..., "detail": ...} (ADR-008)."""

    def __init__(self, code: ErrorCode, **detail: JsonValue) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail
```

The subclass decides the HTTP status, and the code tells the frontend what happened. `api/errors.py` maps the subclasses in one table; services and the engine never mention HTTP.

| Subclass | Status | Raised when |
|---|---|---|
| `NotAuthenticatedError` | 401 | No valid access token |
| `ForbiddenError` | 403 | Not allowed, e.g. `password_change_required` (ADR-006) |
| `NotFoundError` | 404 | Unknown id, or one from another organizer's league |
| `ConflictError` | 409 | The request carried an expectation that is stale, and a reload repairs it: an expected value, a target state, a client id of another row (ADR-008) |
| `RuleViolationError` | 422 | The current state refuses the action, and the organizer needs a message: a taken player name (BR-001), too few entries |

- `ErrorCode` also holds the codes for framework errors: `validation_failed` (422), `not_found` and `method_not_allowed` (the router's 404 and 405), `bad_request` (any other HTTP error) and `internal_error` (500).
- The engine raises its own exceptions, defined in `engine/errors.py` as subclasses of `EngineError` with keyword-only fields (`NotEnoughEntriesError(minimum=4, given=3)`). One function, `services/engine_errors.py:to_app_error()`, translates each into a `RuleViolationError` whose `detail` carries the same fields; services call engine functions inside `except EngineError as err: raise to_app_error(err) from err`.
- 409 makes the frontend reload, and the reloaded screen shows what changed (ADR-008); a stale `expected_round_no` is 409. 422 makes it show a message built from the code and `detail`, because a reload would change nothing; a player name the league already has is 422.
- Services check the rules an organizer can break under the lock, before a unique index would fire. Adding a player locks the league and looks the name up with `lower()` (BR-001): any player of that name, a removed one included, is 422 `player_name_taken`, and the organizer restores a removed holder by a separate request (FR-012, DATA-MODEL §4.2). A create with a client id first loads the row with that id and answers as ADR-008 says; only then are its rules checked, so a retry gets its row back instead of a 422 that its own first attempt caused.
- Services never catch `IntegrityError`; where a race is expected, the query avoids it (`on_conflict_do_nothing`). A violation surfaces at the next flush, at the latest at the commit in `get_session`; either way it reaches the handler uncaught. A handler in `api/errors.py` turns one from a constraint listed in its table, recognized by `err.orig.diag.constraint_name`, into that constraint's 409 code. The table lists only constraints that a race can reach, because no lock covers their check: creating a league has no league row to lock (§7), so `pk_leagues` is listed. Any other violation, including a deferred foreign key or a unique index that a service checks under its lock, is a bug and becomes 500 `internal_error` with the constraint name logged (DATA-MODEL §2). `tests/test_architecture.py` checks that no module but `api/errors.py` names `IntegrityError`.
- Inside `except`, write `raise NewError(...) from err`. Use `from None` only when the cause tells a reader of the log nothing.
- Catch the narrowest exception. The only catch-all is the API's handler for unexpected errors, which answers `internal_error`.
- Log an unexpected exception once: `logger.exception(...)` inside `except` (ruff `TRY400`), and `logger.error(..., exc_info=exc)` in the `IntegrityError` handler, which receives the exception as an argument (ruff `LOG004`). The `Exception` handler logs nothing and only answers `internal_error`: Starlette re-raises the exception after that response, and uvicorn logs it with its traceback and the request id (§4.6).
- `assert` only in tests. Use `assert_never` for exhaustiveness.

### 4.5 Docstrings and comments

- Docstrings are Google style (`convention = "google"`) without types, which the annotations already give.
- Every public function and class in the engine has one, citing the business rules it implements. Elsewhere, write one when the name and types leave something out: a rule ID, a non-obvious reason, a lock order.
- Docstrings of endpoints and Pydantic models end up in `openapi.json` and in the frontend's generated types, so write them for the frontend developer.
- Comments say why, not what. No commented-out code (ruff `ERA`).

### 4.6 Logging

- Each module has `logger = logging.getLogger(__name__)`. `tourneyhub/logging_config.py` holds one `dictConfig` dictionary: JSON lines on stderr through python-json-logger's `JsonFormatter`, for the root logger and for the `uvicorn`, `uvicorn.error` and `uvicorn.access` loggers. `create_app()` applies it first, as does the CLI's `main()` (§7). In the app it replaces uvicorn's own configuration, so uvicorn needs no `--log-config` file.

```python
request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    """Add the current request id to every record; `None` outside a request."""

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


LOGGING_CONFIG: dict[str, object] = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": RequestIdFilter}},
    "formatters": {"json": {"()": "pythonjsonlogger.json.JsonFormatter"}},
    "handlers": {
        "stderr": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["request_id"],
            "stream": "ext://sys.stderr",
        },
    },
    "root": {"level": "INFO", "handlers": ["stderr"]},
    "loggers": {
        name: {"level": "INFO", "handlers": ["stderr"], "propagate": False}
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
    },
}
```

  - Without `"disable_existing_loggers": False`, `dictConfig` disables every logger that already exists. Modules create their loggers at import, before `create_app()` runs, so no `tourneyhub.*` logger would emit anything. A test pins this (§9).
  - Logs go to stderr because stdout carries the schema that `python -m tourneyhub.openapi` prints (§5).
  - The filter sits on the handler. A filter on a logger sees only the records logged on that logger, not those of the `tourneyhub.*` modules or of uvicorn.
- Pass values as arguments, not f-strings: `logger.info("round generated", extra={"tournament_id": str(tournament_id)})` (ruff `G`, `LOG`).
- Never log passwords, tokens, cookies, the `Authorization` header, request bodies, the sign-up code or email addresses. Log user ids instead.
- A middleware sets a new request id in `request_id` at the start of every request, and the filter adds it to every record. The middleware does not reset it: Starlette's `ServerErrorMiddleware`, which wraps every other middleware, answers an unhandled exception, and uvicorn logs it (§4.4), both after the middleware has returned. Each request runs in its own asyncio task with its own copy of the context.
- No `print` outside `cli.py` and `openapi.py` (ruff `T20`).

## 5. FastAPI

- `create_app(settings: Settings | None = None) -> FastAPI` builds the application. It reads the settings eagerly, so a missing or invalid variable stops startup (ADR-001). It creates the database engine and the session factory, keeps them and the settings on `app.state`, installs the error handlers and includes the routers under `/api/v1`. uvicorn runs `--factory tourneyhub.app:create_app`. No module creates an app, an engine or settings at import time.
- Only the dependencies in `api/deps.py` read `app.state`; nothing reads environment variables except `Settings`. `tests/test_architecture.py` checks both.
- Use `lifespan`, never `on_event`. The lifespan disposes of the database engine.
- One `APIRouter` per area, with a `prefix` and `tags`.
- Every endpoint and dependency is `def`; FastAPI runs them in its thread pool. Exception handlers and middleware are `async def` and never block. `tests/test_architecture.py` allows `async def` only in `api/errors.py` and `app.py`.
- Dependencies are `Annotated` aliases defined once in `api/deps.py`: `SessionDep`, `SettingsDep`, `NowDep` (`get_now`, which returns `datetime.now(UTC)`), `CurrentUserDep`, `AccountDep`, `AccessClaimsDep`, `AdminDep`, `LoginThrottleDep`, `SignUpThrottleDep`, `PasswordChangeThrottleDep`, `CustomHeaderDep`. Endpoints use the aliases, never an inline `Depends(...)`. The one exception is a router-wide guard, `APIRouter(dependencies=[Depends(get_admin)])` in `api/admin.py` (below). `tests/test_architecture.py` checks this.
- **The request owns the transaction:**

```python
def get_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory.begin() as session:  # commits, or rolls back on an exception
        yield session


# scope="function" runs the commit before the response is sent.
SessionDep = Annotated[Session, Depends(get_session, scope="function")]
```

  - With the default scope, the code after `yield` runs after the response has been sent, so a commit could fail after the client received a 2xx. With `scope="function"`, a failing commit reaches the error handlers, and an `AppError` raised in the endpoint rolls back before its error response goes out.
  - Use `get_session` only through `SessionDep`. A plain `Depends(get_session)` in the same request opens a second session.
  - The CLI and the auth dependencies (below) open their own transaction with `with session_factory.begin() as session:` around one service call. The dependencies take the factory from `SessionFactoryDep`.
  - A write that must survive an error response cannot be followed by a raised error, because `SessionDep` rolls back. Either it commits in a short transaction of its own before the request's work starts, as `throttle_login` counts a login attempt, or the endpoint returns the error response instead of raising, built with `error_response()` from `api/errors.py`. Only the refresh endpoint does the latter: it revokes a reused token's family under the locks it already holds and returns 401 (ADR-001, ADR-006).
  - Integration tests pin this: a commit that fails returns 500 `internal_error`, and one that fails on a known unique constraint returns its 409 code.
- `CurrentUserDep` loads the user row on every request, gives it to the endpoint as a `User`, and raises `ForbiddenError(ErrorCode.PASSWORD_CHANGE_REQUIRED)` while `must_change_password` is set. The password change and `GET /api/v1/me` use `AccountDep`, the same row without that check (ADR-006); `AccessClaimsDep` gives the password change the token's family, which stays logged in. `AdminDep` reads `is_admin` from the same row (ADR-007). Missing tokens are handled with `HTTPBearer(auto_error=False)` and our own `NotAuthenticatedError`, so they get an ADR-008 code instead of FastAPI's English `detail`.
- The admin router (`api/admin.py`, ADR-007) declares `dependencies=[Depends(get_admin)]` on the `APIRouter`, so a route added to it cannot forget the admin check, which reads `is_admin` from the user's row. A route that needs the admin's id also takes `AdminDep`; FastAPI resolves the dependency once. A test walks the OpenAPI paths and expects 403 `forbidden` for an organizer on every `/admin` route. Responses that hold a code or a password carry `Cache-Control: no-store`. A reset locks the target's row `FOR NO KEY UPDATE`, as a password change does, so a login that verified the old password meanwhile is refused.
- Every admin action inserts its `admin_actions` row through `services/admin.py:record_action`, in the same transaction, from the service that does the action, for the web and the CLI alike. The CLI's admin commands (`create-admin`, `grant-admin`, `revoke-admin`, `set-signup-code`) read secrets with `getpass`, never from an argument, and print no secret except the code that `set-signup-code --generate` makes.
- The login throttle (ADR-006) never sleeps: an attempt inside the waiting period gets 429 `too_many_attempts` with `Retry-After`, and a burst of logins holds neither threads nor connections. `throttle_login` counts the attempt before the password is checked, in a short transaction of its own: per email and per client IP, under transaction-level advisory locks, it counts the failures and inserts the attempt as a failure, so parallel attempts count each other, and the row stays when the login rolls back with its 401. A successful `log_in` marks the attempt as succeeded in its own transaction. `log_in` lists it first: `def log_in(attempt: LoginThrottleDep, body: LoginRequest, session: SessionDep, …)`.

```python
def throttle_login(
    session_factory: SessionFactoryDep,
    body: LoginRequest,
    client_ip: ClientIpDep,
    now: NowDep,
) -> auth_service.Attempt:
    with session_factory.begin() as session:  # commits the attempt at once
        return auth_service.start_login_attempt(
            session, email=body.email, ip=client_ip, now=now
        )


LoginThrottleDep = Annotated[auth_service.Attempt, Depends(throttle_login)]
```

  - FastAPI resolves dependencies in the order of the signature. `SessionDep`'s session takes a connection only at its first query, so the throttle comes before any dependency that queries through `SessionDep`.
  - The email key is folded with PostgreSQL's `lower()`, as the login's lookup folds it. An IPv6 client is counted per /64; an IPv4-mapped address counts as its IPv4 address.
- `SignUpThrottleDep` is the same for sign-up (`start_signup_attempt`, kind `signup_ip`, per client IP). It takes the request body as a parameter, so that a body that fails validation is refused before it is counted. Sign-up has its own limits, as the guessing of a code is not slowed by Argon2: 5 free failures in an hour, then a doubling waiting period up to 15 minutes. `tourneyhub cleanup` deletes attempts older than the longest window.
  - `PasswordChangeThrottleDep` counts a password change on the login's budget (`login_email` of the token's user, `login_ip`), since checking the current password is a password guess. `log_in` re-reads the user's hash `FOR NO KEY UPDATE` after verifying, so that a login racing a password change cannot keep the old password.
  - Both throttles read the body, and so does the route, so a validation error is reported by each. The validation handler lists an error once.
- Every id in a path or body is loaded through the current organizer's league, under its lock when writing (ADR-008). Another organizer's id is then simply not found (OWASP API1).
- The return annotation is the response model. Routers return Pydantic models built from service results (`LeagueRead.model_validate(league)`), never dicts or ORM objects.
- Status codes go on the decorator, as `http.HTTPStatus` members: `@router.post("", status_code=HTTPStatus.CREATED)`.
- Operation ids are the endpoint function names: `FastAPI(generate_unique_id_function=lambda route: route.name)`. Endpoint names are therefore unique across the app.
- Each `APIRouter(...)` passes `responses=` with `ErrorResponse` for the error statuses all its routes share; a route adds only its own. The app declares 422 with `ErrorResponse`, which keeps FastAPI's `HTTPValidationError` out of the schema (ADR-008). `ErrorResponse` lives in `api/schemas.py`.
- `api/errors.py` has handlers for `AppError`, `RequestValidationError`, `starlette.exceptions.HTTPException` (which covers the router's 404 and 405), `IntegrityError` and `Exception` (ADR-008). The validation handler puts one entry per error in `detail.errors`: its `loc`, its `type` and the numeric `ctx` keys (`min_length`, `max_length`, `ge`, `expected_version`, …). It drops `msg`, `url`, `input` and the other `ctx` keys, since `input` can contain a password and the rest is English text, which can quote the input. A league with a 101-character name and an `is_admin` field gets:

```json
{
  "code": "validation_failed",
  "detail": {
    "errors": [
      {"loc": ["body", "name"], "type": "string_too_long", "max_length": 100},
      {"loc": ["body", "is_admin"], "type": "extra_forbidden"}
    ]
  }
}
```

  - `loc` starts with where the value was: `body`, `path`, `query`, `header` or `cookie`. Malformed JSON gives `{"loc": ["body", 7], "type": "json_invalid"}`, where 7 is the character position.
  - `type` is a Pydantic error type or a `PydanticCustomError` type (§6); the frontend translates it.
- `python -m tourneyhub.openapi` prints the schema: it builds the app with placeholder settings (the schema does not depend on them, and creating the database engine does not connect) and prints `json.dumps(app.openapi(), indent=2, sort_keys=True)`. CI runs it with `-W error`, which turns a duplicate operation id into a failure, and compares the result with the committed `openapi.json` (§2). Only the schema goes to stdout; a record logged while the app is built goes to stderr (§4.6).
- `cli.py` uses `argparse` and reads passwords and the sign-up code with `getpass`, never from an argument or an environment variable, and never prints them back. `tourneyhub set-signup-code [--clear]` sets or clears the code, `tourneyhub cleanup` deletes expired and revoked refresh tokens and old `auth_attempts`; a schedule for it is P15. It builds its session factory with the same `db` helpers as `create_app()`. Admin services take `source` (`web` or `cli`) and `admin_user_id: UUID | None` and write `admin_actions` themselves, so actions from the web and the CLI are recorded in one place (ADR-007). `create-admin` checks the display name with `services.accounts.clean_display_name`, the rules the API's `DisplayName` uses, since the CLI may not import `api`. An action that changes nothing records nothing.

## 6. Pydantic and settings

```python
class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)


type LeagueName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class LeagueCreate(RequestModel):
    """A new league; `id` is generated by the client (ADR-008)."""

    id: UUID7
    name: LeagueName
```

- Request models extend `RequestModel`. `extra="forbid"` rejects unknown fields, so a client cannot slip in `is_admin` (OWASP API3). Response models extend `ResponseModel`.
- One model per operation and direction: `LeagueCreate`, `LeagueUpdate`, `LeagueRead`. Class names and `type` aliases become TypeScript type names, so they are unique across the app.
- Operations that are unsafe to repeat carry the expected state as required fields (`expected_round_no`, `expected_draw_counter`) or send the full target state (ADR-008).
- JSON field names are the Python names, in snake_case, with no aliases.
- Put constraints in the type (`StringConstraints`, `Field(ge=0)`) rather than in validators. They appear in OpenAPI and produce stable error types. Every string and list in a request has a maximum length (OWASP API4).
- Don't set `strict=True` or `str_strip_whitespace=True` on a whole model. Strict mode rejects the UUID and date strings that JSON carries, and stripping would change passwords.
- A custom validator raises `PydanticCustomError("stable_type", "message", {...})`, never `ValueError("English text")`, so the error type is a code the frontend can translate. `tests/test_architecture.py` checks that nothing in `api/` raises `ValueError` or `TypeError`.
- Client-supplied ids are `UUID7`, instants are `AwareDatetime`, passwords are `SecretStr`.
- Per-format phase options are a discriminated union on `format` (DATA-MODEL §4.3): `Annotated[RoundRobinOptions | SwissOptions | MonsterDypOptions | KnockoutOptions, Field(discriminator="format")]`.
- Only the v2 API: `model_validate`, `model_dump`, `model_copy`, `ConfigDict`, `field_validator`.
- `X | None` without a default is required but may be `null`. Add `= None` when the field may be left out.

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TOURNEYHUB_", frozen=True)

    env: Literal["development", "production"]
    database_url: SecretStr
    jwt_secret: Annotated[SecretStr, Field(min_length=32)]  # HS256 needs 32 bytes
    cookie_secure: bool = True
```

- `RequestModel`, `ResponseModel`, `ErrorResponse` and the shared `type` aliases live in `api/schemas.py`; the models of one area live in its router module. A model that a dependency reads, such as `LoginRequest`, also lives in `api/schemas.py`: the router module imports `api/deps.py`, so `api/deps.py` cannot import from it.
- A setting without a safe default has no default. Constraints that would otherwise fail later fail at startup instead, like the length of `jwt_secret`. pydantic-settings does not report a misspelled variable, so a default would hide the mistake.
- Rules between settings are `model_validator`s on `Settings`: `cookie_secure=False` is refused unless `env == "development"` (ADR-004).
- Secrets are `SecretStr`, read with `.get_secret_value()` only where they are used.
- No `env_file` in code; Compose and `.env` supply the environment (ADR-004). Tests pass their own `Settings(...)` to `create_app()`.

## 7. SQLAlchemy and Alembic

```python
class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
    # Any: the keys are Python types of every kind, the values any SQL type.
    type_annotation_map: ClassVar[dict[Any, TypeEngine[Any]]] = {
        datetime: DateTime(timezone=True)
    }


def str_enum[E: StrEnum](enum: type[E], *, name: str) -> Enum:
    """A varchar column without a length and a named CHECK of the enum's values."""
    return Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=None,  # undocumented; a test pins the varchar without a length
        values_callable=lambda members: [member.value for member in members],
    )
```

- Models are typed declarative: `Mapped[...]` and `mapped_column()` on a plain `DeclarativeBase`, not `MappedAsDataclass`.
- The naming convention is required: Alembic can compare and drop only named constraints. CHECK constraints get an explicit `name=`.
- Enumerations use `str_enum()`. Without `native_enum=False` SQLAlchemy creates a PostgreSQL enum, without `values_callable` it stores member names, and each column needs its own `name`. Alembic does not notice a value added to an enum, so a test compares every CHECK with its `StrEnum` (DATA-MODEL §2). SQLAlchemy does not document `length=None`, and Alembic does not compare a length with no length, so a second test expects every enum column to be `character varying` without a maximum length in `information_schema.columns`.
- Server-generated primary keys are `mapped_column(primary_key=True, default=uuid7)`. Ids the client supplies (leagues, tournaments, ADR-008) have no default.
- `created_at` and `updated_at` have no default; the service sets both to the `now` it was given (§4.3), and a row without `created_at` fails at the flush. With `server_default=func.now()`, `created_at` would come from the database's clock at the start of the transaction, after `NowDep` has read the time.
- Relationships are `Mapped[list[X]]` or `Mapped[X]` with `back_populates` and `lazy="raise"`. Each query names what it loads: `selectinload` for collections, `joinedload` for many-to-one.
- A relationship along an `ON DELETE CASCADE` foreign key sets `passive_deletes=True`, so deleting a league or a tournament leaves the cascade to PostgreSQL. Without it, the ORM loads the children and sets their foreign keys to `NULL`, which fails.
- A relationship from `players` or `entries` to the rows that reference them through a deferred foreign key (DATA-MODEL §2) sets `passive_deletes="all"` or does not exist, so the ORM never sets those references to `NULL`. Removing a player sets `removed_at`; the application deletes `players` rows only with their league.
- `tests/test_architecture.py` inspects the mappers and checks `lazy="raise"` and both `passive_deletes` rules.
- Queries are 2.0 style: `session.scalars(select(...))`, `session.execute(...)`, `session.get(...)`, `insert(...).returning(...)`. No `session.query()`.
- In query expressions, compare with `.is_(None)`, `.is_not(None)` and `.is_(True)`, or use the boolean column itself. `column is None` silently becomes `WHERE false`; don't apply ruff's unsafe fixes for E711 and E712 inside queries.
- Raw SQL only through `text()` with `:name` parameters.
- A write locks the league row, then the tournament row (ADR-008), always with `populate_existing`:

```python
league = session.scalars(
    select(League)
    .where(League.id == league_id, League.owner_user_id == user_id)
    .with_for_update()
    .execution_options(populate_existing=True)
).one_or_none()
```

  - Without `populate_existing`, a row already in the session gets `FOR UPDATE` but keeps its old attributes, and the expected-state check compares stale data.
  - A lock query that joins other tables uses `with_for_update(of=Model)`. Never combine `FOR UPDATE` with `joinedload`; PostgreSQL refuses it on the nullable side of an outer join.
  - The refresh endpoint locks a token family's rows the same way before reading them (ADR-006).
  - Creating a league has no league row to lock, and no ADR names another lock, so its checks run unlocked. Two requests that race with one id meet at the primary key, and the later one gets 409 (§4.4).
  - A write to a tournament locks its league first and loads the tournament through that league (§5):

```python
# Wrong: the tournament first, by its id alone. Another organizer's id is found,
# two writers can lock in opposite orders, and a row already in the session
# keeps its old attributes.
tournament = session.get(Tournament, tournament_id, with_for_update=True)
league = lock_league(session, league_id=league_id, user_id=user_id)

# Right: the league, then a tournament of that league, both read fresh.
league = lock_league(session, league_id=league_id, user_id=user_id)
tournament = session.scalars(
    select(Tournament)
    .join(Season, Tournament.season_id == Season.id)
    .where(Tournament.id == tournament_id, Season.league_id == league.id)
    .with_for_update(of=Tournament)
    .execution_options(populate_existing=True)
).one_or_none()
```
- SQLAlchemy 2.1 flushes before every statement, `text()` included. Use `with session.no_autoflush:` while an intermediate state must not reach the database.
- The engine is `create_engine("postgresql+psycopg://…", pool_pre_ping=True)`. Keep the pool defaults (5 + 10 connections) until a measurement shows FastAPI's 40 worker threads waiting for them. Nothing sleeps; the login throttle answers 429 instead of waiting (§5).
- ORM objects stay in the session that loaded them: never hand them to another session or a cache, and never use a session or its objects from two threads concurrently. One after the other is fine: FastAPI runs a request's dependencies, endpoint and commit on whichever threads of its pool are free, and the test client of §9 hands the test's session to them. A lock test (§9) that uses threads gives each its own session.
- Use `with` blocks for every session and connection.

**Migrations**
- Alembic lives in `src/tourneyhub/migrations/`, configured in `[tool.alembic]` (§2); its post-write hooks run ruff on new files. There is no `alembic.ini`, and `env.py` leaves logging to the app:

```python
def _run_migrations(engine: Engine) -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,  # imported from tourneyhub.db.models
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


# Tests and pytest-alembic pass an Engine under "connection"; otherwise Settings decide.
_given: Engine | None = context.config.attributes.get("connection")
if _given is not None:
    _run_migrations(_given)
else:
    _engine = create_db_engine(Settings())
    try:
        _run_migrations(_engine)
    finally:
        _engine.dispose()
```
- The wheel ships `migrations/` but not `pyproject.toml`, so in the image `alembic upgrade head` stops with "No 'script_location' key found in configuration". The `api` container runs `tourneyhub migrate` before uvicorn instead (ADR-004, ADR-014). It builds the configuration in code, and `env.py` takes the database from `Settings`:

```python
def migrate() -> None:
    """Run `alembic upgrade head` from the installed package (ADR-014)."""
    config = Config()  # the image has no pyproject.toml
    config.set_main_option("script_location", "tourneyhub:migrations")
    command.upgrade(config, "head")
```

  - A test in `tests/migrations/` runs `main(["migrate"])` on the migration tests' empty database (§9) and compares its revision with the head that `[tool.alembic]` finds, so the two configurations cannot drift apart.
  - `main()` applies the logging configuration of §4.6 first, as `create_app()` does; otherwise the container log shows no `Running upgrade` line.
- One linear history.
- Autogenerate is a draft. Read every generated migration. It misses changes to a partial index's `WHERE`, to a CHECK expression and to enum values, and it turns a rename into a drop and an add.
- Data migrations use `op.execute()` or `sa.table()` stubs, never the app's models. The models will change, but the migration must not. A row a data migration inserts supplies its own `created_at`, which has no default.
- Every migration has a working `downgrade()`. A migration that cannot be undone raises `NotImplementedError` in `downgrade()`, says why, and becomes the `minimum_downgrade_revision` in the `alembic_config` fixture of `tests/migrations/`; otherwise pytest-alembic's up-and-down test fails on it.
- CI runs `alembic upgrade head` and `alembic check`, plus pytest-alembic's tests (`test_single_head_revision`, `test_upgrade`, `test_up_down_consistency`, `test_model_definitions_match_ddl`). Their `alembic_engine` fixture uses a database of their own (§9) and disposes of its engine.

## 8. Engine

- The engine is pure functions over values: no I/O, no clock, no randomness except the seed (ADR-009, ADR-010). import-linter keeps out the frameworks and `random`, `secrets`, `time` and `os`. `tests/test_architecture.py` catches a call to `.now()` or `uuid.uuid7()` inside the engine.
- Services build its inputs from ORM rows; its outputs are engine dataclasses. ORM and Pydantic objects never reach the engine.
- One function in `engine/lots.py` implements ADR-010: `sha256(seed + purpose.encode() + candidate.bytes)` with a 16-byte seed. A test pins one digest, because changing the encoding would reorder the lots of every stored tournament.
- Results never depend on the iteration order of a set or dict of strings (Python randomizes string hashing per process). Sort explicitly.

```python
# Wrong: the set's order changes from process to process, so the same
# tournament gets other pairs after a restart.
def pair_names(names: Iterable[str]) -> tuple[tuple[str, str], ...]:
    ordered = tuple(set(names))
    return tuple(zip(ordered[::2], ordered[1::2], strict=True))


# Right: sort first; the pairs depend only on the input.
def pair_names(names: Iterable[str]) -> tuple[tuple[str, str], ...]:
    ordered = tuple(sorted(set(names)))
    return tuple(zip(ordered[::2], ordered[1::2], strict=True))
```

## 9. Tests

- `tests/` mirrors the package, e.g. `tests/engine/test_standings.py`. Shared helpers are fixtures in `conftest.py`; under `--import-mode=importlib`, test modules cannot import each other, so factory fixtures are typed `Callable[..., League]` in tests.
- A test name states the rule: `test_br056_pairs_the_next_unplayed_entry_below`.
- The PRD's worked examples (§5.1 and those inside BR-054, BR-055, BR-058, BR-061, BR-063, BR-081, BR-111) are exact test vectors (ADR-012). §5.2 holds for every seed: top players are not exempt from the sit-out lot: the sit-outs are chosen first, and the top players come from the players who play, the marked ones first and then the others in league-ranking order (BR-061, BR-063; ADR-011).
- One behaviour per test, with arrange, act and assert separated by blank lines. Parametrize with ids: `pytest.param(..., id="BR-104-shared-places")`.
- Check domain errors by code: `with pytest.raises(ConflictError) as raised:` and then `assert raised.value.code is ErrorCode.SEASON_NUMBER_CHANGED`. Never match English messages.
- Fixtures that need teardown use `yield`; the others `return` (ruff `PT022`). Broad scopes only for expensive, immutable things such as the migrated database.
- Test data comes from factory fixtures named `make_<noun>`. Each returns a function with keyword-only arguments and unique defaults that adds the row, flushes and returns it: `make_league(name="Thursday DYP")`. The row's `created_at`, and `updated_at` where a service would set it, come from the `now` fixture (§4.3).
- Property tests use Hypothesis on the pure engine only, never together with function-scoped database fixtures. `tests/test_architecture.py` allows `hypothesis` imports only under `tests/engine/`.
  - Build inputs with `st.builds` or `@composite`.
  - A failure Hypothesis finds becomes an `@example(...)`; `@reproduce_failure` is never committed (ruff `TID251`).
  - CI uses Hypothesis's built-in `ci` profile (derandomized, no deadline), selected by the `CI` variable; don't redefine it.
  - Pairing tests cap the field at about 32 entries and set `@settings(deadline=None)` (ADR-011).
- Integration tests use PostgreSQL 17 created with the builtin locale (DATA-MODEL §2). A session-scoped `settings` fixture reads its URL from `TOURNEYHUB_TEST_DATABASE_URL` and passes `env="development", cookie_secure=False`: the test client talks to `http://testserver`, and a client never sends a `Secure` cookie back over plain HTTP. A session-scoped `engine` fixture creates the engine, puts it in `config.attributes["connection"]` of `Config(toml_file=...)` and runs `command.upgrade(config, "head")` once. Each test then runs in a transaction that is rolled back:

```python
@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        event.listen(session, "before_commit", _check_deferred_constraints)
        try:
            yield session
            if session.is_active:
                session.commit()  # runs the deferred checks on what the test left
            else:
                session.rollback()  # a flush failed; back to the last commit
            assert_invariants(session)  # the queries of DATA-MODEL §5
        finally:
            session.close()
            transaction.rollback()


def _check_deferred_constraints(session: Session) -> None:
    """Run the deferred checks that a real commit would run (DATA-MODEL §2)."""
    session.flush()
    session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    session.execute(text("SET CONSTRAINTS ALL DEFERRED"))


@pytest.fixture
def client(settings: Settings, session: Session) -> Iterator[TestClient]:
    app = create_app(settings)

    def test_session() -> Iterator[Session]:
        with session.begin_nested():  # a failing request undoes only its own changes
            yield session
        session.commit()  # releases the test's savepoint and runs the deferred checks

    def test_session_factory() -> sessionmaker[Session]:
        # The auth dependencies' own transactions become savepoints of the test's.
        return sessionmaker(
            bind=session.get_bind(), join_transaction_mode="create_savepoint"
        )

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[get_session_factory] = test_session_factory
    with TestClient(app) as client:  # the context manager runs the lifespan
        yield client
```

  - Without `begin_nested()`, a request that ends in 409 would also roll back the data the test set up, which in production would already be committed.
  - The teardown commits what the test left, as the end of a request would: the deferred foreign keys are checked, and the invariant queries see the test's rows. A rollback would discard every row a service test flushed. Only a session whose flush failed (`is_active` is false) is rolled back, to its last commit.
  - A test that provokes a database error does so inside `with session.begin_nested():`, like the `client` override. Outside a savepoint the failed statement aborts the transaction, and the commit in teardown fails.
  - `assert_invariants` grows with the tables that DATA-MODEL §5's queries need.
  - A test of a 500 response creates its client with `raise_server_exceptions=False`; otherwise the test client raises the error instead of returning the response. The test sees no log record of the error; uvicorn writes it (§4.4).
  - The `client` fixture also overrides `get_session_factory`, with a `sessionmaker` bound to the test's connection with `join_transaction_mode="create_savepoint"`. The auth dependencies' own transactions (§5) then become savepoints of the test's transaction: they see the test's rows, and the rollback at the end removes what they wrote. The waiting period is tested through `start_login_attempt` and through the login route; the races between parallel attempts are lock tests (below).
  - `httpx2` is installed; Starlette's test client warns about plain `httpx`, and the warning fails the run.
- pytest-alembic's tests (§7) run on a database of their own, from `TOURNEYHUB_TEST_MIGRATIONS_DATABASE_URL`, emptied before each test. On the database the `engine` fixture migrated, `test_upgrade` would start at head and run nothing, and `test_up_down_consistency` would drop and rebuild the schema the other tests share, so one broken downgrade would fail unrelated tests in some orders:

```python
@pytest.fixture
def alembic_engine() -> Iterator[Engine]:
    """A database of their own, emptied first, so each test starts from base."""
    engine = create_engine(os.environ["TOURNEYHUB_TEST_MIGRATIONS_DATABASE_URL"])
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    yield engine
    engine.dispose()
```

  - CI creates the second database in the same PostgreSQL service, so it gets the builtin locale as well.
- Lock tests (ADR-006, ADR-008) cannot run inside one rolled-back transaction. They commit on two connections, end with `TRUNCATE … CASCADE` and carry the `concurrency` marker.
- Every route that takes an id is tested with another organizer's id (expect 404), and every admin route as a non-admin (expect 403) (OWASP API1, API5).
- Tests override `get_now`, the function behind `NowDep`, with a fixed time instead of patching the clock.
- `create_app()` and the CLI's `main()` bind the log handler to the `sys.stderr` of that moment. Under `capsys` or `capfd`, that is a stream pytest closes after the test, and later records end in `--- Logging error ---`. A test that uses those fixtures, or reads the log, calls either inside `redirect_stderr(io.StringIO())`. `tests/test_logging_config.py` pins §4.6:

```python
def test_a_module_logger_emits_a_json_line(settings: Settings) -> None:
    with redirect_stderr(io.StringIO()) as stderr:
        create_app(settings)  # binds the log handler to this stream

    logger.error("probe", extra={"league_id": "L1"})  # tourneyhub.api.errors.logger

    line = json.loads(stderr.getvalue().splitlines()[-1])
    assert line["message"] == "probe"
    assert line["league_id"] == "L1"
```
- pytest-randomly shuffles the test order. A test that fails only in some orders has a shared-state bug.

## 10. Security

- Passwords: argon2-cffi `PasswordHasher()` with its defaults (RFC 9106's low-memory profile). Call `check_needs_rehash` after a successful login (ADR-006). An unknown email, and an account whose hash is not an Argon2 hash, is verified against a dummy hash, so the response time does not reveal which accounts exist. The rehash is a conditional `UPDATE … WHERE id = :id AND password_hash = :old`, so it never overwrites a password changed meanwhile.
- Every Argon2 hash and verification (login, password change, the `check_needs_rehash` rehash, the dummy hash for an unknown email) runs under one process-wide `threading.BoundedSemaphore(4)`, so at most 4 hashes of 64 MiB run at once, however many of FastAPI's 40 threads are logging in (ADR-006). A login waits for the semaphore inside its transaction and holds its connection; the wait lasts only while the hashes ahead of it run.
- Access tokens with PyJWT; the algorithm list is fixed in code, never read from the token:

```python
# Refuses HS256 keys shorter than 32 bytes.
_jwt = jwt.PyJWT(options={"enforce_minimum_key_length": True})


def read_access_token(token: str, *, key: SecretStr, now: datetime) -> AccessClaims:
    try:
        payload = _jwt.decode(
            token,
            key.get_secret_value(),
            algorithms=["HS256"],
            # fid: the refresh-token family (ADR-006)
            options={
                "require": ["exp", "iat", "sub", "fid"],
                "verify_exp": False,  # compared with `now` below
                "verify_iat": False,
            },
        )
        claims = AccessClaims(
            user_id=UUID(payload["sub"]), family_id=UUID(str(payload["fid"]))
        )
        expires_at = int(payload["exp"])
    except jwt.InvalidTokenError, ValueError, TypeError:
        raise NotAuthenticatedError(ErrorCode.NOT_AUTHENTICATED) from None
    if expires_at <= now.timestamp():
        raise NotAuthenticatedError(ErrorCode.TOKEN_EXPIRED)
    return claims
```

  - PyJWT checks `exp` and `iat` against the system clock and takes no other time. The expiry is compared with the `now` from `NowDep` instead (§4.3), so tests that fix the clock can issue and expire tokens.

- Refresh tokens are `secrets.token_urlsafe(32)`, stored only as `hashlib.sha256(token.encode()).digest()` in `token_hash` (ADR-006). Share tokens are at least `secrets.token_urlsafe(16)` and are stored as they are, because the organizer must be able to see the link again (DATA-MODEL §4.2).
- Secrets compared in Python (the sign-up code) use `hmac.compare_digest` on UTF-8 bytes; on `str` it raises `TypeError` for a Czech letter (DATA-MODEL §4.1).
- No `pickle`, `eval`, `exec`, `yaml.load` or `subprocess` with `shell=True` (ruff `S`).

## 11. Proposed changes to other documents

The Status column records the decisions of the review of 2026-11-04. Accepted rows move into their documents in follow-up pull requests and then leave this table.

| Document | Today | Proposal | Why | Status |
|---|---|---|---|---|
| ADR-014 | — | Decide `psycopg[binary]` or `psycopg[c]` for production | psycopg's documentation recommends `[c]` for production | Deferred to the deployment phase |

## 12. Sources

- Python: https://docs.python.org/3.15/whatsnew/3.15.html, https://docs.python.org/3/whatsnew/3.14.html, PEPs 649 and 749 (annotations), 661 (`sentinel`), 758 (`except`), 790 (3.15 schedule), 810 (lazy imports), 814 (`frozendict`)
- Typing: https://typing.python.org/en/latest/reference/best_practices.html
- Tools: https://docs.astral.sh/uv/, https://docs.astral.sh/ruff/, https://mypy.readthedocs.io/, https://import-linter.readthedocs.io/
- uv releases with CPython 3.15 (0.13.0, 0.13.6): https://github.com/astral-sh/uv/blob/main/CHANGELOG.md
- FastAPI dependencies with `yield` and their scope (0.118.0, 0.121.0): https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/, https://fastapi.tiangolo.com/release-notes/
- SQLAlchemy 2.1: https://docs.sqlalchemy.org/en/21/changelog/migration_21.html; the mypy plugin's removal in 2.1.0b1 (#12293) and the 2.1.7 pool fix for Python 3.15 (#13738) in https://docs.sqlalchemy.org/en/21/changelog/changelog_21.html; release dates in https://pypi.org/project/SQLAlchemy/#history; `NewType` in `type_annotation_map`: https://docs.sqlalchemy.org/en/21/orm/declarative_tables.html#support-for-type-alias-types-defined-by-pep-695-and-newtype; one thread at a time: https://docs.sqlalchemy.org/en/21/orm/session_basics.html#is-the-session-thread-safe-is-asyncsession-safe-to-share-in-concurrent-tasks; https://docs.sqlalchemy.org/en/21/orm/queryguide/api.html#populate-existing, https://docs.sqlalchemy.org/en/21/orm/session_transaction.html
- Alembic: https://alembic.sqlalchemy.org/en/latest/naming.html, https://alembic.sqlalchemy.org/en/latest/autogenerate.html, the 1.20.1 CHECK fix (#1884) in https://alembic.sqlalchemy.org/en/latest/changelog.html, a `Config` built in code: https://alembic.sqlalchemy.org/en/latest/api/config.html
- Logging: https://docs.python.org/3.15/library/logging.config.html (`disable_existing_loggers`), https://docs.python.org/3.15/library/logging.html#filter-objects, Starlette's `ServerErrorMiddleware`, which re-raises so that the server logs: https://github.com/Kludex/starlette/blob/main/starlette/middleware/errors.py
- Security: RFC 9106, RFC 8725, OWASP Password Storage, Authentication and Logging Cheat Sheets, OWASP API Security Top 10 (2023), NIST SP 800-63B-4 §3.1.1.2: https://pages.nist.gov/800-63-4/sp800-63b.html
