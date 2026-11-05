# TourneyHub — Roadmap

| | |
|---|---|
| Status | Draft |
| Date | 2026-10-14 |
| Scope | What comes after the MVP in `PRD.md`. Business level only: no dates and no technical design. |

## 1. Direction

The MVP serves groups the instance owner knows, on a single instance: organizers run game nights inside leagues and seasons, and everyone else follows a share link.

The bigger version is a hosted platform where any club can run leagues and tournaments for any sport or game. It gets there in three stages. Alongside them, a training track (§5) brings a club's training sessions onto TourneyHub.

- The stages are ordered; the items inside a stage are not. The training track has its own trigger and order (§5).
- A stage starts when its trigger happens, not on a date.
- When an item is picked up, it is written into `PRD.md` as requirements and removed from here.

## 2. Stage 1 — After the first season

**Starts when** a group has played a full season on the MVP.
**Goal:** deeper game nights for the first groups, on the same instance.

| ID | Item | What it means |
|---|---|---|
| RM-01 | Co-organizers | Someone else can run a night and enter results, and a league can be handed over to another organizer. |
| RM-02 | Email | Address verification, self-service password reset, and invitations for co-organizers. |
| RM-03 | Live updates | The share link updates by itself while matches are played. |
| RM-04 | Best N results | A season counts only each player's best N tournaments, so missed nights hurt less. |
| RM-05 | Double elimination (DKO) | A second kind of knockout, where an entry is out after its second loss — on its own or after any group phase. |
| RM-06 | Several groups | A group phase split into parallel groups that feed one knockout. |
| RM-08 | More tie-breakers | Further tie-breakers, and configurable ones in round robins. |
| RM-09 | Player pages | Each player's history, win rate and head-to-head records. |
| RM-10 | CSV export | A league's players, results and standings as a spreadsheet file. |
| RM-11 | Dark mode and accessibility | A dark theme, and every screen checked for accessibility. |

## 3. Stage 2 — Players join in

**Starts when** several groups play every week and players want to enter results themselves.
**Goal:** players take part as more than a name on a list.

| ID | Item | What it means |
|---|---|---|
| RM-12 | Player accounts | Players claim their name in a league and see their own history. |
| RM-13 | Self-reported results | Players enter their own results, and the opponent or the organizer confirms them. |
| RM-14 | Notifications | "Your match is next", new results and season news — by push, email, Discord or Slack. |
| RM-15 | Ratings | An Elo-style rating for each player across tournaments and leagues. |
| RM-16 | Persistent teams | Named teams that last across tournaments, teams of more than two, and substitutions. |
| RM-17 | Divisions | Parallel ladders in one league, with promotion and relegation. |
| RM-18 | Scheduling | Match times and venues, and names for fields (in the MVP a field is only a number). |
| RM-19 | Phone app | Installable on a phone, with result entry that works offline. |
| RM-20 | Easier, safer sign-in | Sign-in with Google, and two-factor authentication. |

## 4. Stage 3 — Many clubs

**Starts when** groups outside the instance owner's circle want in.
**Goal:** a hosted platform any club can sign up for.

| ID | Item | What it means |
|---|---|---|
| RM-21 | Clubs | Organizations with several leagues and staff roles, and many clubs on one hosted service. |
| RM-22 | Public leagues | Listing, search and following. |
| RM-23 | Entry fees and payments | Online payment of entry fees, refunds, and rules for unpaid entries. |
| RM-24 | Prizes and payouts | Prize pools, how they are split between places, and automated payouts. |
| RM-25 | Plans and billing | Subscriptions and limits for clubs, if the service charges. |
| RM-26 | Club branding | A club's logo, colours and own web address. |
| RM-27 | Other sports and games | Rule presets per sport, and matches with more than two sides, such as board games or racing. |
| RM-28 | Reports | Financial and season reports, including PDF. |
| RM-29 | Integrations | Webhooks, API keys, and plugins for new formats and scoring. |
| RM-30 | More languages | Languages beyond English and Czech. |
| RM-31 | Privacy self-service | Organizers delete their own account and download their data. Until then, the instance admin handles such requests by hand. |
| RM-32 | Large organizations | Data residency and single sign-on. |

## 5. Training track — Foos lab

**Starts when** the MVP runs on the VPS. It runs alongside the stages and pulls forward the parts of their items it needs.
**Goal:** a club runs its training sessions on TourneyHub, with Foos lab as their frontend. Training sessions are a kind of tournament inside a league kept for training, and the league ranks its players across them.

Foos lab is the training app of a table football club. It stays a separate application with its own frontend and becomes the first application built on TourneyHub's API. Until then it runs on its own database. Its PRD holds the training rules these items take over. `docs/foos-lab.md` maps its terms to TourneyHub's and records the decisions made so far.

| ID | Item | What it means |
|---|---|---|
| RM-33 | Training sessions | A session is a program of disciplines played round by round: drills, legs with special rules (a scenario start such as 0:3, a turnover counting as a goal for the opponent, one side holding a "wall"), singles, and a league-format match between two teams at the end. Everyone plays the same discipline in a round. Partners, opponents and who sits out to referee are balanced across the whole session. The organizer sets the length, picks the disciplines and their number of rounds, moves breaks between rounds and starts the session. |
| RM-34 | Time limits | In a training session, every match and drill has a limit: preparation plus the discipline's time, e.g. 1 + 8 minutes. When it runs out, the match ends with the score as it stands and the session goes on. The organizer sees the expected end of the session. Only in training sessions, and not for the team match. Time limits in other tournaments stay open. |
| RM-35 | Performance ladder | A league ranking from how players play instead of placement points: score difference, wins, goals for. Shown as totals or per game, over the season, the last 28 days, all time or a date range. Players with fewer than 2 tournaments in the range are listed but not ranked per game. Every tournament of the league counts, training sessions and ordinary tournaments alike. A season is one year of the club's league. Extends RM-09. |
| RM-36 | Drills and measurements | Drills at a field, two or three players at a time: each player records a result out of a number of attempts (e.g. goals from 10 shots). A ladder per drill, on the same ranges as RM-35. |
| RM-37 | Match course and waiting times | Every goal, turnover and drill attempt is recorded with its time. Each match shows how it went, and the league shows who keeps others waiting between a match becoming playable and its start. |
| RM-38 | Foos lab on TourneyHub's API | Foos lab keeps its own frontend and moves its data to TourneyHub: it reads and writes only through TourneyHub's API, the first application to do so. At first it still makes its own schedules. Its past sessions are imported once. Needs what RM-33 to RM-37 store, not yet their scheduling. Players entering results at their own table needs parts of RM-12 and RM-13, live updates need RM-03, and other applications on the API need part of RM-29. |

RM-38 can come before the scheduling parts of RM-33 to RM-37. Once those are in TourneyHub, Foos lab asks TourneyHub's API for its schedules instead of making them, and keeps its own frontend.
