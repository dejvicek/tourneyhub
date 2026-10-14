# TourneyHub — MVP Product Requirements

| | |
|---|---|
| Status | Draft |
| Date | 2026-10-14 |
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
| Swiss | Entries play round after round against the entry next to them in the standings, never the same opponent twice. |
| DYP | "Draw Your Partner". Players enter alone and are drawn into pairs, one from the top half and one from the bottom half, for the whole tournament. |
| Monster DYP | Players enter alone. Every round, new 2 vs 2 teams are formed from the current standings, and each player collects their own points. |
| Group phase | **Round robin** (everyone plays everyone, once or twice), **Swiss**, or **Monster DYP** rounds. When a knockout follows, the group phase is its qualification. |
| Knockout | The elimination phase, played as single elimination (SKO): lose once and you're out. It follows the group phase or is the whole tournament. |
| Entry | Whoever takes a place in a tournament: a player in Singles and Monster DYP, a pair in Doubles and DYP (and in a pair knockout). |
| League ranking | The order of a league's players used for seeding and draws (BR-020). |
| Seed | An entry's position in the starting order. Seed 1 is treated as the strongest. |
| Bye | An empty spot in a first-round bracket match. The entry drawn against it gets a free win and goes through without playing. |
| Sit-out | A group-phase round an entry does not play because the numbers do not work out. |
| Walkover | A match won without being played, e.g. because the opponent left. |
| Late player | A player — in Doubles, a pair — added after the tournament has started (BR-067). |
| Disabled | A player or pair the organizer has taken out of new rounds for now. |
| Top players | In Monster DYP, the players kept apart in rounds 1 and 2. |
| BH1, BH2 | Buchholz tie-breakers. BH1 sums the points of an entry's opponents; BH2 sums those opponents' BH1. |
| Score difference | Scores for minus scores against. |
| Place | An entry's finishing position in a tournament. Several entries can share a place. |
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
7. Group-phase points (2 / 1 / 0, optional points for sitting out), tie-breakers (head-to-head and score difference in a round robin; score difference, BH1 and BH2 in Swiss and Monster DYP), and season standings from placement points.
8. A read-only share link per league.
9. English and Czech UI, usable on a phone.

### 4.2 Not in the MVP

Player accounts and players reporting their own results · co-organizers and transferring a league · organizations and multi-tenancy · teams of more than two, and named teams that last across tournaments · entry fees, prizes and payments · live updates (viewers refresh the page) · email of any kind (verification, password reset, invitations) · public listing, search and following · statistics beyond standings · data export and account deletion · double elimination (DKO) knockouts · group phases split into several groups · matches played in sets (e.g. best of three) · other tie-breakers, and configurable ones in a round robin · match times, venues and table assignment.

Each of these is on the roadmap (`ROADMAP.md`).

## 5. Example evenings

### 5.1 A DYP evening

1. An organizer gets the sign-up code from the instance admin and signs up.
2. They create the league "Thursday Foosball". Season 1 starts automatically.
3. They add the regulars to the player list.
4. On Thursday, 12 players come. The organizer creates a DYP tournament with a round robin. The 6 best-ranked players form the top half, the other 6 the bottom half, and each top-half player is drawn a bottom-half partner.
5. Generating creates the round-robin schedule: 6 pairs, 5 rounds, 15 matches.
6. The organizer enters each result on their phone as matches finish. When the round robin is complete, they start a knockout for the top 4 pairs, without a third-place match: 1st v 4th and 2nd v 3rd. The bracket advances by itself.
7. When the final is entered, the tournament finishes. Both players of the winning pair get 10 points and the runners-up 8 each. The two pairs that lost the semifinals share 3rd, so their four players split the points for 3rd and 4th: (6 + 4) / 2 = 5 each. The two pairs that did not qualify are 5th (2 points each) and 6th (0). The season standings update.
8. Players open the league's share link to see the round robin, the bracket and the season standings.

### 5.2 A Monster DYP night

