# Foos lab on TourneyHub

| | |
|---|---|
| Status | Draft |
| Date | 2026-11-05 |
| Scope | How the training app Foos lab maps onto TourneyHub, and the decisions made so far. Background for the training track (`ROADMAP.md` §5, RM-33–RM-38), ADR-015 to ADR-021 and `DATA-MODEL.md` §8. |

## 1. What Foos lab is

Foos lab ("Rozpis stolů") is the training app of a table football club with 6–13 players and up to 4 tables. It keeps the club's roster and generates each session's schedule: who plays whom, on which table and when. Players enter goals, turnovers and drill results from their phones, and the app ranks players across sessions. It is a React app on Supabase, with its own PRD and a pure domain layer (`src/domain`, about 5,300 lines without tests) that has no React and no database code, the same idea as ADR-009.

Foos lab is temporary. The goal is to have everything in TourneyHub. Its PRD stays the source of the training rules until an item of the training track is picked up and written into `PRD.md`.

## 2. Decisions

| # | Question | Decision (2026-11-05) |
|---|---|---|
| 1 | MVP or roadmap? | Roadmap: the training track, RM-33–RM-38. The MVP schema only gets ordered phases (DATA-MODEL D9). |
| 2 | When does the play time of a time limit start? | `min(started_at, called_at + prep)`: at the start, at the latest when the preparation runs out (ADR-017). |
| 3 | Where do time limits end matches? | Only in training sessions. Other tournaments: open. |
| 4 | Team match (league format, best of three) under a time limit? | No. Its 20-minute waves only plan the session. |
| 5 | Seasons? | One season per year of the club's league. |
| 6 | What counts in the ladder? | The club keeps one league for training. Every tournament in it counts, training sessions and ordinary tournaments alike. |
| 7 | How are drills stored? | As a kind of match (ADR-020). |
| 8 | How does Foos lab move? | It moves onto TourneyHub's API (ADR-021, RM-38), first with its own scheduling, which then moves into TourneyHub's engine. |

## 3. Terms

| Foos lab | TourneyHub today | Training track |
|---|---|---|
| Roster, player (`archived`) | League player list (`removed_at`, BR-001, BR-002) | Unchanged |
| Attendees in nomination order | Entries with seeds | Player entries; the seed is the nomination order, which keeps schedules deterministic |
| Session (`Training`) | Tournament | Tournament of type `training` |
| Rounds of one discipline in a row ("etapa") | Phase (group or knockout) | Phase of kind `training` (ADR-015) |
| Round | Round of a phase | Round of a phase |
| Discipline from the catalog | Match format and goals per game of a phase | Discipline preset, copied into the phase (ADR-016) |
| Break (`BreakDef`) | None | Program break (ADR-015) |
| Table | Field (FR-090–FR-094) | Field |
| Active match, queue | On a field, waiting (BR-130, BR-131) | The same, plus the session's start and breaks as barriers |
| Pairs and singles with new partners every round | Monster DYP sides without an entry (D2) | The same |
| Referee, counts for a drill | Sit-out (`round_participation`) | Sit-out with status `referee` |
| League round simulation | None | Phase of format `team_match` |
| Drill, solo results | None | Match of kind `drill` with `drill_results` (ADR-020) |
| Turnovers `la`, `lb` | None | Side stat `turnovers` |
| `game_events` | Result and game scores only | `match_events` |
| `play_times` | `result_entered_at` | `called_at`, `started_at`, `ended_at`, `end_reason` |
| Session standings | Tournament standings | Standings by the phase's ranking |
| Ladder (form / all / from–to, average / total) | Season standings from placement points | League statistics: scope × ranking (ADR-018) |
| Drill ladder, "Zdržovači" (who keeps others waiting) | None | Drill ladder, waiting times (RM-36, RM-37) |
| Session creator, players entering results at their table | Organizer only | Parts of RM-01, RM-12, RM-13 |

## 4. A session as a program

A session has a length (1:00–4:00), a set of disciplines and the number of rounds of each. Everyone plays the same discipline in a round. Drills come first, then matches in catalog order, then the team match, then 10 minutes for entering results. A round takes the discipline's time plus 1 minute to change over. Breaks of 10 minutes come by default after the drills and after the matches, and the organizer can move them, change their length or add more.

Example: the default disciplines, 8 players, 4 tables, 3:00.

