# TourneyHub — MVP Product Requirements

| | |
|---|---|
| Status | Draft |
| Date | 2026-11-12 |
| Scope | MVP only. Business requirements only: technical decisions are recorded in `ADR.md` when they are made. |

## 1. Purpose

Clubs and groups of friends play regular game nights — board games, table football, racket sports, esports — and want to know who is winning the season. Today they use paper or spreadsheets: brackets are drawn by hand, partners are drawn from a hat, results get lost, and nobody can check the standings without asking the organizer.

The MVP lets an organizer run a league in seasons, play tournaments inside each season — alone, in pairs, or with drawn partners — enter results from a phone, and share read-only standings with the group. Its first users are groups the instance owner knows personally, on a single instance.

**The MVP succeeds when** a real group plays a full season on it — several tournaments, results entered at the table, players checking standings through the share link — without falling back to paper.

## 2. Users

| User | Account | What they do |
|---|---|---|
| **Organizer** | Yes | Creates leagues, keeps the player list, runs tournaments, enters results. |
| **Player** | No | A name on a league's player list. Sees results through the share link, like any viewer. |
| **Viewer** | No | Anyone with a league's share link. Read-only. |
| **Instance admin** | n/a | Runs the instance. Sets the sign-up code and resets forgotten passwords. |

## 3. Glossary

| Term | Meaning |
|---|---|
| League | A group that plays together over time, e.g. "Thursday Foosball". Owned by one organizer. |
| Season | A period of a league with its own standings. A league always has exactly one active season. |
| Tournament | One event inside a season, usually one evening. |
| Type | How the sides of a match are formed: **Singles** (1 vs 1), **Doubles** (2 vs 2, pairs set by the organizer), **DYP** or **Monster DYP**. |
| Phase | A tournament usually has two: a **group phase**, then a **knockout**. Either can be left out, but Monster DYP always has its group phase. |
| Swiss | Entries play round after round against the entry next to them in the standings, and no entry meets the same opponent twice while it can be avoided (BR-057). |
| DYP | "Draw Your Partner". Players enter alone and are drawn into pairs, one from the top half and one from the bottom half, for the whole tournament. |
| Monster DYP | Players enter alone. Every round, new 2 vs 2 teams are formed from the current standings, and each player collects their own points. |
| Group phase | **Round robin** (everyone plays everyone, once or twice), **Swiss**, or **Monster DYP** rounds. When a knockout follows, the group phase is its qualification. |
| Knockout | The elimination phase, played as single elimination (SKO): lose once and you're out. It follows the group phase or is the whole tournament. In Lord have mercy a player who is out can come in again as a replacement (BR-148). |
| Entry | Whoever takes a place in a tournament: a player in Singles and Monster DYP, a pair in Doubles and DYP (and in a pair knockout). |
| League ranking | The order of a league's players used for seeding and draws (BR-020). |
| Seed | An entry's position in the starting order. Seed 1 is treated as the strongest. |
| Bye | An empty spot in a first-round bracket match. The entry drawn against it gets a free win and goes through without playing. |
| Sit-out | A group-phase round an entry does not play because the numbers do not work out. |
| Walkover | A match won without being played, e.g. because the opponent left. |
| Match format | How many games a match has. **BO1**: one game. **BO2**: exactly two games, so 1:1 is a draw. **BO3** and **BO5**: best of three or five, so the first side to win 2 or 3 games wins the match. |
| Game | One game of a match, played to a number of goals, e.g. first to 10. A BO1 match is a single game. |
| Field | A place where one match is played at a time: a foosball table, a court, a board. A tournament's fields are numbered 1, 2, 3 … |
| On a field | A match that has a field and is being played there. |
| Waiting | A match whose two sides are known but that has no field yet. |
| Held | A waiting match the organizer took off its field. It takes no field by itself until the organizer places or releases it (BR-136). |
| Late player | A player — in Doubles, a pair — added after the tournament has started (BR-067). |
| Disabled | A player or pair the organizer has taken out of new rounds for now. In a Lord have mercy knockout a disabled player who is still in is replaced or, with nobody to come in, stays in the draw; a disabled player who is knocked out is only skipped as a replacement (BR-147–BR-149). |
| Top players | In Monster DYP, the players kept apart in rounds 1 and 2. |
| BH1, BH2 | Buchholz tie-breakers. BH1 sums the points of an entry's opponents; BH2 sums those opponents' BH1. |
| Game difference | Games won minus games lost, over every match with a result. A drawn BO1 game counts as neither, and a walkover counts the games needed to win the match format: BO1 1:0, BO2 2:0, BO3 2:0, BO5 3:0. |
| Score difference | Goals for minus goals against, over every game with an entered score. |
| Place | An entry's finishing position in a tournament. Several entries can share a place. In a Lord have mercy knockout each player has a place of their own (BR-145). |
| Placement points | Season points a player earns for their place in a finished tournament. |
| Tournament win | Finishing 1st in a tournament — including a shared 1st, and as either player of the winning pair. |

## 4. Scope

### 4.1 In the MVP

1. Organizer accounts, with self sign-up behind a sign-up code.
2. Leagues with a player list.
3. Seasons with season standings, and a league ranking built from them.
4. Tournament types: Singles, Doubles, DYP and Monster DYP.
5. Tournaments in two phases, either of which can be left out: a group phase — round robin (once or twice), Swiss or Monster DYP rounds — then a single-elimination knockout (optional third-place match). Swiss and Monster DYP rounds go on for as long as the organizer wants.
6. Seeding by league ranking or random shuffle, adjustable by hand; generating brackets, schedules and rounds; adding and deleting rounds, late players and disabling players; result entry and corrections.
7. Group-phase points (2 / 1 / 0, and 0, 1 or 2 points for sitting out in Swiss and Monster DYP), tie-breakers (head-to-head, game difference and score difference in a round robin; score difference, BH1 and BH2 in Swiss and Monster DYP), and season standings from placement points.
8. A read-only share link per league.
9. English and Czech UI, usable on a phone.
10. Match formats BO1, BO2, BO3 and BO5, chosen per phase, with an optional different format for the final.
11. Fields: the organizer sets how many fields a tournament has. Matches go to free fields in schedule order and the rest wait. During the tournament the organizer adds and removes fields and puts matches on the field they want.

### 4.2 Not in the MVP

Player accounts and players reporting their own results · co-organizers and transferring a league · organizations and multi-tenancy · teams of more than two, and named teams that last across tournaments · entry fees, prizes and payments · live updates (viewers refresh the page) · email of any kind (verification, password reset, invitations) · public listing, search and following · statistics beyond standings · data export and account deletion · double elimination (DKO) knockouts · group phases split into several groups · other tie-breakers, and configurable ones in a round robin · match times and venues · names for fields (a field is only a number).

