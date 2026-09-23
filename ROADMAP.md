# TourneyHub — Roadmap: Post-MVP Modules

> Everything that is **not** in the MVP (`PRD.md`), organised as **modules** so each can be added later with an additive migration and a new `ModuleManifest` (ADR-004). Agents: read the module you are touching **and** §3 (reserved seams) before designing anything nearby. Requirement IDs come from PRD v1 and stay stable.
>
> Tiers: **V1** = first post-MVP release (hardening/depth). **Future** = later, not yet committed. Nothing here may be pulled into the MVP without a `PRD.md` change.

## 1. Module index

| Module id | Tier | Title | Depends on | Reserved seam at MVP (§3) |
|---|---|---|---|---|
| M-PAY | V1 | Hosted inbound payments (one gateway) + refunds + unpaid policy | finance | `PaymentProvider` port, `payments.provider/provider_ref`, payment FSM `failed` |
| M-REPORT | V1 | Reporting & CSV export (async artifacts) | leagues, tournaments, finance | `reporting` module slot, report views (FR-100) |
| M-SCORE+ | V1 | Custom scoring systems + configurable tie-breakers + ranking-based seeding | leagues, tournaments | `scoring_systems.config` jsonb, `preset_key NULL = custom`, `seeding_method` CHECK |
| M-PRIZE+ | V1 | Custom prize distribution (per-rank basis points) | finance | `prize_config` jsonb shape `{distribution_bp: []}` |
| M-AUTH+ | V1 | OAuth (Google, GitHub), TOTP 2FA, inactivity flagging | identity | `users.last_login_at`, `refresh_tokens.family_id`, auth router |
| M-ENT | V1 | Plan entitlements & per-tenant quotas / rate limits | platform | `organizations.plan`, `EntitlementService` port |
| M-STATS+ | V1 | Player statistics depth, cached rankings, materialized stats | leagues, tournaments | `v_player_statistics` view → materialized; `source_version` |
| M-UX-V1 | V1 | Dark mode, WCAG 2.1 AA audit, public-page prerender/SSG | web | design tokens, `/public/*` endpoints with OpenGraph data |
| M-FORMATS | Future | Double elimination, Swiss, group stage, custom | tournaments | `TournamentFormat` protocol, `format_type` key, `match_slots.source_kind='loser'`, `loser_next_match_id` |
| M-FFA | Future | Free-for-all / `placement` result model (N-slot matches) | tournaments | `match_slots` table, `match_slots.placement`, `result_model` CHECK |
| M-BESTOF | Future | Structured best-of-N (`match_games` per set/map/leg) | tournaments | `tournaments.best_of`, `match_slots.score` as aggregate |
| M-DISC | Future | Managed discipline catalog | leagues, tournaments | `tournaments.discipline_id` nullable seam, `discipline_name` stays |
| M-TEAMS | Future | Persistent named teams, team standings, substitutions, `team_size > 10` | tournaments, leagues | `participants.display_name`, `participant_members`, per-user standings unchanged |
| M-DIV | Future | League divisions (parallel ladders) | leagues | one-active-season invariant kept; `seasons` gain `division_id` |
| M-SOCIAL | Future | Private `viewer` role, follower counts, comments | invitations, leagues | `league_memberships.role` CHECK, `follows` |
| M-RATING | Future | Head-to-head analytics, Elo/rating systems | leagues | `v_player_statistics`, event stream |
| M-PDF | Future | PDF export | reporting | async artifact pipeline from M-REPORT |
| M-PAYOUT | Future | Automated outbound payouts (KYC, Connect-style) | finance, M-PAY | `payouts`/`payout_shares` FSM, provider port |
| M-SAAS | Future | Subscriptions, billing, invoicing, tax/VAT, dunning | platform, M-ENT | `organizations.plan`, finance isolation |
| M-BRAND | Future | Custom branding / white-label / custom domains | platform, web | `organizations.branding` jsonb, CSS tokens |
| M-RESIDENCY | Future | Per-region data residency, enterprise SSO/SCIM | platform, identity | central tenant session (schema/db-per-tenant migration path) |
| M-PLUGINS | Future | Third-party plugin system (formats, scoring) | core registry | `ModuleManifest`, entry-point discovery |
| M-NOTIF | Future | Engagement notifications, web push, in-app center, Discord/Slack/webhooks, preferences | platform | `NotificationChannel` registry, `notification_deliveries.channel` CHECK, `transactional` flag |
| M-I18N | Future | UI translations | web | react-i18next already wired, no hard-coded strings |
| M-MOBILE | Future | PWA / offline result entry | web, realtime | ETag reconciliation, idempotency keys |
| M-WEBHOOKS | Future | Outbound webhooks + API keys/PATs for integrations | platform, identity | outbox events, auth router |

