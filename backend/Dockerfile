# syntax=docker/dockerfile:1

# The api image (ADR-014) and its development variant (ADR-004), built from backend/.
# The last stage, runtime, is the default target; compose.override.yaml builds dev.

FROM python:3.15.2-slim-trixie AS base
# The venv comes first on PATH. Logs go to stderr unbuffered (§4.6). Nothing writes
# .pyc files at runtime: the venv is read-only for the app user, and in development
# the source is mounted from the host.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
# A fixed id above the system range, which no host user is likely to share.
RUN groupadd --gid 10001 tourneyhub \
    && useradd --uid 10001 --gid tourneyhub --no-create-home \
        --home-dir /nonexistent --shell /usr/sbin/nologin tourneyhub


FROM base AS uv
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
# The image's CPython 3.15.2, never a downloaded one; the venv lives outside /src,
# where development mounts the source.
ENV UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /src


FROM uv AS build
# Dependencies first, so that a change in src/ reuses this layer.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=.python-version,target=.python-version \
    uv sync --locked --no-dev --no-install-project
COPY pyproject.toml uv.lock .python-version ./
COPY src/ src/
# Non-editable: the project goes into the venv as a wheel, which ships migrations/
# but no pyproject.toml, hence `tourneyhub migrate` (§7).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


FROM uv AS dev
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=.python-version,target=.python-version \
    uv sync --locked --no-install-project
COPY pyproject.toml uv.lock .python-version ./
COPY src/ src/
# Editable, with the dev group (watchfiles for --reload): the venv points at
# /src/src, which compose.override.yaml replaces with the mounted source.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked
USER tourneyhub
EXPOSE 8000
CMD ["sh", "-c", "tourneyhub migrate && exec uvicorn --factory tourneyhub.app:create_app --host 0.0.0.0 --port 8000 --forwarded-allow-ips 172.30.0.0/24 --reload --reload-dir /src/src"]


FROM base AS runtime
# Only the venv: no uv, no source, no pyproject.toml. It stays owned by root.
COPY --from=build /app/.venv /app/.venv
USER tourneyhub
WORKDIR /app
EXPOSE 8000
# Migrations run as the container starts (ADR-004, ADR-014). exec makes uvicorn
# PID 1, so `docker stop` reaches it. X-Forwarded-For is trusted only from the
# Compose network's fixed range, where Caddy is (ADR-006).
CMD ["sh", "-c", "tourneyhub migrate && exec uvicorn --factory tourneyhub.app:create_app --host 0.0.0.0 --port 8000 --forwarded-allow-ips 172.30.0.0/24"]