1. 14 players come. The organizer creates a Monster DYP and is shown a recommendation of at least 4 rounds. Points for sitting out stay off.
2. Round 1: 12 players play in 3 matches and 2 sit out. The 3 best-ranked players are in different matches.
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
| FR-002 | Passwords have at least 12 characters. An email address can belong to only one account. |
| FR-003 | Organizers log in with email and password and stay logged in on that device until they log out. |
| FR-004 | A logged-in organizer can change their password. |
| FR-005 | The instance admin can set or change the sign-up code. Changing it does not affect existing accounts. |
| FR-006 | The instance admin can set a new password for an organizer who forgot theirs. There is no self-service reset in the MVP. |
| FR-007 | An organizer's home page lists their leagues. Organizers can manage only their own leagues. |

### 6.2 Leagues and players

| ID | Requirement |
|---|---|
| FR-010 | An organizer creates a league with a name. Creating it also starts Season 1. |
| FR-011 | League settings: name; whether draws are allowed in group phases; and the placement points table. The default is 10, 8, 6, 4, 2 for 1st–5th, kept small so that a player who misses a few tournaments can still catch up. Points are whole numbers, and no place is worth more than the place above it. |
| FR-012 | The organizer adds players to the league's player list by name, renames them and removes them (BR-001, BR-002). A rename shows everywhere, including past results. |
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
| FR-030 | The organizer creates a tournament in the league's active season with a name, a date (default: today) and a type: Singles, Doubles, DYP or Monster DYP. |
| FR-031 | A tournament usually has a group phase followed by a knockout, but either can be left out. Singles, Doubles and DYP choose a group phase — round robin (once or twice), Swiss or none; Monster DYP always plays its own rounds (§7.8). Without a group phase, the tournament is a knockout from the start, with or without a third-place match. After a group phase, the organizer decides whether a knockout follows (FR-040). |
| FR-032 | The organizer picks the players from the league's player list. There must be at least 2 entries, or 4 with a third-place match; Monster DYP needs at least 4 players. There is no maximum. If a technical limit is ever needed, it must still allow 256 entries in a tournament and 20 rounds in a group phase. |
| FR-033 | Doubles: the organizer puts the players into pairs. DYP: the players are split into a top and a bottom half — by the league ranking or by hand — and the pairs are drawn (BR-031–BR-033). |
| FR-034 | The first phase of a Singles, Doubles or DYP tournament is seeded by league ranking (default) or random shuffle, and the organizer can then reorder the seeds by hand. A knockout after a group phase is seeded by the group-phase places (§7.11). |
| FR-035 | Generating creates the bracket, the round-robin schedule, or the first round of a Swiss or Monster DYP, and starts the tournament. |
| FR-036 | Until the first result is entered, the organizer can go back to setup, change anything — including a new DYP draw — and generate again. |
| FR-037 | A tournament with a knockout finishes automatically when every knockout match has a result. A tournament without one finishes when the organizer finishes it after the group phase (FR-040). |
| FR-038 | The organizer can delete a tournament after confirming, unless its season is closed. |
| FR-039 | Round robin, Swiss and Monster DYP have a setup setting, **points for sitting out**: off by default (0 points), on gives 1 point (BR-071). |

### 6.5 Group phase and knockout

| ID | Requirement |
|---|---|
| FR-040 | Swiss and Monster DYP have no set number of rounds: once every match in the current round has a result, the organizer adds the next round, starts the knockout (FR-045) or finishes the tournament after confirming. The organizer sees a recommended minimum number of rounds (BR-068) but can stop earlier or play on. A round robin offers the same choice — knockout or finish — once all its matches have results. |
| FR-041 | Monster DYP: the top players (BR-061) are taken from the league ranking, or marked by the organizer — at most one per match in a round. |
| FR-042 | Each new round is drawn from the current standings (§7.7, §7.8), leaving out disabled players (BR-064). |
| FR-043 | For a Swiss or Monster DYP, the organizer switches each tie-breaker — score difference, BH1, BH2 — on or off and puts them in order. Default: BH1, then BH2, then score difference. |
| FR-044 | In a Swiss or Monster DYP, the organizer can disable any player — in Doubles and DYP, a pair — and re-enable them later (BR-064). |
| FR-045 | When starting the knockout, the organizer picks how many entries qualify and whether there is a third-place match (BR-080). After a round robin or Swiss, the qualifying entries play as they are. After Monster DYP rounds, the knockout is formed in one of four ways: **Seeded pairs**, **Singles**, **A little mercy** or **Lord have mercy** (§7.11). |
| FR-046 | The organizer can delete the newest round of a Swiss or Monster DYP, or a knockout that follows a group phase, with any results in it (BR-066, BR-087). Deleting round 1 takes the tournament back to setup. |
| FR-047 | The organizer can add late players from the league's player list — in Doubles, a pair — to any group phase except DYP: between rounds of a Swiss or Monster DYP, and until a round robin is complete (BR-054, BR-067). A knockout without a group phase takes them only in place of a bye (BR-045); a knockout after a group phase takes none. |
| FR-048 | Before a late player joins a Swiss or Monster DYP that uses BH1 or BH2, the organizer is warned that it may be unfair: the rounds the late player missed earned no points, so everyone who meets them afterwards gets a lower BH. The organizer can go ahead anyway. |