Each of these is on the roadmap (`ROADMAP.md`).

## 5. Example evenings

### 5.1 A DYP evening

1. An organizer gets the sign-up code from the instance admin and signs up.
2. They create the league "Thursday Foosball". Season 1 starts automatically.
3. They add the regulars to the player list.
4. On Thursday, 12 players come. The organizer creates a DYP tournament with a round robin. The 6 best-ranked players form the top half, the other 6 the bottom half, and each top-half player is drawn a bottom-half partner.
5. Generating creates the round-robin schedule: 6 pairs, 5 rounds, 15 matches, all BO1. The bar has two foosball tables, set up as Field 1 and Field 2, so two matches of round 1 start and the third waits.
6. The organizer enters each result on their phone as matches finish, and each freed field takes the next waiting match. Halfway through, a third table frees up and the organizer adds it as Field 3. When the round robin is complete, they start a knockout for the top 4 pairs, without a third-place match: 1st v 4th and 2nd v 3rd, with a BO3 final. The bracket advances by itself.
7. When the final is entered, the tournament finishes. Both players of the winning pair get 10 points and the runners-up 8 each. The two pairs that lost the semifinals share 3rd, so their four players split the points for 3rd and 4th: (6 + 4) / 2 = 5 each. The two pairs that did not qualify are 5th (2 points each) and 6th (0). The season standings update.
8. Players open the league's share link to see the round robin, the bracket and the season standings.

### 5.2 A Monster DYP night

1. 14 players come. The organizer creates a Monster DYP and is shown a recommendation of at least 4 rounds. Points for sitting out stay at their default, 0 (FR-039).
2. Round 1: 12 players play in 3 matches and 2 sit out. The 3 best-ranked of the 12 who play are in different matches.
3. After round 1 a late player arrives. The organizer adds them, and they play from round 2, starting on 0 points.
4. Whenever every match of a round has a result, the organizer adds the next round. A win is worth 2 points, a draw 1.
5. After round 3 one player leaves for a while. The organizer disables them, and re-enables them before round 5.
6. After round 5 the organizer decides the group phase is over and starts a "Seeded pairs" knockout for the top 8: #1 + #5, #2 + #6, #3 + #7 and #4 + #8.
7. The knockout decides places 1–3: the winning pair is 1st, the runners-up 2nd, and the two semifinal-losing pairs share 3rd. The other 7 players follow in their Monster DYP order, from 5th to 11th.

After ten weeks of evenings like these, the organizer starts Season 2. Season 1 stays visible, read-only.

## 6. Functional requirements

### 6.1 Accounts

| ID | Requirement |
|---|---|
| FR-001 | A person signs up as an organizer with email, display name, password and the instance's sign-up code. Without the correct code, sign-up fails. |
| FR-002 | Passwords have 15 to 1024 characters. An email address can belong to only one account. |
| FR-003 | Organizers log in with email and password and stay logged in on that device until they log out. A device not used for 90 days is logged out; each use restarts the 90 days. |
| FR-004 | A logged-in organizer can change their password. They enter their current password, and the new one must differ from it. The change logs them out on every other device; the device they changed it on stays logged in. |
| FR-005 | The instance admin can set or change the sign-up code. Changing it does not affect existing accounts. |
| FR-006 | The instance admin can set a new password for an organizer who forgot theirs. This logs the organizer out on every device, and after their next login they must choose a new password before they can do anything else. There is no self-service reset in the MVP. |
| FR-007 | An organizer's home page lists their leagues. A dropdown in the header switches between them. Organizers can manage only their own leagues. |

### 6.2 Leagues and players

| ID | Requirement |
|---|---|
| FR-010 | An organizer creates a league with a name. Creating it also starts Season 1. |
| FR-011 | League settings: name; whether draws are allowed in group phases (default: not allowed); the defaults for new tournaments — number of fields (1), match format (BO1, BO3 or BO5; default BO1) and goals per game (10); and the placement points table. The default is 10, 8, 6, 4, 2 for 1st–5th, kept small so that a player who misses a few tournaments can still catch up. Points are whole numbers, and no place is worth more than the place above it. |
| FR-012 | The organizer adds players to the league's player list by name, renames them, removes them and restores removed players (BR-001, BR-002, BR-005, BR-006). A rename shows everywhere, including past results. A removed player's name stays taken, so adding the name of a removed player is refused, and the organizer restores that player instead. A restore therefore always works, as long as the league is under its player limit (BR-006). When a removal is refused (BR-002), the app lists the tournaments that block it. |
| FR-013 | The organizer can delete a league after confirming. Everything in it is deleted. |

### 6.3 Seasons

| ID | Requirement |
|---|---|
| FR-020 | Seasons are named "Season 1", "Season 2", … by default and can be renamed. |
| FR-021 | Starting a new season closes the current one (BR-010). |
| FR-022 | Closed seasons stay visible, read-only, with their tournaments and final standings. |

### 6.4 Tournaments

| ID | Requirement |
|---|---|
| FR-030 | The organizer creates a tournament in the league's active season with a name of 1 to 100 characters, a date (default: today) and a type: Singles, Doubles, DYP or Monster DYP. Setup also sets the number of fields, the match format of each phase it creates and the goals per game, starting from the league's defaults (FR-011). A knockout after a group phase gets its match format when it starts (FR-045), prefilled from the league's default; the final plays that format unless the organizer gives it one of its own (BR-120). The organizer can change the knockout's format while it has no result, and the final's while the final has no result (FR-054). "Cancel" in the setup wizard keeps the tournament in setup; deleting it is a separate step (FR-038). |
| FR-031 | A tournament usually has a group phase followed by a knockout, but either can be left out. Singles, Doubles and DYP choose a group phase — round robin (once or twice), Swiss or none; Monster DYP always plays its own rounds (§7.8). Without a group phase, the tournament is a knockout from the start, with or without a third-place match. After a group phase, the organizer decides whether a knockout follows (FR-040). |
| FR-032 | The organizer picks the players from the league's player list. There must be at least 2 entries, or 4 with a third-place match; Monster DYP needs at least 4 players. A round robin takes at most 16 entries, and a late entry cannot take it past 16. The other formats have no maximum; if a technical limit is ever needed for them, it must still allow 256 entries in a tournament and 20 rounds in a group phase. The schedule made at the start of a round robin of N entries has N−1 rounds when played once, or N with an odd count, and twice as many when played twice (BR-051, BR-052); a late entry adds rounds (BR-054). |
| FR-033 | Doubles: the organizer puts the players into pairs. DYP: the players are split into a top and a bottom half — by the league ranking or by hand — and the pairs are drawn (BR-031–BR-033). |
| FR-034 | The first phase of a Singles, Doubles or DYP tournament is seeded by league ranking (default) or random shuffle, and the organizer can then reorder the seeds by hand. A knockout after a group phase is seeded by the group-phase places (§7.11). |
| FR-035 | Generating creates the bracket, the round-robin schedule, or the first round of a Swiss or Monster DYP, and starts the tournament. |
| FR-036 | While no match in the tournament has a result (BR-096), the organizer can go back to setup, change anything — including a new DYP draw — and generate again. "Back to setup" is in the tournament's menu in the tournament list and in the menu of the tournament's header. |
| FR-037 | A tournament with a knockout finishes automatically when every knockout match has a result. A Lord have mercy knockout draws its rounds one at a time (BR-140), so there the tournament finishes when the final has a result and, if the knockout has a third-place match, that match too. A tournament without a knockout finishes when the organizer finishes it after the group phase (FR-040). |
| FR-038 | The organizer can delete a tournament after confirming, unless its season is closed. |
| FR-039 | Swiss and Monster DYP have a setup setting, **points for sitting out**: 0, 1 or 2 (BR-071, BR-075–BR-077). The default is 0. Setup does not show it for a round robin, which has no points for sitting out (BR-071). |

