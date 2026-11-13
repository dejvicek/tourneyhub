# MVP roadmap

What is left before the MVP described in [PRD.md](PRD.md) is done, as a checklist. Progress is ticked in issue [#84](https://github.com/dejvicek/tourneyhub/issues/84); this file follows it. Work after the MVP is in [ROADMAP.md](ROADMAP.md).

The MVP is split into 16 packages, P1 to P16. The critical path is P1 → P5 → P7 → P8 → P9 → P10 → P11 → P12 → P13 → P14 → P16; P15 can run alongside.

## 1. Done

- [x] P1 Schema decisions: fields, hand placements and game scores.
- [x] P2 and P3 Accounts and sign-in (JWT with a refresh token, ADR-006).
- [x] P4 Instance admin: sign-up code, organizer list, password reset, CLI ([#40](https://github.com/dejvicek/tourneyhub/pull/40)).
- [x] P5 Leagues, players and seasons.
- [x] P6 Engine core: lots, league ranking, seeding, DYP draws, places, season points ([#36](https://github.com/dejvicek/tourneyhub/pull/36)).
- [x] P7 Tournament setup: format, players, pairs, DYP halves, draws and seeds ([#37](https://github.com/dejvicek/tourneyhub/pull/37)).
- [x] P8 Round robin, results and match formats ([#39](https://github.com/dejvicek/tourneyhub/pull/39), [#45](https://github.com/dejvicek/tourneyhub/pull/45)).
- [x] P9 Fields ([#50](https://github.com/dejvicek/tourneyhub/pull/50)).
- [x] P10 Knockout, finishing and season standings ([#57](https://github.com/dejvicek/tourneyhub/pull/57), [#58](https://github.com/dejvicek/tourneyhub/pull/58), [#66](https://github.com/dejvicek/tourneyhub/pull/66)).
- [x] P11 Share link ([#44](https://github.com/dejvicek/tourneyhub/pull/44)) and milestone M1, the DYP evening end to end in e2e ([#47](https://github.com/dejvicek/tourneyhub/pull/47)).

## 2. Small follow-ups

- [x] Sit-out order: not the round before, then fewest sit-outs (BR-058, BR-063) ([#60](https://github.com/dejvicek/tourneyhub/issues/60), [#87](https://github.com/dejvicek/tourneyhub/pull/87)).
- [x] Game difference in round-robin standings, column only in best of 3 and best of 5 (BR-101) ([#61](https://github.com/dejvicek/tourneyhub/issues/61), [#85](https://github.com/dejvicek/tourneyhub/pull/85)).
- [ ] Code for the answers from issue #48 ([#75](https://github.com/dejvicek/tourneyhub/issues/75)); its 19 items Q1–Q46 are ticked there.

## 3. Remove the demo mode

The demo mode (`pnpm dev:demo`, `frontend/src/demo/`) answers the API with MSW. The team now works against the real backend, so the demo goes. Today app code and tests still depend on it, and the screens call 12 routes the backend lacks through `provisionalApi`.

- [x] D1 Move out of `src/demo` what the app uses: `rules.ts` (with the Lord have mercy filter, so the option stays hidden on the knockout start screen), the types from `contract.ts`, and the helpers of the finals screens (`StartKnockoutPage`, `names.ts`, `score.ts`, `RankingTable`, `TiebreakerSheet`). Done when only `src/api/provisional.ts` and `main.tsx` import from the demo outside `src/demo` and the tests. ([#91](https://github.com/dejvicek/tourneyhub/pull/91))
- [x] D2 Tests without the demo: Vitest gets its own MSW handlers and test data instead of the demo store and seed. Done when nothing in `src/test/` imports from `@/demo/`. ([#101](https://github.com/dejvicek/tourneyhub/pull/101))
- [ ] D3 Move the routes the backend already covers or can cover with little work:
  - [ ] Finishing a tournament on the finals screen calls `POST …/finish` instead of `PUT …/state`.
  - [ ] `GET …/players/{player_id}/tournaments` (BR-002, FR-012), together with Q25.
  - [ ] `PUT …/setup/top-players` (FR-041), together with Q11.
- [ ] D4 Routes that come with P12–P14 (section 4). Until they exist, the screens that need them are hidden:
  - [x] P12, P13: the screens move from the provisional `…/ranking` to `GET …/play` and the public `…/standings`; `PUT …/tiebreakers`, `POST …/rounds` and `DELETE …/rounds/{round_id}` exist in the backend, and the screens still have to switch to them. ([#97](https://github.com/dejvicek/tourneyhub/pull/97))
  - [ ] P14: `GET …/participants`, `POST …/entries`, `PUT …/entries/{entry_id}/disabled`.
- [ ] D5 Delete the demo: `src/demo/`, `src/api/provisional.ts` and `src/api/provisionalPaths.ts`, what is left in `src/api/provisionalTypes.ts`, the exports of `src/lib/rules.ts` only the demo read, the `dev:demo` script, the demo settings in `vite.config.ts`, `main.tsx` and CI, and the mentions in `CLAUDE.md` and `docs/style/frontend-style.md`. Done when no demo code is left and lint, typecheck, unit tests, build and e2e pass.
  - [ ] ESLint also stops `./test/…` and `./demo/…` imports from files directly in `src/`, and dynamic `import()` of them.
  - [ ] Comments in `src/test/fake/` that still say "demo", and the ESLint globs and comments for the demo's tests, which match nothing since D2.
  - [ ] Tests that call `provisionalApi` (six files) and the two tests of `providesProvisionalRoutes()` (`src/lib/demoMode.ts`) move to `api` once D3 and D4 switch their routes.
  - [ ] Decide whether the fake engines in `src/test/fake/` (about 3,700 lines that mirror server logic) are replaced by plain fixtures; no issue tracks it yet.

## 4. Rest of the MVP

- [ ] **P12 Swiss** (FR-040, FR-042, FR-043, FR-046; BR-055 – BR-058, BR-065, BR-066, BR-068, BR-072 – BR-074; ADR-011)
  - [x] Engine: pairing, standings with BH1 and BH2, recommended number of rounds ([#38](https://github.com/dejvicek/tourneyhub/pull/38), [#43](https://github.com/dejvicek/tourneyhub/pull/43)).
  - [x] Services and API: start a Swiss phase, add a round against an expected number, delete a round, the order of tie-breakers ([#90](https://github.com/dejvicek/tourneyhub/pull/90)).
  - [x] Screen 11 (between rounds) on the real API ([#97](https://github.com/dejvicek/tourneyhub/pull/97)).
  - [x] Property tests and the benchmark (ADR-011 Timing) ([#95](https://github.com/dejvicek/tourneyhub/pull/95)).
  - [ ] Tie-breaker order after the knockout draw, and the game-difference column in a Swiss ([#92](https://github.com/dejvicek/tourneyhub/issues/92), waiting for an answer).
  - [ ] Cut line during the Swiss rounds, before the knockout is drawn ([#98](https://github.com/dejvicek/tourneyhub/issues/98), waiting for an answer).
- [ ] **P13 Monster DYP** (FR-041, FR-045; BR-060 – BR-063, BR-081 – BR-084; ADR-010, ADR-011)
  - [x] Engine: round draws, standings, knockout entries ([#41](https://github.com/dejvicek/tourneyhub/pull/41)).
  - [ ] Services and API: start, rounds, top players (`entries.is_top_player`).
  - [ ] Knockout modes: seeded pairs, singles, A little mercy, Lord have mercy.
  - [ ] Lord have mercy re-mix ([#63](https://github.com/dejvicek/tourneyhub/issues/63)):
    - [x] Step 1, data model and engine: a stored draw per knockout round (DATA-MODEL D4 and D5, ADR-009, ADR-010); the draw of later rounds, the result lock and places per player in the engine ([#93](https://github.com/dejvicek/tourneyhub/pull/93)).
    - [ ] Step 1, services, API and screens: drawing and deleting a knockout round, disabling a player in the knockout, finishing, the round-by-round view on the organizer's screen and on the share link, and the option on the start-knockout screen. Needs the Monster DYP services and the knockout modes above.
    - [ ] Step 2: replacements.
    - [ ] Order of re-mixed pairs sharing a place ([#94](https://github.com/dejvicek/tourneyhub/issues/94), waiting for an answer).
    - [ ] Check the bracket size of round 1 in `remix_state` ([#96](https://github.com/dejvicek/tourneyhub/issues/96)).
  - [ ] Screen 13 and marking top players on the real API.
  - [x] Which draw to use when every grouping repeats a partner ([#79](https://github.com/dejvicek/tourneyhub/issues/79), [#83](https://github.com/dejvicek/tourneyhub/pull/83)).
- [ ] **P14 Late players and disabling** (FR-044, FR-047, FR-048; BR-045, BR-054, BR-064, BR-067)
  - [ ] Disable and enable a participant (written as a target state, ADR-008).
  - [ ] Late entries in Swiss and Monster DYP.
  - [ ] Reschedule a round robin for a late entry, keeping seeds 1 and 2 last (BR-054, BR-051) ([#62](https://github.com/dejvicek/tourneyhub/issues/62)).
  - [ ] A late entry takes a bye; warning about the Buchholz tie-breakers.
  - [ ] Screen 12 on the real API.
- [ ] **P15 Deployment** (ADR-005, ADR-014)
  - [ ] CI pushes the images to GHCR after e2e on `main`.
  - [ ] VPS, domain, Let's Encrypt, HSTS rolled out in stages.
  - [ ] The api uses its own database role, not the superuser.
  - [ ] Backups with `pg_dump` off the VPS, with a tested restore.
  - [ ] Monitoring that alerts a person; log retention; secrets.
  - [ ] Open: who gets the alerts; EU hosting and the privacy note.
- [ ] **P16 Pilot readiness** (FR-082; ADR-012, ADR-013)
  - [ ] e2e of a Monster DYP evening.
  - [ ] e2e on Android Chromium and WebKit.
  - [ ] Accessibility report (axe) in both themes.
  - [ ] Test that entering a result takes 3 taps.

