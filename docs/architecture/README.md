# TourneyHub architecture in LikeC4

A LikeC4 model of the TourneyHub architecture for a visual overview. The sources of truth are `ADR.md` and `PRD.md` in the repository root and `DATA-MODEL.md` (currently PR #3); the model is only their picture and can fall behind.

## Files

| File | Contents |
|---|---|
| `spec.c4` | element kinds (actor, system, SPA, container, database, table group, external service…), deployment node kinds and the `fk` relationship for foreign keys |
| `model.c4` | actors, SPA, API with the engine, CLI, PostgreSQL with its table groups, GitHub and the relationships between them |
| `1-structure.c4` | folder I. Structure, views 1 to 6: context, containers, SPA, API, data, development and CI |
| `2-deployment.c4` | deployment model and folder II. Deployment, views 7 and 8: development in Docker Compose (laptop and phone on the LAN) and production on the VPS (Caddy, backups off the VPS) |
| `3-flows.c4` | folder III. Flows, views 9 to 15: login and refresh, result entry, next round, viewer, password reset (13a admin, 13b first login), release, the DYP evening from PRD §5.1 (15a setup, 15b play and viewers) |

Elements link to the relevant ADRs, data model sections and PRD sections on GitHub (the anchors match the headings in the documents).

Links to `DATA-MODEL.md` point at branch `docs/data-model-mvp` (PR #3). After PR #3 merges, switch them to `main`:

```sh
sed -i '' 's#blob/docs/data-model-mvp/#blob/main/#g' docs/architecture/model.c4
```

## View order and folders

The views are in three folders: I. Structure (`1-structure.c4`), II. Deployment (`2-deployment.c4`) and III. Flows (`3-flows.c4`). The folder is the string after the `views` keyword in each file (`views "I. Structure" { … }`); LikeC4 puts it before the view title (`I. Structure / 1. Context…`) and shows it as a folder in the drop-down list in the toolbar. Folders are sorted alphabetically by name, hence the Roman numerals: without them the list would start with Deployment. The `order` property of each view sets the order inside the folder; without it LikeC4 orders views by the order in which it loaded the files, and the order changes on hot reload. The number in the view title stays (1 to 15b); the view ids (`index`, `containers`, `spa`, `api`, `data`, `devops`, `devDeployment`, `prodDeployment`, `loginRefresh`, `resultEntry`, `addRound`, `shareLink`, `adminReset`, `adminResetLogin`, `release`, `dypEvening`, `dypEveningPlay`) do not change, because `navigateTo` and the `/view/<id>/` URLs point at them.

Where the view list appears:

- The start page (`/`) and the ⌘K search: all 17 views in a row, 1 to 15b.
- Clicking the view title in the toolbar: folders I to III on the left, the views of the selected folder on the right.
- The hamburger menu on the start page: all three modes give the order 1 to 15b; the default "By files" shows the files `1-structure.c4`, `2-deployment.c4`, `3-flows.c4`, which match folders I to III (LikeC4 does not care about file names, it only sorts them alphabetically); "By folders" in LikeC4 1.60 shows only a flat list without folders, and so does "List".

## How to read the diagrams

- Blue is TourneyHub, grey external services (GitHub), green the engine (pure functions), purple cylinders table groups, figures actors. Technology icons (React, Python, PostgreSQL, Git, GitHub, Docker, Vite, TypeScript, Apple) are only for quick recognition; GHCR carries the Docker icon because it holds container images, and so does the VPS, because it runs Docker Compose (the ADRs name no other technology for the VPS).
- The orange stripe on TourneyHub is the `#proposed` tag: all ADRs are still Proposed.
- View 4 does not draw the API container frame: with it Graphviz pushes PostgreSQL below the frame and the five lines to the database snake around the engine. Everything in it except the SPA and PostgreSQL is inside the API (view 2); the components carry the prefix "API:" in their title, the engine is green.
- The short text in a node is the `summary`; the full description, the technology and the links to the ADRs, the PRD and the data model open with the card icon in the node's top right corner (or a double click).
- A dashed arrow is a call or a use and points from the caller to the callee. A solid line with a crow's foot (view 5) is a foreign key; the foot is at the referencing table.
- The dynamic views 9 to 13 and 15 open as a sequence diagram. The Diagram/Sequence switch is in the toolbar, and the Start button walks through the steps one by one.

## Navigating between views

Every other view can be reached by clicking from view 1. The magnifier icon is at the bottom of every node that leads somewhere (on compound nodes, left of the title). A compound node (TourneyHub, SPA, API, database, GitHub) opens its own view; an actor opens the flow in which it does what its arrow in that view says (the organizer runs the evening, the admin resets a password, in view 6 the admin pulls images).

| From view | Element | To |
|---|---|---|
| 1 Context | TourneyHub, GitHub | 2 Containers, 6 Development and CI |
| 1 Context | Organizer, viewer, admin, developer | 15a DYP evening, 12 Viewer, 13a Password reset, 14 From PR to VPS |
| 2 Containers | SPA, API, PostgreSQL | 3, 4, 5 |
| 2 Containers | Organizer, viewer, admin | 15a, 12, 13a |
| 3 SPA | Client-side auth, organizer screens, admin screens, viewer pages, API | 9 Login, 15a, 13a, 12, 4 |
| 4 API | auth, tournaments, engine, viewers, instance admin, leagues; SPA, PostgreSQL | 9, 10 Result entry, 11 Next round, 12, 13a, 15a; 3, 5 |
| 5 Data | Accounts and administration, Rounds and matches; API | 9, 10; 4 |
| 6 Development and CI | GitHub Actions, developer, admin; GHCR | 14; 8 Production |
| 7 Development | environment, Vite; SPA, API and db instances | 8; 3, 4, 5 |
| 8 Production | environment, Caddy; SPA, API and db instances | 7; 2, 3, 4, 5 |
| 13a → 13b → 9 | step with the link icon | the 401 leads to the first login, its login to the login detail |
| 14 From PR to VPS | API, PostgreSQL | 4, 5 |
| 15a → 15b → 10, 12 | step with the link icon | the schedule leads to play, the result entry to view 10, the share link to view 12 |

The ← → arrows in the toolbar go back (history as in a browser), as do the view drop-down next to them and ⌘K. The sequence diagrams 9 to 12 and 15b have no magnifiers on their elements; use the arrow to go back.

## Running

All commands run from the repository root.

Live preview that re-renders after every change to a `.c4` file:

```sh
npx likec4@1.60.0 start docs/architecture
```

Offline version in one file (just open it in a browser; rebuild it after changing the model). The output goes to `docs/architecture/dist`, which is git-ignored:

```sh
npx likec4@1.60.0 build docs/architecture --output-single-file --title TourneyHub -o docs/architecture/dist
open docs/architecture/dist/index.html
```

Syntax check after an edit:

```sh
npx likec4@1.60.0 validate docs/architecture
```

## Other options

- The LikeC4 extension for VS Code: a diagram preview next to the editor and completion in `.c4` files.
- `npx likec4@1.60.0 mcp docs/architecture` starts an MCP server through which an agent can query the model.
- `npx likec4@1.60.0 export png docs/architecture` exports images (it downloads a browser for Playwright).
