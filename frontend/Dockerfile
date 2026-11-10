# syntax=docker/dockerfile:1

# The web image (ADR-005, ADR-014): Caddy serving the built frontend and
# proxying /api to the api service. The last stage, runtime, is the default
# target; dev runs the Vite dev server for compose.override.yaml (ADR-004).
# The build context is frontend/. The schema for the API types comes from the
# named context `backend`, the backend/ directory, of which only openapi.json
# is copied; Compose passes it, by hand it is
# `docker build --build-context backend=backend frontend`.

FROM node:26.13.0-trixie-slim AS node
# Node 25 and later ship no Corepack, so pnpm is installed explicitly, at the
# version pinned in package.json's packageManager (ADR-003).
RUN --mount=type=cache,target=/root/.npm \
    npm install --global pnpm@12.18.0
WORKDIR /src/frontend


FROM node AS dev
# compose.override.yaml mounts the source here and a named volume on
# node_modules; a new volume takes over this directory's owner.
RUN mkdir node_modules && chown node:node node_modules
USER node
EXPOSE 5173
# The volume is installed from the lockfile at every start, so it follows
# pnpm-lock.yaml. Vite listens on all of the container's interfaces, and
# Compose publishes the port on all of the host's, for a phone (ADR-004).
CMD ["sh", "-c", "pnpm install --frozen-lockfile && exec pnpm dev --host 0.0.0.0"]


FROM node AS build
# Dependencies first, so that a change in src/ reuses this layer.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/pnpm-store \
    pnpm install --frozen-lockfile --store-dir /pnpm-store
COPY . .
# The build runs generate:api first, which reads ../backend/openapi.json
# (ADR-008).
COPY --from=backend openapi.json /src/backend/openapi.json
RUN pnpm build


FROM caddy:2.11.9-alpine AS runtime
# An unprivileged user with a fixed id; /data (certificates, the local CA) and
# /config must be writable for it. Binding 80 and 443 needs no root: Docker
# starts containers with net.ipv4.ip_unprivileged_port_start=0.
RUN addgroup -S -g 10001 caddy \
    && adduser -S -D -H -u 10001 -G caddy -h /nonexistent -s /sbin/nologin caddy \
    && chown -R caddy:caddy /data /config
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /src/frontend/dist /srv
USER caddy
