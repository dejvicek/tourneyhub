---
name: python-style
description: Use when planning, writing, changing or reviewing Python in TourneyHub's backend/ — FastAPI routers and dependencies, Pydantic models or settings, SQLAlchemy models and queries, Alembic migrations, the tourneyhub.engine package, the tourneyhub CLI, logging, openapi.json, pytest or Hypothesis tests, backend/pyproject.toml, or the CI jobs, Dockerfile and Compose services that run backend/ — or when editing docs/style/python-style.md.
---

# TourneyHub Python style

The rules live in `docs/style/python-style.md`. Before writing code, read the sections for what you touch (§3 layers, §4 errors, time and logging, §5 FastAPI, §6 Pydantic, §7 SQLAlchemy, §8 engine, §9 tests, §10 security). Take tool versions and configuration from `backend/pyproject.toml` and `backend/uv.lock`, not from memory; the guide's §2 explains the choices in them that are not obvious. Where it disagrees with `ADR.md`, the ADR wins until it is changed; the guide's §11 lists the changes it proposes.

## Project decisions an agent will not guess

| Topic | This project does |
|---|---|
| Transactions | The request owns them: `SessionDep = Annotated[Session, Depends(get_session, scope="function")]`, where `get_session` uses `session_factory.begin()`. Services never commit. Never write `Depends(get_session)` inline. The login throttle counts the attempt in its own short transaction, listed before `SessionDep`, and answers 429 instead of sleeping. The refresh endpoint returns its reuse 401 instead of raising, so the revocation commits. |
| Layers | `api` and `cli` → `services` → `db` → `engine` (import-linter). Services are `verb_noun(session, *, …)` functions returning loaded rows; routers and dependencies run no queries and import nothing from `db` except `User` in `api/deps.py`; the engine imports nothing outside itself. |
| Errors | Services raise `AppError` subclasses with an `ErrorCode`, e.g. `NotFoundError` (404), `ConflictError` (409: a stale expectation, the frontend reloads), `RuleViolationError` (422: the state refuses the action, the frontend shows a message). Rules an organizer can break are checked under the lock, before a unique index fires. The engine raises `EngineError` subclasses when a rule refuses the input, and `to_app_error()` turns each into a 422; a caller error (a broken precondition, a bug in the caller) is a plain `ValueError`, in the engine and in services. Only `api/` knows HTTP statuses; only `api/errors.py` maps errors to them and catches `IntegrityError`, whose 409s cover only races, such as a retry in flight. No English text in responses. |
| Locks | League row, then tournament row: `.with_for_update()`, plus `.execution_options(populate_existing=True)` when the lock loads ORM objects; a lock that selects columns only needs none. Ids are loaded through the organizer's league. |
| ORM | Relationships use `lazy="raise"`, `back_populates` when both sides declare the relationship, `passive_deletes=True` along `ON DELETE CASCADE`, and `passive_deletes="all"` (or no relationship) along the deferred foreign keys to `players` and `entries`; each query names its loads. `.is_(None)`, never `is None`, in queries. Enum columns use `str_enum()`. |
| App | `create_app(settings)` reads settings eagerly and keeps them and the session factory on `app.state`, read only by `api/deps.py`; nothing is created at import time; `uvicorn --factory`. |
| Logging | `create_app()` and the CLI's `main()` apply `LOGGING_CONFIG` first: JSON lines on stderr (stdout carries the `openapi.json` export), `"disable_existing_loggers": False`, the request-id filter on the handler. The `Exception` handler does not log; uvicorn logs the re-raised exception. |
| Models | `RequestModel` / `ResponseModel` bases in `api/schemas.py`; `LeagueCreate`, `LeagueRead` in the area's router module (`api/tournament_models.py` for a split area); snake_case JSON; validators raise `PydanticCustomError`. |
| Python 3.15 | No `from __future__ import annotations`, no `if TYPE_CHECKING:` imports, no `lazy import`. `uuid.uuid7()`, `datetime.now(UTC)`; "now" comes from `NowDep` and is passed down; `random` is banned. Line length stays 88. |
| Tests | Names cite rule IDs (`test_br056_…`). The schema comes from `alembic upgrade head`; the test session joins an outer transaction and commits in teardown before the invariant queries; the app override wraps each request in `begin_nested()`, and so does a test that expects a database error. Test `Settings` use `env="development", cookie_secure=False`. pytest-alembic's tests use their own database. `httpx2`, not `httpx`. Hypothesis only on the engine. |

## Before you report the work as done

Run the commands of the guide's §2 from `backend/`, never from the repository root: `uv sync --locked`, `ruff format`, `ruff check`, `mypy`, `lint-imports`, the tests with coverage, and the OpenAPI drift check.

If a rule stops you from doing what the task needs, do not work around it. Say which rule, and propose a change to `docs/style/python-style.md`.