### 6.5 Group phase and knockout

| ID | Requirement |
|---|---|
| FR-040 | Swiss and Monster DYP have no set number of rounds: once every match in the current round has a result, the organizer adds the next round, starts the knockout (FR-045) or finishes the tournament after confirming. The organizer sees a recommended minimum number of rounds (BR-068) but can stop earlier or play on. A round robin offers the same choice — knockout or finish — once all its matches have results. |
| FR-041 | Monster DYP: the top players are the players the organizer marked in a step of the tournament setup, filled up from the league ranking (BR-061). The organizer can mark at most one player per match of round 1; when a later round has fewer matches, the marked players who play count in league-ranking order (BR-061). |
| FR-042 | Each new round is drawn from the current standings (§7.7, §7.8), leaving out disabled players (BR-064). |
| FR-043 | For a Swiss or Monster DYP, the organizer switches each tie-breaker — score difference, BH1, BH2 — on or off and puts them in order. Default: BH1, then BH2, then score difference. |
| FR-044 | In a Swiss or Monster DYP, the organizer can disable any player — in Doubles and DYP, a pair — and re-enable them later (BR-064). In a Lord have mercy knockout, they can also disable a player who has left or gone home, and re-enable them later (BR-147). |
| FR-045 | When starting the knockout, the organizer picks how many entries qualify, whether there is a third-place match (BR-080) and the match format of the knockout and the final (FR-030). After a round robin or Swiss, the qualifying entries play as they are. After Monster DYP rounds, the knockout is formed in one of four ways: **Seeded pairs**, **Singles**, **A little mercy** or **Lord have mercy** (§7.11). For A little mercy and Lord have mercy, where the pairs are drawn by lot, the organizer sees the drawn pairs on the start-knockout screen and can draw them again before starting the knockout (BR-083, BR-084). |
| FR-046 | The organizer can delete the newest round of a Swiss or Monster DYP, or a knockout that follows a group phase, with any results in it (BR-066, BR-087). Deleting round 1 of a Swiss or Monster DYP takes the tournament back to setup. In a Lord have mercy knockout the organizer can also delete its newest round (BR-146); deleting its first round deletes the knockout (BR-087). |
| FR-047 | The organizer can add late players from the league's player list — in Doubles, a pair — to any group phase except DYP: between rounds of a Swiss or Monster DYP, and until a round robin is complete (BR-054, BR-067). The organizer can add several late entries in one step (BR-054). A knockout without a group phase takes them only in place of a bye (BR-045); a knockout after a group phase takes none. |
| FR-048 | Before a late player joins a Swiss or Monster DYP that uses BH1 or BH2, the organizer is warned that it may be unfair: the rounds the late player missed earned no points, so everyone who meets them afterwards gets a lower BH. The organizer can go ahead anyway. |
| FR-049 | In a Lord have mercy knockout, once every match of a knockout round has a result, the organizer draws the next round (BR-140). Before the draw is stored, the organizer sees which players come in as replacements and which stay in the draw without one (BR-149, BR-157), and can skip a player who is not there by disabling them (BR-147, BR-148). |

### 6.6 Results

| ID | Requirement |
|---|---|
| FR-050 | The organizer enters a result for each match: a winner, or a draw where allowed (BR-090). In BO2, BO3 and BO5 the result is the number of games each side won, e.g. 2:1, entered game by game. |
| FR-051 | A result can include the score of each game — goals for each side, in whole numbers. Swiss and Monster DYP rounds require them (BR-092). Without game scores, the organizer picks the winner of each game. |
| FR-052 | A match can be recorded as a walkover: a winner, with no score. |
| FR-053 | The organizer can change or clear a result, subject to BR-011, BR-053, BR-065 and BR-094; in a Lord have mercy knockout, BR-146 replaces BR-094. |
| FR-054 | The organizer can change a phase's match format while the phase has no result (BR-096). The final's format can change while the final has no result (BR-096). |

### 6.7 Standings

| ID | Requirement |
|---|---|
| FR-060 | Every tournament shows its standings, which update as results come in (§7.13). Swiss and Monster DYP standings also show BH1, BH2, score difference and sit-outs. The sat-out column counts sit-outs only, not missed rounds (BR-064, BR-067). |
| FR-061 | Every season shows season standings: each player who has played in a finished tournament of the season, with their total placement points, tournaments played and tournament wins (§7.14). |

### 6.8 Sharing

| ID | Requirement |
|---|---|
| FR-070 | Every league has a share link. Without an account, anyone with it can see the league, all its seasons, closed ones included, with their season standings, and each tournament's bracket or rounds, results and standings. A running tournament's schedule shows which match is on which field and which matches are waiting, each waiting match with its round. Tournaments still in setup are visible only to the organizer. |
| FR-071 | The link cannot be guessed, and leagues are not listed or searchable anywhere. |
| FR-072 | Viewers cannot change anything. |

### 6.9 Language and devices

