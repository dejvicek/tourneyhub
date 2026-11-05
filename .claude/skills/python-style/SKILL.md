---
name: python-style
description: Use when planning, writing, changing or reviewing Python in TourneyHub's backend/ — FastAPI routers and dependencies, Pydantic models or settings, SQLAlchemy models and queries, Alembic migrations, the tourneyhub.engine package, the tourneyhub CLI, logging, openapi.json, pytest or Hypothesis tests, backend/pyproject.toml, or the CI jobs, Dockerfile and Compose services that run backend/ — or when editing docs/python-style.md.
---

# TourneyHub Python style

The rules live in `docs/python-style.md`. Before writing code, read the sections for what you touch (§3 layers, §4 errors, time and logging, §5 FastAPI, §6 Pydantic, §7 SQLAlchemy, §8 engine, §9 tests, §10 security). Take tool versions and configuration from its §2, not from memory. Where it disagrees with `ADR.md`, its §11 lists the change it proposes.

## Project decisions an agent will not guess

| Topic | This project does |
|---|---|
| Transactions | The request owns them: `SessionDep = Annotated[Session, Depends(get_session, scope="function")]`, where `get_session` uses `session_factory.begin()`. Services never commit. Never write `Depends(get_session)` inline. |
| Layers | `api` and `cli` → `services` → `db` → `engine` (import-linter). Services are `verb_noun(session, *, …)` functions returning loaded rows; routers and dependencies run no queries; the engine imports nothing outside itself. |
| Errors | Services raise `AppError` subclasses (`NotFoundError`, `ConflictError`, …) with an `ErrorCode`. Only `api/` knows HTTP statuses; only `api/errors.py` maps errors to them and catches `IntegrityError`. No English text in responses. |
| Locks | League row, then tournament row: `.with_for_update()` plus `.execution_options(populate_existing=True)`. Ids are loaded through the organizer's league. |
| ORM | Relationships use `lazy="raise"`, and `passive_deletes=True` along `ON DELETE CASCADE`; each query names its loads. `.is_(None)`, never `is None`, in queries. Enum columns use `str_enum()`. |
| App | `create_app(settings)` reads settings eagerly and keeps them and the session factory on `app.state`, read only by `api/deps.py`; nothing is created at import time; `uvicorn --factory`. |
| Models | `RequestModel` / `ResponseModel` bases in `api/schemas.py`; `LeagueCreate`, `LeagueRead` in the area's router module; snake_case JSON; validators raise `PydanticCustomError`. |
| Python 3.15 | No `from __future__ import annotations`, no `if TYPE_CHECKING:` imports, no `lazy import`. `uuid.uuid7()`, `datetime.now(UTC)`; "now" comes from `NowDep` and is passed down; `random` is banned. Line length stays 88. |
| Tests | Names cite rule IDs (`test_br056_…`). The schema comes from `alembic upgrade head`; the test session joins an outer transaction and commits in teardown before the invariant queries; the app override wraps each request in `begin_nested()`, and so does a test that expects a database error. `httpx2`, not `httpx`. Hypothesis only on the engine. |

## Before you report the work as done

Run the commands of the guide's §2 from `backend/`, never from the repository root: `uv sync --locked`, `ruff format`, `ruff check`, `mypy`, `lint-imports`, the tests with coverage, and the OpenAPI drift check.

If a rule stops you from doing what the task needs, do not work around it. Say which rule, and propose a change to `docs/python-style.md`.