### 6.6 Results

| ID | Requirement |
|---|---|
| FR-050 | The organizer enters a result for each match: a winner, or a draw where allowed (BR-090). |
| FR-051 | A result can include a score for each side, in whole numbers. Swiss and Monster DYP rounds require scores (BR-092). |
| FR-052 | A match can be recorded as a walkover: a winner, with no score. |
| FR-053 | The organizer can change or clear a result, subject to BR-011, BR-053, BR-065 and BR-094. |

### 6.7 Standings

| ID | Requirement |
|---|---|
| FR-060 | Every tournament shows its standings, which update as results come in (§7.13). Swiss and Monster DYP standings also show BH1, BH2, score difference and sit-outs. |
| FR-061 | Every season shows season standings: each player who has played in a finished tournament of the season, with their total placement points, tournaments played and tournament wins (§7.14). |

### 6.8 Sharing

| ID | Requirement |
|---|---|
| FR-070 | Every league has a share link. Without an account, anyone with it can see the league, its seasons and season standings, and each tournament's bracket, schedule or rounds, results and standings. Tournaments still in setup are visible only to the organizer. |
| FR-071 | The link cannot be guessed, and leagues are not listed or searchable anywhere. |
| FR-072 | Viewers cannot change anything. |

### 6.9 Language and devices

| ID | Requirement |
|---|---|
| FR-080 | The whole UI is available in English and Czech. Names entered by organizers are shown as entered, and the knockout options (§7.11) keep their English names in both languages. |
| FR-081 | Organizers choose their language and it is remembered. Viewers get their browser's language if it is English or Czech, otherwise English, and can switch. Dates follow the chosen language's format. |
| FR-082 | Every screen works on a phone. Entering a result takes at most three taps from the bracket, schedule or round — open the match, choose the result, save — plus typing scores. |

## 7. Business rules

### 7.1 Players

| ID | Rule |
|---|---|
| BR-001 | Player names are unique within a league, ignoring upper and lower case. |
| BR-002 | A player who is in an unfinished tournament cannot be removed. A removed player keeps their past results, places and points but cannot be picked for new tournaments. |
| BR-003 | A player is in a tournament at most once; in Doubles and DYP, in exactly one pair. |

### 7.2 Seasons and settings

| ID | Rule |
|---|---|
| BR-010 | A new season cannot start while any tournament in the current season is unfinished. The organizer finishes or deletes it first. |
| BR-011 | Nothing in a closed season can change: no new tournaments, results, corrections or deletions. Renaming the league, the season or a player, and deleting the whole league, still apply. |
| BR-012 | Changing the placement points table recalculates the active season's standings; a closed season keeps the table it was played under. Turning draws off affects only results entered afterwards. |

### 7.3 League ranking and seeding

| ID | Rule |
|---|---|
| BR-020 | The league ranking orders the league's players by current season points, then tournament wins, then their final place last season (players without one come after those with one), then by lot. It reflects the standings at the moment it is used. |
| BR-021 | Seeding by league ranking: singles follow the ranking. Pairs are ordered by the sum of their two players' ranking positions, lowest first; on equal sums, the pair with the better-ranked player goes first. |
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
| BR-043 | There are no draws. The winner of each match goes through; the loser is out. |
| BR-044 | With a third-place match, the two semifinal losers play it. |
| BR-045 | A generated bracket cannot be edited by hand, with one exception: in a Singles or Doubles knockout without a group phase, a late entry can take the place of a bye until every first-round match has a result, as long as the entry with the bye has no second-round result yet. The two then play a normal first-round match. |