## 2. Module briefs

Each brief: purpose, requirements carried, data-model delta, API delta, notes for the agent.

### M-PAY — Hosted inbound payments, refunds, unpaid policy (V1)
- **Requirements:** FR-083 (inbound gateway, webhooks authoritative for `paid`/`failed`/`refunded`), FR-076 (full/partial refunds with reason + audit), FR-077 (unpaid-by-deadline → `forfeited` or removed, configurable, A-009), BR-107 (refund ≤ paid), E-11, E-17, E-26.
- **Data:** new `refunds` (id, org, payment_id, amount_minor, currency, reason, recorded_by, provider_ref, created_at) with `CHECK Σ refunds ≤ payment.amount_minor` enforced in app; `payments.provider = 'stripe'` etc.; `webhook_events` (provider, event_id UNIQUE, payload, processed_at) for idempotent webhook handling; `tournaments.unpaid_policy` jsonb.
- **API:** `POST …/registrations/{id}/checkout` → provider session URL; `POST /api/v1/webhooks/{provider}`; `POST …/payments/{id}/refunds`.
- **Notes:** implement as a new `PaymentProvider` in a `finance_stripe` module (or provider package) registered via manifest; `ManualProvider` stays for self-host and free events. **Gated on legal review Q-005a.** Self-host never moves money; disclaimer remains.

### M-REPORT — Reporting & CSV (V1)
- **Requirements:** FR-078 (financial report: income, fees, pool, payouts, balance), FR-101 (CSV of standings, schedules, financial reports), FR-103 (async generation with downloadable artifact).
- **Data:** `report_jobs` (id, org, kind, params jsonb, status, artifact_url, requested_by, created_at, completed_at). Object storage adapter (S3-compatible / local disk).
- **API:** `POST …/reports` → job; `GET …/reports/{id}`; `GET …/reports/{id}/download`.
- **Notes:** reads only via other modules' public services or read-only SQL views; runs in the worker (`ScheduledJob`/on-demand).

### M-SCORE+ — Custom scoring, configurable tie-breakers, ranking-based seeding (V1)
- **Requirements:** FR-025 (custom values), FR-057 (configurable tie-break list), FR-046 (`ranking` seeding from current season standings), FR-059 explicit reopen endpoint (optional; ADR-002 already reopens implicitly).
- **Data:** none beyond widening `seeding_method` CHECK to include `ranking`; `scoring_systems.preset_key = NULL`.
- **Notes:** the UI gains a scoring editor; validation via the existing `ScoringConfig` schema; new tie-breaker keys register in a `TieBreakerRegistry`.

### M-PRIZE+ — Custom prize distribution (V1)
- **Requirements:** FR-073 custom per-rank basis points (must sum to 10 000), organizer fee already covered.
- **Data:** `prize_config` `{v:1, distribution_bp:[...]}` already accepted by the schema; UI + validation only.

### M-AUTH+ — OAuth, TOTP, inactivity (V1)
- **Requirements:** FR-011 (Google, GitHub OAuth), FR-012 (TOTP 2FA), FR-013 (inactivity flag after 540 d, A-004).
- **Data:** `external_identities` (user_id, provider, subject UNIQUE, email, linked_at); `users.totp_secret_enc`, `users.totp_enabled_at`; `recovery_codes` (hashed).
- **Notes:** OAuth via `authlib`; account linking requires verified email match or explicit link flow; inactivity job in the worker.

### M-ENT — Entitlements & quotas (V1)
- **Requirements:** FR-156 enforcement, per-tenant rate limiting/quotas (PRD v1 §4.2).
- **Data:** `plans` (key, limits jsonb) seeded; `organizations.plan` FK-ish by key; `usage_counters` (org, metric, period, value).
- **Notes:** `EntitlementService.check(org, capability, quantity)` already called at MVP with a permissive default; this module supplies the real implementation and 402/429 responses (`plan_limit_reached`). Only build if monetization or abuse control is needed.

