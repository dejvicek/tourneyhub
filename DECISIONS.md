# TourneyHub — Decision Brief

**One-page executive summary of the 13 resolved product & architecture decisions.**

TourneyHub is an open-source, **hosted-first** platform for running leagues and tournaments for any competitive discipline (board games, racket/table sports, bar/pub games, esports) — a ready-to-use hosted service, with self-hosting fully supported from the same codebase. This brief is the fast path to *what was decided and why*. For full requirements, business rules, and models, see **`PRD.md`**.

| Field | Value |
|---|---|
| Document type | Decision brief (executive summary) |
| Version | 1.0 (Draft) |
| Status | For review |
| Role | **Canonical decision log** — PRD §0.3 links here. Full requirement wording remains authoritative in `PRD.md` §24 (Open Questions — resolved) and §25 (Assumptions Register). |

---

## The 13 Decisions

| # | Decision *(ref)* | What we chose | Why (rationale) |
|---|---|---|---|
| 1 | **License** *(Q-001, NFR-019)* | AGPL-3.0 **+ CLA** | Copyleft protects the hosted-service commons (operators who modify the networked app must publish changes); CLA preserves dual-licensing/commercial-hosting optionality. |
| 2 | **GDPR erasure vs integrity** *(Q-002, PRD §13, FR-130)* | Sever User↔Participant, hard-delete identity PII, retain **anonymized** match/finance facts | Reconciles right-to-erasure with competition integrity; de-linked data is anonymous historical fact (Recital 26). |
| 3 | **API style** *(Q-003, PRD §17)* | **REST + JSON only** through V1; GraphQL deferred | Small, stable view set keeps caching/idempotency/ETags simple; `?include=`/`?fields=` + composite endpoints avoid over/under-fetch. |
| 4 | **Tech stack** *(Q-004, PRD §21)* | **.NET 8 / ASP.NET Core**, PostgreSQL + EF Core, SignalR + Redis, **React + Vite + TS** (SSG public pages) | Strong typing + native `decimal` for finance/audit; best-in-class realtime; deep Prague .NET talent pool. |
| 5 | **Money handling** *(Q-005, FR-079/082/083)* | **Manual ledger at MVP** (hosted + self-host) via `IPaymentProvider`/`ManualProvider`; **hosted inbound entry-fee gateway = V1**; outbound payouts = Future+ | Lets communities run free events immediately; keeps payments (the biggest legal/ops load) out of MVP; seam lets one provider drop in at V1. |
| 6 | **Teams** *(Q-006, FR-040a/075a/090a)* | `teamSize` **1–10**, ad-hoc rosters, captain role, equal-split payouts, **per-player** points | Covers doubles/esports now; per-User standings avoid persistent-team complexity (Future). |
| 7 | **Seasons** *(Q-007, A-006, BR-002)* | Exactly **one `active` season** per league; divisions = Future | Keeps standings unambiguous; parallel competitions = separate leagues. |
| 8 | **Disciplines** *(Q-008, FR-040b/040d)* | `Game`→**`Discipline`**; MVP = `winner`+`score`, head-to-head, free-text name | Broadens beyond one game type while keeping the match model 2-sided and additive (free-for-all = Future). |
| 9 | **Result entry** *(Q-009, FR-051/051a/051b)* | `resultEntryMode`: **organizer** (default) + **playerSelfReport** | Enables online/distributed play; organizer always stays the final authority. |
| 10 | **Notifications** *(Q-010, FR-140–143)* | **Transactional email only** via `INotificationChannel`/`EmailChannel`; **hosted = managed provider (primary)**, self-host SMTP (secondary) | Email underpins verification/invites; managed delivery gives the hosted service deliverability/retries/bounce visibility; seam keeps channels additive. |
| 11 | **Admin bootstrap** *(Q-011, FR-009a–d)* | **Hosted (primary):** platform operator + per-org Owner. **Self-host (secondary):** env-configured bootstrap admin; first-user-admin opt-in; one-shot, audited, always ≥1 admin | Hosted onboarding makes each org creator the OrgOwner; self-host bootstrap stops a random visitor claiming admin on first boot. |
| 12 | **Spectator** *(Q-012, FR-028a/028b)* | **Capability level, not a role** (anonymous + logged-in non-members); MVP adds follow/favourite | Falls out of the league-scoped role model; needs no grant or invitation. |
| 13 | **Best-of-N** *(Q-013, FR-040c)* | **Aggregate result only** (winner + e.g. `2–1`); per-set/map/leg = Future | Captures set/map/leg sports without the `MatchGame` sub-game data-model cost. |

---

## Residual Actions (open — not decisions)

| ID | Action | Gate |
|---|---|---|
| **Q-002a** | Legal counsel review of the §13 erasure policy (hosted operator processes EU personal data) | Before **EU hosted** launch |
| **Q-005a** | Legal review of money-handling/transmission implications | Before **hosted paid-entry rollout** (V1) |

---

*This file is the canonical decision log; PRD §0.3 links here. When a decision changes, update this file **and** the corresponding requirement(s) in `PRD.md` (§24 / §25).*
