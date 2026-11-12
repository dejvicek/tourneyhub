# TourneyHub documentation

| Folder | Document | What it holds |
|---|---|---|
| `product/` | [PRD.md](product/PRD.md) | What the MVP does: users, glossary, requirements (`FR-`) and business rules (`BR-`). |
| | [ROADMAP.md](product/ROADMAP.md) | What comes after the MVP (`RM-`), in stages. |
| `architecture/` | [ADR.md](architecture/ADR.md) | How it is built: the architecture decision records (ADR-001 onwards). |
| | [DATA-MODEL.md](architecture/DATA-MODEL.md) | The PostgreSQL schema and what the database enforces. |
| | [diagrams/](architecture/diagrams/README.md) | A LikeC4 picture of the ADRs, the PRD and the data model. |
| `style/` | [python-style.md](style/python-style.md) | How the backend's code is written. |
| | [frontend-style.md](style/frontend-style.md) | How the frontend's code is written. |

The PRD decides what, the ADRs and the data model decide how, and the style guides decide how the code is written; where a style guide and an ADR disagree, the ADR wins until it is changed. How to run the project is in the [README](../README.md) at the repository root.