| Phase | Format | Rounds × minutes |
|---|---|---|
| Passes on the five-bar | drill rotation | 1 × 8 |
| Ball control on the five-bar | drill rotation | 1 × 8 |
| Penalty against a goalkeeper | drill rotation | 2 × 4 (two variants) |
| *Break* | | 10 |
| Normal leg | balanced rotation | 2 × 8 |
| Turnover tax | balanced rotation | 1 × 8 |
| Wall | balanced rotation | 2 × 8 (roles swapped in the second round) |
| Start 0:3 with turnover tax | balanced rotation | 2 × 5 (roles swapped) |
| Start 4:4 | balanced rotation | 1 × 5 |
| Start 5:5, win by 2, cap 10 | balanced rotation | 1 × 6 |
| Singles | balanced rotation | 1 × 8 |
| *Break* | | 10 |
| League round simulation | team match | 2 waves × 20 |
| *Entering results* | | 10 |

Planned: 2:58 of 3:00. That is 11 phases, 15 rounds and 2 breaks. The same model describes the DYP evening of PRD §5.1 as 2 phases: a round robin, then a knockout.

A discipline's parameters, as a phase would keep them (ADR-016):

```json
{
  "discipline": "start03",
  "kind": "match",
  "format": "bo1",
  "goals_to": 6, "win_by": 1, "goal_cap": null,
  "start_score": [0, 3],
  "turnover_tax": true,
  "roles": "behind_ahead", "paired": true,
  "track": ["turnovers"],
  "prep_sec": 60, "play_sec": 300,
  "on_time_up": "keep_score"
}
```

With a scenario start, the table shows the score including the start. Only the goals played are stored: a leg that ends 6:4 from 0:3 is stored as 6:1.

## 5. Time limits

A match's limit is preparation plus the discipline's time. The 1 minute Foos lab plans between rounds becomes the preparation.

```
play_from = min(started_at, called_at + prep)
deadline  = play_from + play
```

With a limit of 1 + 8 minutes:

| Started after | What happens |
|---|---|
| 40 s, leg over in the 6th minute | Ends normally. Its field is free at 6:40. |
| 40 s, leg not over | Ends with the score as it stands at 8:40 (`time_up`). |
| 2 min | The play time ran from 1:00. Ends at 9:00, after 7 minutes of play. |

The rest is in ADR-017: who writes the end, the server's clock, the forecast of the session's end, and results after `time_up`. In Foos lab this changes one rule: its PRD §4.8 says nothing ends by itself. With time limits, a match ends when its time runs out, and only a match that ends normally waits for a person to confirm.

## 6. Moving Foos lab

1. **Foos lab, now.** Foos lab builds time limits with the model of ADR-017: a pure deadline function, `called_at` and `end_reason` on its play times, an end checked against the server's clock, and the deadline counted in its queue. It keeps a copy of the rules in each locked round and splits its domain into a generic core (program, queue, time limits, statistics) and the foosball content (catalog, rules, texts).
2. **TourneyHub, MVP.** Phases are ordered (D9). Nothing else of the training track is built.
3. **RM-38.** TourneyHub stores what the training track needs (DATA-MODEL §8) and accepts `external` phases (ADR-021). Foos lab gets a storage implementation on the API, and its data is imported once.
4. **RM-33 to RM-37.** The scheduling moves into TourneyHub's engine: `balanced_rotation`, `drill_rotation` and `team_match`, with Foos lab's acceptance criteria and test cases as test vectors (ADR-012). New sessions are scheduled by TourneyHub, and Foos lab is retired.

### Import

| Foos lab | TourneyHub | Watch out |
|---|---|---|
| `players` | League players | `archived` becomes `removed_at`. Logins are not copied. |
| `trainings`, format `custom` | Tournament of type `training`, phases from `plan`, breaks from `breaks` | Rounds are taken from Foos lab's schedule at import time and stored |
| `trainings`, format `classic` (2026-10-31) | Tournament of type `training` with its fixed blocks as phases | Its schedule is computed one last time by Foos lab's code and stored as matches. The classic algorithm is not ported. |
| `scores` | Game scores and `match_side_stats` | For the team match, `ga`/`gb` are sets won, not goals. The sets themselves were not recorded. |
| `solo_results` | `drill_results` | The key `metric@round` points to the drill match of that round |
| `play_times` | Match, break and tournament times | `training` and `pause|k` are special ids |
| `game_events` | `match_events` | Keep the client-generated ids |

Player and session ids are UUIDs and are kept. Match ids are text (`league|round|table|A1+A2vB1+B2`) and get new UUIDv7 values through a mapping table in the import.

## 7. Open

- Time limits in other tournaments than training sessions (decision 3).
- Whether the per-game average of a league that plays legs to 6 and games to 10 needs a filter by discipline (ADR-018).
- Live updates: Server-Sent Events are proposed (ADR-019) and decided when RM-03 or RM-34 is picked up.