| ID | Requirement |
|---|---|
| FR-080 | The whole UI is available in English and Czech. Names entered by organizers are shown as entered, and the knockout options (§7.11) keep their English names in both languages. |
| FR-081 | Organizers choose their language and it is saved to their account, so every device they log in on uses it. Viewers get their browser's language if it is English or Czech, otherwise English, and can switch. The language switch is a dropdown in the header that lists the available languages, so that more can be added later (RM-30). Dates follow the chosen language's format. |
| FR-082 | Every screen works on a phone. Entering a result takes at most three taps from the bracket, schedule, round or field — open the match, choose the result, save — plus entering scores. In BO2, BO3 and BO5, choosing the result takes one tap per game played. |
| FR-083 | Every screen has a light and a dark theme. The app follows the device's setting; there is no manual switch in the MVP. |

### 6.10 Fields

| ID | Requirement |
|---|---|
| FR-090 | Every tournament has at least one field. The organizer sets how many in setup and can add or remove fields at any time while the tournament runs (BR-132). |
| FR-091 | A field is shown as "Field" and its number. Names for fields are not in the MVP. |
| FR-092 | Matches go onto free fields by themselves (BR-130). Matches that could be played but have no field are shown as waiting, in the order in which they will get one. A held match (BR-136) is listed among them, marked "held", but is skipped while it is held. |
| FR-093 | The organizer can put a waiting match on a free field, move a match to another free field, swap the matches on two fields, or take a match off its field and back to waiting (BR-133). A match taken off its field is held, and the waiting list marks it "held". The organizer can release a held match (BR-136). |
| FR-094 | Entering a match's result frees its field, which takes the next waiting match. The organizer can also enter a result for a waiting match, for example one played somewhere else; that match then never takes a field. |

### 6.11 Privacy

| ID | Requirement |
|---|---|
| FR-100 | From the pilot on, the instance, its database and its backups are hosted in the EU. This is settled before the pilot starts and holds for as long as the instance runs. |
| FR-101 | A "Privacy" page in English and Czech is linked from the footer of every page and from sign-up. It says who the data controller is, what data is stored, why, for how long, what rights people have, and that a share link makes players' names and results public. |
| FR-102 | Before a league's share link is first shown, the organizer confirms that the league's players know the link makes their names and results public. |
| FR-103 | The app sets only the cookie needed to stay logged in. A viewer's choice of language is kept in the browser's localStorage (FR-081, ADR-003). Both are necessary for the app to work, so no consent is needed and there is no cookie banner. |
| FR-104 | Until organizers can delete their own data (RM-31), the instance admin deletes an account or a league on request, by hand. A player's request to be erased goes to the organizer, who entered the player. The organizer can rename the player to a neutral name (FR-012); the tournaments' results, places and points stay. Removing the player (BR-002) alone keeps the name. |

## 7. Business rules

### 7.1 Players

| ID | Rule |
|---|---|
| BR-001 | Player names are unique within a league, ignoring upper and lower case. |
| BR-002 | A player who is in an unfinished tournament, including one still in setup, cannot be removed. A removed player keeps their past results, places and points but cannot be picked for new tournaments. |
| BR-003 | A player is in a tournament at most once; in Doubles and DYP, in exactly one pair. |
| BR-005 | A player's name has 1 to 100 characters. Leading and trailing spaces are dropped, runs of spaces count as one space, and invisible characters are refused. Upper and lower case do not make names different (BR-001). Names that only look alike, such as a Latin and a Cyrillic "a", are different names; they are not merged. |
| BR-006 | A league has at most 1000 players on its list. Removed players do not count; restoring one counts them again. |

### 7.2 Seasons and settings

| ID | Rule |
|---|---|
| BR-010 | A new season cannot start while any tournament in the current season is unfinished, including one still in setup. The organizer finishes or deletes it first. |
| BR-011 | Nothing in a closed season can change: no new tournaments, results, corrections or deletions. Renaming the league, the season or a player, and deleting the whole league, still apply. |
| BR-012 | Changing the placement points table recalculates the active season's standings; a closed season keeps the table it was played under. |
| BR-013 | Turning draws off does not change results already entered. BR-125 says when it is refused. |

### 7.3 League ranking and seeding

| ID | Rule |
|---|---|
| BR-020 | The league ranking orders the league's players by current season points, then the tournaments they won this season, then their final place last season (players without one come after those with one), then by lot. It reflects the standings at the moment it is used. Removed players are left out of the ranking, so the position sums of BR-021 skip them. |
| BR-021 | Seeding by league ranking: singles follow the ranking. Pairs are ordered by the sum of their two players' positions in the whole league ranking, not renumbered among the tournament's players, lowest first; on equal sums, the pair with the better-ranked player goes first. |
| BR-022 | Random shuffle orders the entries by lot. |

### 7.4 Doubles and DYP

| ID | Rule |
|---|---|
| BR-030 | In Doubles and DYP, a pair is two different players who stay together for the whole tournament and share its results and place. |
| BR-031 | DYP needs at least 4 players. With an odd number, one player is left out and does not play in the tournament (BR-032). |
| BR-032 | DYP halves by league ranking: with an odd number, a player drawn by lot is left out, and the top half is the better-ranked half of the rest. By hand: the organizer puts every player in a half, leaving one out with an odd number, and both halves must be the same size. |
| BR-033 | Each top-half player is drawn a partner at random from the bottom half. |

### 7.5 Knockout

| ID | Rule |
|---|---|
| BR-040 | The bracket is the smallest power of two that fits all entries (7 entries → 8). The empty spots are byes. |
| BR-041 | Byes go to the top seeds, one per seed, so byes occur only in the first round and no match is ever bye against bye. A bye is not a match: the entry goes straight to the next round. |
| BR-042 | Seeds are placed so the strongest meet as late as possible: seeds 1 and 2 can meet only in the final, and seeds 1–4 can meet one another only in the semifinals or later. |
| BR-043 | There are no draws. The winner of each match goes through; the loser is out. In Lord have mercy, a player who is out can come in again as a replacement (BR-148). |
| BR-044 | With a third-place match, the two semifinal losers play it. In Lord have mercy, their four players are paired again for it (BR-144). |
| BR-045 | A generated bracket cannot be edited by hand, with one exception: in a Singles or Doubles knockout without a group phase, a late entry can take the place of a bye until every first-round match has a result, as long as the entry with the bye has no second-round result yet. The two then play a normal first-round match. |

### 7.6 Round robin

