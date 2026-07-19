# TourneyHub

**Open-source, hosted-first platform for running leagues and tournaments for any competitive discipline.** Board games, racket sports, bar games, esports — create an organization, set up leagues, and run tournaments with brackets, standings, and live results.

Use it as a ready-to-go hosted service, or self-host the same codebase.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | .NET 8, ASP.NET Core |
| API | REST + JSON (OpenAPI 3) |
| Database | PostgreSQL + EF Core |
| Cache / Realtime | Redis (SignalR backplane) |
| Frontend | React + Vite + TypeScript, Tailwind CSS |
| Auth | ASP.NET Core Identity (Argon2id/PBKDF2) |
| Testing | xUnit + Testcontainers + Playwright |

---

## Prerequisites

- [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0)
- [Node.js 20+](https://nodejs.org/)
- [Docker](https://www.docker.com/) (for Postgres, Redis, Mailpit)

---

## Quick Start

```bash
# 1. Clone and copy env
git clone <repo-url> tourneyhub && cd tourneyhub
cp .env.example .env

# 2. Start infrastructure
docker compose up -d

# 3. Apply database migrations
dotnet ef database update \
  --project src/TourneyHub.Infrastructure \
  --startup-project src/TourneyHub.Api

# 4. Run the API
dotnet run --project src/TourneyHub.Api
# → http://localhost:8080
# → http://localhost:8080/swagger

# 5. Run the frontend (separate terminal)
cd web && npm ci && npm run dev
# → http://localhost:5173
```

---

## Project Structure

```
tourneyhub/
├── src/
│   ├── TourneyHub.Domain/         # Entities, value objects, domain services
│   ├── TourneyHub.Application/    # Use cases, ports (interfaces)
│   ├── TourneyHub.Infrastructure/ # EF Core, Redis, email, payment providers
│   └── TourneyHub.Api/            # ASP.NET Core host, controllers, SignalR hubs
├── tests/                         # xUnit: unit, integration (Testcontainers), architecture
├── web/                           # React + Vite + TypeScript SPA
├── api/openapi.yaml               # API contract (source of truth)
├── spec/                          # Requirements traceability + test vectors
├── plan/                          # Phased implementation plan
├── docker-compose.yml             # Postgres + Redis + Mailpit
└── PRD.md                         # Product requirements (governs all development)
```

---

## Useful Commands

| Task | Command |
|---|---|
| Backend build | `dotnet build` |
| Run all tests | `dotnet test` |
| EF migration add | `dotnet ef migrations add <Name> --project src/TourneyHub.Infrastructure --startup-project src/TourneyHub.Api` |
| Frontend dev | `cd web && npm run dev` |
| Frontend build | `cd web && npm run build` |
| Frontend typecheck | `cd web && npm run typecheck` |
| Frontend lint | `cd web && npm run lint` |
| Regenerate API types | `cd web && npm run gen:api` |
| Validate OpenAPI | `npx @redocly/cli lint api/openapi.yaml` |
| Infra up/down | `docker compose up -d` / `docker compose down` |

## Health Checks

| Endpoint | Purpose |
|---|---|
| `/health/live` | Liveness ping (always 200 if server running) |
| `/health/ready` | Readiness probe (checks DB + Redis; 503 if unhealthy) |

---

## Documentation

- **[PRD.md](./PRD.md)** — Product requirements (governs all development)
- **[DECISIONS.md](./DECISIONS.md)** — Resolved architectural decisions
- **[AGENTS.md](./AGENTS.md)** — Development guide (guardrails, conventions, DoD)
- **[CONTRIBUTING.md](./CONTRIBUTING.md)** — How to contribute (CLA required)
- **[plan/](./plan/)** — Phased implementation plan

---

## License

[GNU Affero General Public License v3.0](./LICENSE)

TourneyHub is free software: you can redistribute it and/or modify it under the terms of the AGPL-3.0. If you modify and run this software as a network service, you must make your modified source code available to users of that service.