### M-STATS+ — Statistics depth & caching (V1)
- **Requirements:** FR-093 depth, FR-096 (cache derived rankings, invalidate on source change, R-004), FR-094 richer histories.
- **Data:** materialize `v_player_statistics` → `player_statistics` table refreshed by outbox handlers; Redis cache for public overview.

### M-UX-V1 — Dark mode, accessibility, prerender (V1)
- **Requirements:** NFR-010 WCAG 2.1 AA audit, dark mode via tokens (R-017 prerender/SSG of public routes for SEO).
- **Notes:** dark theme = second token set in `design/tokens.css`; prerender via Vite SSG plugin or a build-time crawler hitting `/public/*`.

### M-FORMATS — More formats (Future)
- **Requirements:** double elimination, Swiss, group stage, custom (PRD v1 §4.3).
- **Data:** none required: `matches.loser_next_match_id`, `match_slots.source_kind='loser'`, `format_config` jsonb already exist; group stage may add `matches.group_label`.
- **Notes:** each format is a `TournamentFormat` implementation + golden vectors in `spec/test-vectors/`; standings logic per format.

### M-FFA — Free-for-all / placement (Future)
- **Requirements:** `result_model='placement'`, N-slot matches (FR-040b/040d Future).
- **Data:** widen `result_model` CHECK; use `match_slots.placement`; `winner_slot_no` becomes derived from placement 1.
- **Notes:** scoring function gains a placement → points table; ships together with group stage.

### M-BESTOF — Structured best-of-N (Future)
- **Data:** new `match_games` (id, org, match_id, game_no, winner_slot_no, scores per slot jsonb, played_at); aggregate stays in `match_slots.score` for compatibility.

### M-DISC — Discipline catalog (Future)
- **Data:** new `disciplines` (id, org NULL for global?, name, default_result_model, default_team_size, icon) — decide global vs per-org at design time; `tournaments.discipline_id` FK filled, `discipline_name` kept as display snapshot.

### M-TEAMS — Persistent teams (Future)
- **Requirements:** cross-tournament team identity, team standings, in-tournament substitutions, `team_size > 10` (PRD v1 §4.3, A-015/016/017 overrides).
- **Data:** new `teams` (org, name, slug, captain_user_id), `team_members`; `participants.team_id` nullable; substitutions log; team-scoped season standings table alongside per-user ones.

### M-DIV — League divisions (Future)
- **Data:** `divisions` (league_id, name, order); `seasons.division_id`; partial unique index becomes `(league_id, division_id) WHERE active`.

### M-SOCIAL — Private viewers & social (Future)
- **Data:** widen `league_memberships.role` CHECK with `viewer`; follower counts from `follows`; `comments` table (org, target, author, body, created_at, moderation state).

### M-RATING — Head-to-head & Elo (Future)
- **Requirements:** FR-097, FR-098.
- **Data:** `ratings` (org, scope, user_id, rating_milli, games, updated_at), `rating_history`; computed from outbox `match.completed` events in order (deterministic replay).

### M-PDF — PDF export (Future)
- **Requirements:** FR-102. Builds on M-REPORT artifacts (WeasyPrint or headless Chromium in the worker).

### M-PAYOUT — Automated outbound payouts (Future)
- **Requirements:** FR-083 outbound (KYC-gated, Connect-style). Data: `payout_shares.provider_ref`, `payee_accounts` (user_id, provider, account_ref, kyc_state). Heavy legal/ops; only after M-PAY has run in production.

### M-SAAS / M-BRAND / M-RESIDENCY / M-PLUGINS (Future)
- **M-SAAS:** subscriptions, invoices, tax; `subscriptions`, `invoices` tables; provider webhooks; entitlement integration.
- **M-BRAND:** `organizations.branding` jsonb (logo, colours, domain); CSS variables override per org; custom domains need a hostname → org resolver in the tenant dependency (ADR-006 layer 1 already resolves by URL).
- **M-RESIDENCY:** region pinning per org; the tenant session is the single choke point to route to a regional database; SSO/SCIM via M-AUTH+ foundations.
- **M-PLUGINS:** external packages exposing `ModuleManifest` via Python entry points (`tourneyhub.modules`); sandboxing/versioning policy needed.