### 7.6 Round robin

| ID | Rule |
|---|---|
| BR-050 | Every entry plays every other entry once, or twice if the organizer chose twice. |
| BR-051 | Matches are grouped into rounds, and no entry plays twice in a round. With an odd number of entries, one sits out each round, and every entry sits out the same number of times. |
| BR-052 | When played twice, the second half repeats the first half's pairings, round by round. |
| BR-053 | A round robin's results lock when the knockout is drawn. |
| BR-054 | A late entry in a round robin plays every other entry as often as everyone else does. The matches not yet played are rescheduled to fit its matches in, keeping sit-outs as even as possible; results already entered stay. |

### 7.7 Swiss

| ID | Rule |
|---|---|
| BR-055 | Round 1 pairs the top half of the seeds against the bottom half: seed 1 plays seed N/2 + 1, seed 2 plays seed N/2 + 2, and so on (8 entries: 1 v 5, 2 v 6, 3 v 7, 4 v 8). |
| BR-056 | From round 2, entries are ordered by current standing and play their neighbour: 1st v 2nd, 3rd v 4th, and so on. An entry that has already played its neighbour plays the next entry down that it has not played. |
| BR-057 | No entry meets the same opponent twice while it can be avoided. |
| BR-058 | With an odd number of entries in a round, one sits out: the lowest-placed of those who have sat out the fewest times. Disabled entries do not count. |

### 7.8 Monster DYP rounds