| ID | Rule |
|---|---|
| BR-050 | Every entry plays every other entry once, or twice if the organizer chose twice. |
| BR-051 | Matches are grouped into rounds, and no entry plays twice in a round. In the schedule made at the start, seeds 1 and 2 meet in the last round, as the last match of that round; when played twice, the same holds in each half (BR-052). With an odd number of entries, one sits out each round and every entry sits out the same number of times. After a late entry, BR-054 governs the rescheduled rounds: with 4 entries and a 5th joining after round 2, entries 1–4 sit out twice and the 5th never. |
| BR-052 | When played twice, the second half repeats the first half's pairings, round by round. After a late entry, BR-054 governs the matches not yet played. |
| BR-053 | A round robin's results lock when the knockout is drawn. |
| BR-054 | A late entry in a round robin plays every other entry as often as everyone else does. The matches not yet played are rescheduled to fit its matches in; results already entered stay. When played twice, BR-052 holds only for the matches before the reschedule: the matches not yet played follow BR-054, and a repeat order is kept only where BR-054 leaves it unchanged. The reschedule prefers, in this order: (1) fewer rounds; (2) a shorter longest run of rounds that any entry sits out in a row, counting the rounds already played (rounds that already had a result when the late entry joined are not its sit-outs); (3) when played twice, the late entry meeting every other entry once before it meets any of them a second time; (4) the last unplayed match of seeds 1 and 2 in a later round, as the last match of that round (BR-051); (5) fewer already scheduled matches moved to a different round; when a pair has two matches not yet played, a match counts as moved only for a scheduled round in which the pair no longer plays; (6) the late entry's opponents compared round by round, the better seed first, where a round the late entry sits out counts after every opponent; (7) the matches without a late entry compared round by round, each round's matches from the best seed down, a round with fewer of them counting after. With 4 entries and a 5th joining after round 2, four more rounds are needed (6 in all), and with 1 v 2 in round 6 some entry would sit out two rounds in a row, so 1 v 2 is played in round 5 of 6. The schedule is then: round 3: 5 v 1; round 4: 5 v 2, 3 v 4; round 5: 5 v 3, 1 v 2; round 6: 5 v 4. Entries added in one step are fitted in one after another, in league-ranking order (BR-020, and BR-021 for pairs), each by the reschedule for one late entry, so the order of picking does not matter; the organizer and the viewers see only the result, so the schedule changes once. Entries added in separate steps get one reschedule each, in the order added. Late entries take the next seeds, in that order. Matches with a result do not move. A match on a field stays on its field. When played twice, with 4 entries and a 5th joining after round 2, eight more rounds are needed (10 in all), and the late entry meets 1, 2, 3, 4, 1, 2, 4, 3: round 3: 5 v 1, 3 v 4; round 4: 5 v 2, 1 v 4; round 5: 5 v 3, 2 v 4; round 6: 5 v 4, 1 v 2; round 7: 5 v 1, 2 v 3; round 8: 5 v 2, 3 v 4; round 9: 5 v 4, 1 v 3; round 10: 5 v 3, 1 v 2. Entries 1–4 each sit out twice, never two rounds in a row. |

### 7.7 Swiss

| ID | Rule |
|---|---|
| BR-055 | Round 1 pairs the top half of the seeds against the bottom half: seed 1 plays seed N/2 + 1, seed 2 plays seed N/2 + 2, and so on (8 entries: 1 v 5, 2 v 6, 3 v 7, 4 v 8). |
| BR-056 | From round 2, entries are ordered by current standing and play their neighbour: 1st v 2nd, 3rd v 4th, and so on. An entry that has already played its neighbour plays the next entry down that it has not played. |
| BR-057 | No entry meets the same opponent twice while it can be avoided. |
| BR-058 | With an odd number of entries in a round, one sits out. Entries that did not sit out the round before are picked to sit out first; among them, the one with the fewest sit-outs so far; among those, the one whose sitting out leaves the fewest repeat opponents in the round (BR-057); and then the lowest-placed; remaining ties by lot (BR-074). A missed round counts as a sit-out here (BR-064, BR-067). In round 1, before any result, the lowest seed sits out, and the others are paired by BR-055 (7 entries: seed 7 sits out, then 1 v 4, 2 v 5, 3 v 6). Disabled entries do not count and are not picked. |

### 7.8 Monster DYP rounds