### M-NOTIF — Engagement notifications & channels (Future)
- **Requirements:** FR-144 (match-ready, seeded, season-started, digests; web push, in-app, Discord/Slack/webhooks; per-user preferences), FR-143 opt-out honoured.
- **Data:** `notification_preferences` (user_id, category, channel, enabled); widen `notification_deliveries.channel` CHECK; `push_subscriptions`.
- **Notes:** new `NotificationChannel` implementations registered via manifest; templates flagged `transactional=False` consult preferences.

### M-I18N / M-MOBILE / M-WEBHOOKS (Future)
- **M-I18N:** translation files per locale; extraction script; no backend change.
- **M-MOBILE:** PWA manifest, service worker, offline queue of result submissions replayed with `Idempotency-Key` and `If-Match`.
- **M-WEBHOOKS:** `webhook_endpoints` (org, url, secret, events[]), deliveries table with retries, signed payloads sourced from `outbox_events`; `api_keys` (user/org, hashed, scopes) for automation.

## 3. Seams the MVP must reserve (checklist for agents)

These exist at MVP **only** so the modules above can be added additively. Do not remove them; do not build on them beyond what `PRD.md` requires.

| Seam | Where | Serves |
|---|---|---|
| `TournamentFormat` protocol + `FormatRegistry` from manifests | `tournaments/domain/formats` | M-FORMATS, M-FFA |
| `match_slots` table (ordered sides), `placement` column, `source_kind='loser'`, `loser_next_match_id` | `DATA-MODEL.md` §8.5–8.6 | M-FORMATS, M-FFA |
| `tournaments.best_of` + aggregate `match_slots.score` | §8.1, §8.6 | M-BESTOF |
| `tournaments.discipline_id` nullable, `discipline_name` kept | §8.1 | M-DISC |
| `participants` decoupled from users; `display_name` snapshot | §8.2 | M-TEAMS, GDPR |
| `PaymentProvider` port, `ManualProvider`, `payments.provider/provider_ref`, `failed` state | finance module | M-PAY, M-PAYOUT |
| `prize_config` accepts `distribution_bp` | finance schema | M-PRIZE+ |
| `scoring_systems.config` jsonb, `preset_key` nullable, `TieBreakerRegistry` | leagues module | M-SCORE+ |
| `seeding_method` as text CHECK | §8.1 | M-SCORE+ (ranking) |
| `organizations.plan`, `EntitlementService` port (permissive default) | platform module | M-ENT, M-SAAS |
| `organizations.branding` jsonb; CSS variable tokens | §4.1, `design/tokens.css` | M-BRAND, M-UX-V1 |
| `NotificationChannel` registry, `transactional` template flag, `notification_deliveries.channel` CHECK | platform module | M-NOTIF |
| `outbox_events` with versioned payloads | §4.5 | M-WEBHOOKS, M-RATING, M-STATS+, realtime |
| `league_memberships.role` as text CHECK | §7.2 | M-SOCIAL (`viewer`) |
| `users.last_login_at`, refresh token families, auth router structure | identity module | M-AUTH+ |
| `v_player_statistics` view with `source_version` provenance | §10 | M-STATS+, M-RATING |
| Tenant session as the single DB choke point; URL-based org resolution | ADR-006 | M-RESIDENCY, M-BRAND (custom domains) |
| `ModuleManifest` registry with `depends_on`, `scheduled_jobs`, plugin tuples | `core/registry.py` | M-PLUGINS, every module |
| `reporting` slot in the module DAG (read-only consumer) | ADR-004 | M-REPORT, M-PDF |
| `Idempotency-Key` + `If-Match` on all mutations | ADR-005 | M-MOBILE |

## 4. Requirement IDs living here (not in `PRD.md`)

FR-011, FR-012, FR-013, FR-018, FR-046 (ranking), FR-057 (configurable), FR-059 (explicit endpoint), FR-073 (custom), FR-076, FR-077, FR-078, FR-083, FR-096, FR-097, FR-098, FR-101, FR-102, FR-103, FR-133, FR-144, BR-107, A-004, A-009, A-013, R-017 (prerender). Keep these IDs when the module is promoted into `PRD.md`.