| ID | Rule |
|---|---|
| BR-060 | Every round, players are grouped in fours by their current standing — in round 1, by the league ranking. In each group, the 1st and 4th play the 2nd and 3rd (#1 + #4 vs #2 + #3). |
| BR-061 | There are as many top players as matches in a round. In rounds 1 and 2 they are in different groups, and the other players fill the groups in standing order (16 players, top 4: #1 #5 #6 #7 · #2 #8 #9 #10 · #3 #11 #12 #13 · #4 #14 #15 #16). |
| BR-062 | Nobody gets the same partner twice while it can be avoided; the grouping changes as little as needed to avoid it. |
| BR-063 | When the number of players is not divisible by 4, the extra one to three players sit out the round. The players who have sat out the fewest times sit out; ties are decided by lot. Disabled players do not count. |

### 7.9 Round by round (Swiss and Monster DYP)

| ID | Rule |
|---|---|
| BR-064 | A disabled player or pair is not drawn into new rounds. Their results and points stay; rounds they miss earn 0 and do not count as sit-outs. Once re-enabled, they play from the next round. At the end they are placed by their standing. |
| BR-065 | A round's results can be changed until the next round or the knockout is drawn; after that they are locked. |
| BR-066 | Deleting the newest round removes its matches and results and unlocks the round before it. |
| BR-067 | In a Swiss or Monster DYP, a late player starts on 0 points and plays from the next round; rounds they missed earn 0 and do not count as sit-outs. A round robin fits a late entry into its schedule (BR-054), and a knockout without a group phase only lets one take a bye (BR-045). DYP takes no late players, because its pairs are drawn at the start, and neither does a knockout after a group phase, whose qualifiers are fixed. |
| BR-068 | The recommended minimum number of rounds is log₂ of the number of entries, rounded up — the usual Swiss minimum, after which at most one entry can have won every match. Monster DYP counts players. 5–8 entries → 3 rounds, 9–16 → 4, 17–32 → 5. Late players count from when they join. |

### 7.10 Group-phase points and standings

| ID | Rule |
|---|---|
| BR-070 | In round robin, Swiss and Monster DYP rounds, a win is worth 2 points, a draw 1 and a loss 0. In Monster DYP, both players of a team get the points. |
| BR-071 | A sit-out is worth 0 points, or 1 point when the tournament's "points for sitting out" setting is on. |
| BR-072 | Swiss and Monster DYP: entries level on points are ordered by the enabled tie-breakers, in the organizer's order (FR-043). |
| BR-073 | BH1 is the sum of the current points of every opponent faced, counted once per match. BH2 is the sum of those opponents' BH1. Score difference is scores for minus scores against over all matches. Sit-outs add nothing to BH1 or BH2, and score difference counts only entered scores. |
| BR-074 | Entries still level share the place. Where a strict order is needed — pairing the next round, or the knockout's cut and seeding — the lot decides. |

### 7.11 From group phase to knockout

| ID | Rule |
|---|---|
| BR-080 | The best entries in the standings qualify, as many as the organizer picks. Disabled entries do not qualify; the next ones move up. A knockout needs at least 2 entries, or 4 with a third-place match, and the Monster DYP pair options need an even number of qualifiers. |
| BR-081 | **Seeded pairs** (Monster DYP): with N qualifiers, 1st partners the (N/2 + 1)th, 2nd partners the (N/2 + 2)th, and so on — with 16: #1 + #9, #2 + #10 … #8 + #16. Pairs are seeded by their better player's place. |
| BR-082 | **Singles** (Monster DYP): qualifiers play 1 vs 1, seeded by their place. |
| BR-083 | **A little mercy** (Monster DYP): qualifiers are split into a top and a bottom half by place, and each top-half player is drawn a partner from the bottom half. Pairs are seeded by their better player's place. |
| BR-084 | **Lord have mercy** (Monster DYP): qualifiers are paired completely at random and placed in the bracket by lot, ignoring the standings. |
| BR-085 | After a round robin or Swiss, the qualifying entries play on as they are — players in Singles, pairs in Doubles and DYP — seeded by their place. |
| BR-086 | Knockout pairs stay together until the end. The knockout follows §7.5, including the optional third-place match, but takes no late entries. |
| BR-087 | Deleting the knockout unlocks the group phase — all of a round robin's results, or the newest round of a Swiss or Monster DYP — and the organizer chooses again what comes next (FR-040). |

### 7.12 Results

| ID | Rule |
|---|---|
| BR-090 | Draws are possible only in group phases, and only if the league allows draws. Knockouts have no draws. |
| BR-091 | A match gets a result only once both of its sides are known. |
| BR-092 | Scores, if entered, must agree with the result: the winner has the higher score, and a draw has equal scores. Swiss and Monster DYP round matches need scores, except walkovers. |
| BR-093 | A walkover counts as a normal win and loss everywhere. |
| BR-094 | In a knockout, a result is locked once any later match it feeds has a result: the next match for its winner and, for a semifinal with a third-place match, that match for its loser. That later result must be cleared first. Changing a winner updates the sides of the later matches. |
| BR-095 | Clearing a result in a finished tournament puts it back in progress. |

### 7.13 Tournament places

| ID | Rule |
|---|---|
| BR-100 | Places belong to entries. Every player in an entry gets the entry's place. |
| BR-101 | Round robin: entries are ranked by points (BR-070, BR-071), with played, won, drawn, lost, sat out, score difference and points shown. When exactly two entries are level, the one with more points from the matches between them ranks higher. Entries still level are ordered by score difference, counting only entered scores, and after that share the place (BR-074). |
| BR-102 | Knockout: the winner is 1st and the final's loser 2nd. With a third-place match, its winner is 3rd and its loser 4th; without one, the two semifinal losers share 3rd. Entries knocked out in the same earlier round share a place: quarterfinal losers share 5th, round-of-16 losers share 9th, and so on. |
| BR-103 | With a group phase but no knockout, the group-phase standings are the places. With both, the knockout entries take the top places by BR-102, and the other entries follow in their group-phase order, numbered after the knockout entries: after 8 knockout pairs, the best non-qualifier is 9th. |
| BR-104 | After a shared place, numbering skips accordingly: two entries sharing 3rd are followed by 5th. |

### 7.14 Season standings

| ID | Rule |
|---|---|
| BR-110 | When a tournament finishes, each player in it earns the placement points for their place from the league's table. Places beyond the table earn 0. |
| BR-111 | Entries sharing a place split the points of the places they cover: each gets the average, rounded down. With the default table, two pairs sharing 3rd cover 3rd and 4th, so each of their four players gets (6 + 4) / 2 = 5; four entries sharing 5th get (2 + 0 + 0 + 0) / 4 = 0.5, rounded down to 0. |
| BR-112 | Only finished tournaments count. Correcting a result in a finished tournament, or deleting a tournament, recalculates the season standings. |
| BR-113 | Season standings rank players by total placement points, then tournament wins. Players still level share the place. |

## 8. Open questions

None at the moment.