| ID | Rule |
|---|---|
| BR-060 | Every round, players are grouped in fours by their current standing — in round 1, by the league ranking. In each group, the 1st and 4th play the 2nd and 3rd (#1 + #4 vs #2 + #3). |
| BR-061 | There are as many top players as matches in a round. In rounds 1 and 2 they are in different groups, and the other players fill the groups in standing order (16 players, top 4: #1 #5 #6 #7 · #2 #8 #9 #10 · #3 #11 #12 #13 · #4 #14 #15 #16). Top players are not exempt from sitting out: the sit-outs are chosen before the top players (BR-063), and the top players are taken from the players who play, in this order: the players marked by the organizer (FR-041), then the others, each in league-ranking order. A top player who sits out or is disabled is replaced by the next one, so every group has exactly one. The number of top players follows each round's number of matches, so it changes when a late or disabled player changes the number of matches between rounds 1 and 2. |
| BR-062 | Nobody gets the same partner twice while it can be avoided; the grouping changes as little as needed to avoid it. |
| BR-063 | When the number of players is not divisible by 4, the extra one to three players sit out the round. Players who did not sit out the round before are picked to sit out first; among them, those who have sat out the fewest times, and remaining ties are decided by lot. A missed round counts as a sit-out here (BR-064, BR-067). Disabled players do not count and are not picked. For example, 6 players play 6 rounds, and each has sat out twice. A 7th player arrives and counts 6 sit-outs. From round 7, three sit out each round: the 7th plays rounds 7 to 14, and the other six sit out every second round. After round 14 all seven count 6, and in round 15 the lot can pick the 7th for the first time. |

### 7.9 Round by round (Swiss and Monster DYP)

| ID | Rule |
|---|---|
| BR-064 | A disabled player or pair is not drawn into new rounds. Their results and points stay; rounds they miss earn 0 and no points for sitting out (BR-071, BR-076, BR-077). For the sit-out order only (BR-058, BR-063), each missed round counts as a sit-out. Once re-enabled, they are in the draw from the next round. At the end they are placed by their standing. In a Lord have mercy knockout, §7.17 applies instead of this rule. |
| BR-065 | A round's results can be changed until the next round or the knockout is drawn; after that they are locked. |
| BR-066 | Deleting the newest round removes its matches and results and unlocks the round before it. |
| BR-067 | In a Swiss or Monster DYP, a late player starts on 0 points and is in the draw from the next round; rounds they missed earn 0 and no points for sitting out (BR-071, BR-076, BR-077). For the sit-out order only (BR-058, BR-063), each missed round counts as a sit-out. A round robin fits a late entry into its schedule (BR-054), and a knockout without a group phase only lets one take a bye (BR-045). DYP takes no late players, because its pairs are drawn at the start, and neither does a knockout after a group phase, whose qualifiers are fixed. |
| BR-068 | The recommended minimum number of rounds is log₂ of the number of entries, rounded up — the usual Swiss minimum, after which at most one entry can have won every match. Monster DYP counts players. 5–8 entries → 3 rounds, 9–16 → 4, 17–32 → 5. Only active entries count: late players from when they join, and disabled ones not while they are disabled. |

### 7.10 Group-phase points and standings

| ID | Rule |
|---|---|
| BR-070 | In round robin, Swiss and Monster DYP rounds, a win is worth 2 points, a draw 1 and a loss 0. In Monster DYP, both players of a team get the points. |
| BR-071 | In Swiss and Monster DYP, a sit-out is worth the tournament's points for sitting out: 0, 1 or 2 (FR-039). A round-robin phase has no points for sitting out: in a complete round robin every entry sits out equally often (BR-051), and with a late entry (BR-054) the points would distort the order. When the group phase is no longer a Swiss or a Monster DYP, the setting is dropped, a picked value included; switching back starts from the default (FR-039). |
| BR-072 | Swiss and Monster DYP: entries level on points are ordered by the enabled tie-breakers, in the organizer's order (FR-043). |
| BR-073 | BH1 is the sum of the current points of every opponent faced, counted once per match. BH2 is the sum of those opponents' BH1. Score difference is goals for minus goals against over all games. Sit-outs add nothing to BH1 or BH2, and score difference counts only entered game scores. |
| BR-074 | Entries still level share the place. Where a strict order is needed — pairing the next round, or the knockout's cut and seeding — the lot decides. |
| BR-075 | The organizer picks the points for sitting out, 0, 1 or 2, in setup (FR-036). While the phase has a result (BR-096), the value cannot change. |
| BR-076 | Sit-out points count as points in the standings (BR-072). |
| BR-077 | In Monster DYP, each player who sits out a round (BR-063) gets the points for sitting out. |

### 7.11 From group phase to knockout

| ID | Rule |
|---|---|
| BR-080 | The best entries in the standings qualify, as many as the organizer picks. Disabled entries do not qualify; the next ones move up. A knockout needs at least 2 entries, or 4 with a third-place match, and the Monster DYP pair options need an even number of qualifiers. |
| BR-081 | **Seeded pairs** (Monster DYP): with N qualifiers, 1st partners the (N/2 + 1)th, 2nd partners the (N/2 + 2)th, and so on — with 16: #1 + #9, #2 + #10 … #8 + #16. Pairs are seeded by their better player's place. |
| BR-082 | **Singles** (Monster DYP): qualifiers play 1 vs 1, seeded by their place. |
| BR-083 | **A little mercy** (Monster DYP): qualifiers are split into a top and a bottom half by place, and each top-half player is drawn a partner from the bottom half. Pairs are seeded by their better player's place. |
| BR-084 | **Lord have mercy** (Monster DYP): qualifiers are paired completely at random and placed in the bracket by lot, ignoring the standings. The pairs are mixed again before every later round (§7.17). |
| BR-085 | After a round robin or Swiss, the qualifying entries play on as they are — players in Singles, pairs in Doubles and DYP — seeded by their place. |
| BR-086 | Knockout pairs stay together until the end, except in Lord have mercy (§7.17). The knockout follows §7.5, including the optional third-place match, but takes no late entries. |
| BR-087 | Deleting the knockout unlocks the group phase — all of a round robin's results, or the newest round of a Swiss or Monster DYP — and the organizer chooses again what comes next (FR-040). |

### 7.12 Results

| ID | Rule |
|---|---|
| BR-090 | Draws are possible only in group phases, and only if the league allows draws: a BO1 game with equal scores, or a BO2 match won 1:1. Knockouts have no draws. |
| BR-091 | A match gets a result only once both of its sides are known. |
| BR-092 | Scores, if entered, must agree with the result: the winner of a game has the higher score, a drawn BO1 game has equal scores, and the games won must match the game scores. Swiss and Monster DYP round matches need a score for every game played, except walkovers. |
| BR-093 | A walkover counts as a normal win and loss everywhere. |
| BR-094 | In a knockout, a result is locked once any later match it feeds has a result: the next match for its winner and, for a semifinal with a third-place match, that match for its loser. That later result must be cleared first. Changing a winner updates the sides of the later matches. In Lord have mercy, the later sides are drawn, not fed, so BR-146 applies instead. |
| BR-095 | Clearing a result in a finished tournament puts it back in progress. So does deleting its knockout or its newest knockout round (FR-046). |
| BR-096 | A phase, a final or a whole tournament has no result while none of its matches has one. It has none again once every result in it is cleared (FR-053), and a phase also once its round 1 is deleted (FR-046). |

### 7.13 Tournament places

| ID | Rule |
|---|---|
| BR-100 | Places belong to entries. Every player in an entry gets the entry's place. In a Lord have mercy knockout, places are per player (BR-145). |
| BR-101 | Round robin: entries are ranked by the points of their matches (BR-070), with played, won, drawn, lost, sat out, game difference, score difference and points shown; a round robin has no points for sitting out (BR-071). When exactly two entries are level, the one with more points from the matches between them ranks higher. Entries still level are ordered by game difference (a walkover counts the games needed to win the format, as in the glossary), then by score difference, counting only entered scores, and after that share the place (BR-074). This order applies in every match format. When the standings note that head-to-head decided between two entries that met twice, the note shows both results. A sit-out counts in the sat-out column once every match of its round has a result. The game-difference column is shown only when the phase plays BO3 or BO5: in BO1 and BO2 it follows from won and lost, which the table already shows, and it costs width on a phone (FR-082). |
| BR-102 | Knockout: the winner is 1st and the final's loser 2nd. With a third-place match, its winner is 3rd and its loser 4th; without one, the two semifinal losers share 3rd. Entries knocked out in the same earlier round share a place: quarterfinal losers share 5th, round-of-16 losers share 9th, and so on. |
| BR-103 | With a group phase but no knockout, the group-phase standings are the places. With both, the knockout entries take the top places by BR-102 (in Lord have mercy, the knockout's players by BR-145), and the other entries follow in their group-phase order, numbered after the knockout entries: after 8 knockout pairs, the best non-qualifier is 9th. |
| BR-104 | After a shared place, numbering skips accordingly: two entries sharing 3rd are followed by 5th. |

### 7.14 Season standings

| ID | Rule |
|---|---|
| BR-110 | When a tournament finishes, each player in it earns the placement points for their place from the league's table. Places beyond the table earn 0. |
| BR-111 | Entries sharing a place split the points of the places they cover: each gets the average, rounded down. With the default table, two pairs sharing 3rd cover 3rd and 4th, so each of their four players gets (6 + 4) / 2 = 5; four entries sharing 5th get (2 + 0 + 0 + 0) / 4 = 0.5, rounded down to 0. |
| BR-112 | Only finished tournaments count. Correcting a result in a finished tournament, putting it back in progress (BR-095) or deleting the tournament recalculates the season standings. |
| BR-113 | Season standings rank players by total placement points, then tournament wins. Players still level share the place. |

### 7.15 Match formats

| ID | Rule |
|---|---|
| BR-120 | Each phase has one match format: BO1, BO2, BO3 or BO5, BO1 by default. The final plays the knockout's format unless the organizer gives it one of its own, for example BO5; the third-place match plays the knockout's format. |
| BR-121 | BO1 is one game. BO2 is always two games: 2:0 is a win and 1:1 a draw, so BO2 is offered only in group phases of leagues that allow draws. In BO3 and BO5 the first side to win 2 or 3 games wins the match, and the remaining games are not played. |
| BR-122 | Group-phase points come from the match result, not from games: a win is 2, a draw 1, a loss 0 (BR-070), whatever the format. |
| BR-123 | Goals per game (default 10) sets how many goals the score counter shows. It is a guide, not a rule: other whole-number scores can still be entered, and the organizer can change it at any time, also while the tournament runs. When no side of a game reached it, such as 5:3 with 10, the app warns but saves the score. |
| BR-124 | A walkover in BO2, BO3 or BO5 gives the winner the match with no game scores. |
| BR-125 | Draws cannot be turned off while the league has an unfinished tournament, including one still in setup, whose group phase plays BO2: without draws, BO2 has no valid result for 1:1 (BR-121). The organizer first finishes or deletes it, or changes its format while FR-054 allows it. |

### 7.16 Fields

| ID | Rule |
|---|---|
| BR-130 | A match can take a field once both its sides are known and none of its players is on another field. A free field takes the first such match in schedule order: in a round robin by round and then by match, so a later round's match can start while the current round finishes; in Swiss and Monster DYP within the current round; in a knockout by round, top of the bracket first; in a Lord have mercy knockout by round, in the order the lot placed the pairs (BR-084, BR-141). In every knockout the third-place match comes after the final. |
| BR-131 | Nobody plays on two fields at once. A match whose players are still on another field waits, even when a field is free, and the next match that can be played takes the field. |
| BR-132 | A new field takes the lowest free number and straight away takes the next waiting match. Removing a field keeps the other numbers; a match on the removed field goes back to the front of the waiting list. The last field cannot be removed. |
| BR-133 | A field the organizer gives a match by hand overrides the automatic order until that match has a result. A match the organizer takes off its field is held (BR-136), as an exception to BR-130. The freed field takes the next waiting match. |
| BR-134 | Clearing a result does not put the match back on a field; it waits like any other match. |
| BR-135 | Fields do not change standings, places, points or sit-outs: waiting for a field is not sitting out. |
| BR-136 | A held match takes no field by itself (BR-130) and keeps its place in schedule order. The hold ends when the organizer places the match by hand (BR-133), releases it, or enters its result (FR-094). A released match waits like any other. A match that left its field for another reason (BR-132, BR-134) is not held. Example: one field plays M4, and M5 (held) and M6 wait. The organizer releases M5; when M4's result comes in, the field takes M5, not M6. |

### 7.17 Lord have mercy re-mix

In a **Lord have mercy** knockout (BR-084) the pairs do not stay together: the players still in are paired again before every later round. Where a rule assumes fixed knockout pairs, these rules apply instead.

| ID | Rule |
|---|---|
| BR-140 | The first knockout round is drawn when the knockout starts (BR-084). Once every match of a knockout round has a result, the organizer draws the next round. |
| BR-141 | The next round mixes the players who went through: the winners of the round before and, after round 1, the pairs that had a bye. They are paired completely at random, ignoring the standings, and the new pairs are placed in the round by lot. |
| BR-142 | The final is re-mixed too: the four players of the two pairs that reached it are paired again at random. |
| BR-143 | A player can get a partner they have had before. The draw does not avoid repeat partners. |
| BR-144 | With a third-place match, the four players of the two losing semifinal pairs are paired again completely at random for it. It is drawn together with the final. |
| BR-145 | Places are per player. Each player takes the place of the pair they played their last knockout match with. Places are numbered and shared as if those pairs were entries (BR-102, BR-104), and placement points are split the same way (BR-111). With 4 pairs in the knockout and a third-place match, the final's winners are 1st, its losers 2nd, the third-place match's winners 3rd and its losers 4th; without one, the four semifinal losers share 3rd. Either way, the best non-qualifier is 5th (BR-103). A player who was replaced is placed by BR-151. |
| BR-146 | Drawing the next round locks the winners of the round before. A score in a locked round can still be corrected, but not cleared, while the same pair wins. To change a winner, the organizer deletes the newest knockout round with its matches and results, which unlocks the round before as in BR-066, fixes the result and draws the next round again. The final and the third-place match count as one round. Deleting the first knockout round deletes the knockout (BR-087). A round is never drawn again by itself: only the organizer draws again. Drawing a round after the first again with the same players gives the same pairs (BR-156). The pairs change only when the players in the round change. Deleting the newest round of a finished tournament puts it back in progress (BR-095) and recalculates the season standings (BR-112). |
| BR-147 | The organizer can disable a player during a Lord have mercy knockout and re-enable them later (FR-044). A player is still in when their latest pair won its match or had a bye, or its match has no result yet; with a third-place match, the semifinal losers are also still in until that match has a result. A player who was replaced is not still in, whatever their pair did (BR-153). Every other player of the knockout is knocked out. A disabled player who is still in has left, and is replaced in the next draw (BR-148) or, with nobody available, stays in the draw (BR-149). Disabling a player who is knocked out only skips them as a replacement and leaves their place as it is. |
| BR-148 | A replacement comes into the next draw in place of each player who left — into the third-place match when that is the match the player was to play — so the number of players stays the same. The replacement is the best-placed player who is knocked out (BR-147) and not disabled; a player who was replaced is never picked (BR-153). Best-placed means last knocked out in a later round first, then the better group-phase standing, then the lot (BR-074). With a third-place match the semifinal losers are still in, so the first candidates are the quarterfinal losers, if the knockout had quarterfinals; without one, the semifinal losers are knocked out and come first. With several players to replace, the better group-phase standing gets the better replacement (BR-074); with too few replacements, those with the best group-phase standing are left without one and stay in the draw (BR-149), and the others are replaced in that order. |
| BR-149 | If nobody is available as a replacement, the player who left stays in the draw and their pair loses by walkover (BR-093). The organizer records the walkover (FR-052). If the player is re-enabled before the match has a result, the match is played. BR-157 covers a match in which both pairs have such a player. |
| BR-151 | A player who was replaced takes the place their replacement gave up: they are placed as if knocked out in the round in which the replacement was last knocked out before coming in, so every place keeps its number of players. A player replaced before the draw is therefore placed at least one round lower than one who leaves after it and loses by walkover (BR-152), and lower than one who is left without a replacement (BR-149). That is intended: the organizer decides who is there, and after the draw can still delete the round and draw it again (BR-146). |
| BR-152 | If a player leaves after the round is drawn and before their match has a result, their pair loses by walkover (BR-149), unless the organizer deletes that round (BR-146), disables the player and draws it again. A player who leaves after their pair has won its match, or while it has a bye, is replaced in the next draw (BR-147, BR-148). Deleting the round deletes the results of its other matches too. Where the players of a draw are the same, the pairs come out the same (BR-156) and those results have to be entered again; where a replacement comes in, it is a new draw, the pairs can change, and matches already played are played again. In the first knockout round there is no replacement. The organizer can leave the walkover, or delete the round, which deletes the knockout (BR-087), and start the knockout again: the disabled player does not qualify and the next one moves up (BR-080). When nobody is left to move up, because every player qualified or the others are disabled, the knockout can start again only with two qualifiers fewer (BR-080), without a third-place match if fewer than 4 pairs remain; with 2 pairs only the walkover is left. |
| BR-153 | Once a replacement has been drawn in place of a player, that player cannot come back: re-enabling them does not bring them back into a draw, and they are not picked as a replacement. Only BR-154 undoes this. |
| BR-154 | If the organizer deletes the round in which the replacement was drawn (BR-146), the replacement is undone, and a re-enabled player is in the new draw. A player who is still disabled is replaced again (BR-148). |
| BR-155 | A Lord have mercy knockout is shown round by round, not as a bracket tree, on the organizer's screen and on the share link (FR-070). The view marks which player came in for which, and which players have left but stay in the draw (BR-149). |
| BR-156 | Each knockout round after the first is drawn from the players who play it: the players who went through (BR-141) or, for the third-place match, the semifinal losers (BR-144), with each replacement in place of the player who left (BR-148). The pairs are placed in the round's matches by the same lot, so drawing again with the same players also gives the same matches (BR-146). When a player in the draw changes, it is a new draw: a corrected result changes who goes through, or a replacement comes in or is undone (BR-154). The final and the third-place match are drawn at the same time (BR-144) but each by its own lot, so a change of players in one does not change the pairs of the other. Round 1 can be drawn again only on the start-knockout screen, before the knockout starts (FR-045). |
| BR-157 | If both pairs of a match have a player who left and was not replaced, the organizer records which pair wins (FR-052). |

Consequence: the next round's pairs are not known until every match of the round before has a result (BR-140), so fields stand idle between knockout rounds (BR-130).

Worked case for BR-145, BR-147, BR-148 and BR-151; the variants cover BR-149, BR-152–BR-154, BR-156 and BR-157. Sixteen players qualify, with a third-place match and the default points table (FR-011); #n is the player placed nth after the group phase.

1. **Quarterfinals.** The pairs of #1, #2, #3, #4, #9, #10, #11 and #12 win. #5, #6, #7, #8, #13, #14, #15 and #16 are knocked out.
2. **Before the semifinal draw.** #3 has left and #5 has gone home, so the organizer disables both. #5 is knocked out, so #5 is only skipped (BR-147). #6 comes in for #3: every candidate was knocked out in the quarterfinals, and #6 has the best standing of those not disabled (BR-148). The semifinals are drawn from #1, #2, #4, #6, #9, #10, #11 and #12 (BR-156).
3. **Semifinals.** The pairs of #1, #2, #6 and #9 win. #4, #10, #11 and #12 lose and wait for the third-place match, so they are still in (BR-147).
4. **Before the last draw.** #2 has left. The semifinal losers are not candidates, so the candidates are the quarterfinal losers who are not disabled: #7, #8, #13, #14, #15 and #16. #7 has the best standing and comes in for #2 (BR-148).
5. **Final and third-place match.** The final is drawn from #1, #6, #7 and #9; say the pair of #1 and #6 beats the pair of #7 and #9. The third-place match is drawn from #4, #10, #11 and #12; say the pair of #4 and #10 beats the pair of #11 and #12.
6. **Places and points.** #1 and #6 are 1st (10 each), #7 and #9 are 2nd (8 each), #4 and #10 are 3rd (6 each), #11 and #12 are 4th (4 each). #3 takes the place #6 gave up and #2 the place #7 gave up (BR-151): both share 5th with #5, #8, #13, #14, #15 and #16, for (2 + 0 + 0 + 0) / 4 = 0.5, rounded down to 0 (BR-111). Every place keeps its number of players: 2, 2, 2, 2 and 8.

Four variants:

- **#2 leaves after the last round is drawn (BR-152).** The final was drawn from #1, #2, #6 and #9. The organizer records a walkover against #2's pair, and #2 is 2nd, not in the shared 5th of step 6 (BR-151). Or the organizer deletes the round, disables #2 and draws again. #7 comes in, so the final is a new draw from #1, #6, #7 and #9 and its pairs can change. The third-place match has the same four players, so its pairs come out the same, and a result it already had is entered again (BR-156).
- **#2 comes back after step 5 is drawn (BR-153, BR-154).** Re-enabling #2 changes nothing: #7 plays the final and #2 stays in the shared 5th. If the organizer deletes the last round, the replacement is undone: #7 is knocked out in the quarterfinals again, and the final is drawn from #1, #2, #6 and #9.
- **#1 and #2 both leave before the last draw, and everybody knocked out has gone home except #7 (BR-148, BR-149).** #1 has the better standing and is left without a replacement; #2 gets #7. The final is drawn from #1, #6, #7 and #9, and the organizer records a walkover against #1's pair: #1 is 2nd, and #2 shares 5th.
- **The same, and #7 has gone home too (BR-157).** #1 and #2 both stay in the draw with #6 and #9. Drawn into one pair, that pair loses by walkover. Drawn into different pairs, both pairs of the final have a player who left, and the organizer records which pair wins. #1 and #2 take the places of their pairs (BR-145).

## 8. Open questions

| Question | Decides |
|---|---|
| Who is the data controller named on the "Privacy" page (FR-101), and which EU host runs the instance and its backups (FR-100)? | The instance owner, with dejvicek |
