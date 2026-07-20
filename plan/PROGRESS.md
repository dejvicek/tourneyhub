# TourneyHub — Progress Tracker

> Live status of the phased implementation plan. Update the `Status` column as steps progress.
> Reference: [`plan/README.md`](./plan/README.md) (step details, dependencies, template).
>
> Legend — Status: ⬜ not started · 🟨 in progress · ✅ done · ⏸️ blocked · ❌ cancelled
> Scope: `MVP` (ship first) · `MVP*` (recommend defer to V1) · `V1` · `Future`

| #   | Step                               | Status | Scope        | Depends on | Started  | Completed |
| --- | ---------------------------------- | ------ | ------------ | ---------- | -------- | --------- |
| 00  | Project meta & tooling hardening   | ✅      | MVP          | —          | 2026-07-18 | 2026-07-18 |
| 01  | Tenancy as a real boundary         | ✅      | MVP          | 00         | 2026-07-20 | 2026-07-20 |
| 02  | API conventions & optimistic concurrency | ✅ | MVP          | 01         | 2026-07-20 | 2026-07-20 |
| 03  | ADR: recompute/concurrency/outbox/PRNG | ✅      | MVP          | —          | 2026-07-20 | 2026-07-20 |
| 04  | Audit log + outbox + notification seam | ✅ | MVP          | 01, 03     | 2026-07-20 | 2026-07-20 |
| 05  | Auth & accounts                    | ✅      | MVP          | 00, 01, 02 | 2026-07-20 | 2026-07-20 |
| 06  | Organizations & membership         | ✅      | MVP          | 01, 05     | 2026-07-20 | 2026-07-20 |
| 07  | Platform admin & self-host bootstrap | ✅    | MVP          | 06         | 2026-07-20 | 2026-07-20 |
| 08  | Invitations                        | ✅      | MVP          | 06, 04     | 2026-07-20 | 2026-07-20 |
| 09  | Transactional notifications        | ✅      | MVP          | 04, 05, 08 | 2026-07-21 | 2026-07-21 |
| 10  | Leagues & seasons                  | ✅      | MVP          | 06         | 2026-07-21 | 2026-07-21 |
| 11  | Scoring system config              | ⬜      | MVP          | 10         | —        | —         |
| 12  | Tournaments, participants & rosters | ⬜     | MVP          | 10         | —        | —         |
| 13  | Single-elimination bracket         | ⬜      | MVP          | 12         | —        | —         |
| 14  | Round-robin & tie-breaks           | ⬜      | MVP*         | 11, 12     | —        | —         |
| 15  | Match results, validation & recompute | ⬜   | MVP          | 02, 03, 13 | —        | —         |
| 16  | Rankings, standings & public reads | ⬜      | MVP          | 11, 15     | —        | —         |
| 17  | Live/realtime gateway              | ⬜      | MVP*         | 04, 16     | —        | —         |
| 18  | Fees, payments & prize pool        | ⬜      | MVP*         | 12, 16     | —        | —         |
| 19  | Payouts & team splits              | ⬜      | MVP*         | 18         | —        | —         |
| 20  | GDPR & privacy                     | ⬜      | MVP          | 05, 16     | —        | —         |
| 21  | Reporting & exports                | ⬜      | V1           | 16, 19     | —        | —         |
| 22  | Hosted inbound payments            | ⬜      | V1 (gated)   | 18         | —        | —         |

---

## How to use

1. When starting a step: set `🟨 in progress` and fill in the `Started` date.
2. When finishing a step: set `✅ done`, fill in `Completed`, and commit the completed step files.
3. If a step is blocked by an upstream dependency mid-work: set `⏸️ blocked` and note why.

**Definition of Done** for every step = AGENTS.md §8 + the step's own DoD section. No evidence = not done.
