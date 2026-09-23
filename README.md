# TourneyHub

Open-source, hosted-first, multi-tenant platform for running leagues and tournaments for any competitive discipline. Python backend, React frontend, PostgreSQL. AGPL-3.0.

**This branch is a from-scratch rewrite. Code is not scaffolded yet — start with the documents.**

| Read | For |
|---|---|
| [`CLAUDE.md`](./CLAUDE.md) | How to work in this repo: stack, commands, gates, guardrails, Definition of Done, module recipe |
| [`PRD.md`](./PRD.md) | MVP requirements (governs behaviour) |
| [`DATA-MODEL.md`](./DATA-MODEL.md) | PostgreSQL schema — **must be approved by the owner before persistence code** |
| [`ADR.md`](./ADR.md) | Architecture decisions and core semantics |
| [`ROADMAP.md`](./ROADMAP.md) | Post-MVP modules and the seams reserved for them |
| [`spec/`](./spec) | Requirement traceability, error catalog, golden test vectors |
| [`design/tokens.css`](./design/tokens.css) | Design tokens for the web app |

Local infrastructure: `docker compose up -d` (Postgres 16, Redis 7, Mailpit). Configuration reference: [`.env.example`](./.env.example).
