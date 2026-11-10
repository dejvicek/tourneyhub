# TourneyHub

TourneyHub lets an organizer run a league in seasons, play tournaments inside each season (alone, in pairs or with drawn partners), enter results from a phone and share read-only standings with the group. What it does is in [PRD.md](PRD.md), how it is built in [ADR.md](ADR.md), the database in [DATA-MODEL.md](DATA-MODEL.md) and the backend's code style in [docs/python-style.md](docs/python-style.md); [docs/architecture](docs/architecture) pictures it in LikeC4.

## Prerequisites

- Docker with Compose v2, Docker Engine 25 or later (the api's healthcheck uses `start_interval`).
- For the end-to-end test and the frontend checks on the host: Node.js 26.13.0 (`frontend/.nvmrc`) and pnpm 12.18.0 (`packageManager` in `frontend/package.json`). Node 25 and later ship no Corepack, so install pnpm yourself, e.g. `npm install --global pnpm@12.18.0`.

The images pin the rest: Python 3.15.2 with uv 0.13.7 (`backend/Dockerfile`), PostgreSQL 17, Caddy 2.11.9 (`frontend/Dockerfile`).

## Configuration

Settings come from `.env` in the repository root, which is never committed. Copy [.env.example](.env.example), which describes every variable, and fill in the empty values (the two secrets; `openssl rand -hex 24` makes one):

```sh
cp .env.example .env
```

Both stacks use the Compose project `tourneyhub` and the same database volume; stop one with `docker compose down` before starting the other.

> Sign-up (P2b) and the login screens (P2c) are not there yet, so accounts are created by hand. Expose neither stack beyond a trusted local network.

## Development stack

```sh
docker compose up --build
```

`db`, `api` (uvicorn with reload, migrations at start) and `frontend` (Vite with hot reload). Open http://localhost:5173, or `http://<the machine's LAN address>:5173` on a phone; Vite passes `/api` on to the api. The api itself is on http://localhost:8000 only. To run a second stack (another worktree) beside this one, give it its own Compose network range with `COMPOSE_SUBNET=172.31.20.0/24` in `.env` (default `172.30.0.0/24`; it also sets the api's `FORWARDED_ALLOW_IPS` in production).

## Production stack locally

The images that CI tests and the VPS runs: Caddy serving the built frontend and proxying `/api`, the api and the database. When ports 80 or 443 are taken, set `HTTP_PORT=8080` and `HTTPS_PORT=8443` in `.env`.

```sh
docker compose -f compose.yaml -f compose.prod.yaml up --build --detach --wait
docker compose -f compose.yaml -f compose.prod.yaml down
```

Open https://localhost:8443 (or https://localhost on 443). The certificate comes from Caddy's internal CA, so the browser warns about it. `TOURNEYHUB_ENV` is `production` and `TOURNEYHUB_COOKIE_SECURE` `true` here, whatever `.env` says.

## Backend checks

Inside the development `api` container, with the venv's commands; `uv run` does not work there, since the venv belongs to root. The tests need two empty databases (docs/python-style.md §9), created once per database volume:

```sh
docker compose up --detach --wait
docker compose exec db createdb -U postgres tourneyhub_test
docker compose exec db createdb -U postgres tourneyhub_test_migrations
docker compose exec api sh -c '
  db=${TOURNEYHUB_DATABASE_URL%/*}
  export TOURNEYHUB_TEST_DATABASE_URL=$db/tourneyhub_test
  export TOURNEYHUB_TEST_MIGRATIONS_DATABASE_URL=$db/tourneyhub_test_migrations
  ruff format --check && ruff check && mypy && lint-imports &&
  coverage run -m pytest && coverage report &&
  coverage report --include="*/tourneyhub/engine/*" --fail-under=100 &&
  python -W error -m tourneyhub.openapi | diff -u openapi.json -'
```

docs/python-style.md §2 lists the same commands for uv on the host, where the tests need a PostgreSQL 17 of your own, created with the builtin locale.

## Frontend checks

```sh
cd frontend
pnpm install --frozen-lockfile
pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build
```

The same scripts also run in the development container: `docker compose exec frontend pnpm lint`.

## End-to-end test

Playwright in desktop Chromium against the production stack on https://localhost:8443 (`frontend/e2e`, ADR-013). With `HTTP_PORT=8080` and `HTTPS_PORT=8443` in `.env`:

```sh
docker compose -f compose.yaml -f compose.prod.yaml up --build --detach --wait
cd frontend
pnpm exec playwright install chromium  # once; on Linux add --with-deps
pnpm e2e
cd ..
docker compose -f compose.yaml -f compose.prod.yaml down
```

`E2E_BASE_URL` points the test elsewhere. On failure, traces, screenshots and videos are in `frontend/e2e/test-results`.

## CI

`.github/workflows/ci.yml` runs the backend, frontend and end-to-end jobs on every pull request, each only when its area changed; `ci-ok` is the one check to require (ADR-012). Dependabot keeps the dependencies, base images and actions current.
