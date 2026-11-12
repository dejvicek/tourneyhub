# Research: best-practice skills for Python and React (2026-11-12)

Question: can TourneyHub set up a best-practices skill for Python and React, like
[laravel-best-practices](https://github.com/nunomaduro/laravel-starter-kit/tree/main/.claude/skills/laravel-best-practices)
does for Laravel? Do ready-made packages exist?

## Verdict

Yes, but the project already has most of it: the `python-style` and `frontend-style`
skills and the guides in `docs/style/`. No ready-made package fits our stack. The
official skills (FastAPI, Pydantic, shadcn, Astral) contradict our decisions in several
places, and the community skills we sampled contain errors. Published measurements show
that generic rule packs help little and cost context.

Recommendation: install nothing wholesale. Take one thing from the Laravel pattern, the
**wrong/right example per rule**, and turn rules that exist only as text into tool checks
where the existing tools can do it. Points 1 and 2 of §6 are done in PR #69.

## 1. How the Laravel skill is built

- It is not hand-written. **Laravel Boost v2** (`boost:install`) generates it and copies it
  for eight agents (Claude Code, Cursor, Copilot, Codex and others). Boost also adds an MCP
  server with version-aware documentation search (`search-docs`).
- `SKILL.md` (189 lines): a long description as the trigger, a "Consistency First" section
  (follow the existing pattern in the code), an index of 19 topics with short bullets that
  link to `rules/<topic>.md`, and an instruction to read the rule files in a subagent.
- `rules/`: 20 files (26–201 lines). Each rule is a heading, a short explanation, an
  **Incorrect** block and a **Correct** block. No rule IDs, no evals, no version.

## 2. What TourneyHub already has

| Element of the Laravel pattern | TourneyHub | Status |
|---|---|---|
| Skill with a trigger description | `.claude/skills/python-style`, `frontend-style` | have |
| Index → load only the needed part | the skill points to guide sections (§) | have, by § instead of files |
| Project decisions an agent cannot guess | "Project decisions" table in each skill | have; Laravel has none |
| Rules with wrong/right examples | python-style.md 17 code blocks, frontend-style.md 2 (before #69) | partly |
| Tool enforcement | ruff (~40 rule families), mypy strict, import-linter, strict ESLint with custom bans, CI | have; Laravel has none |
| Version-aware documentation search | Context7 MCP (connected outside the repo) | have |
| An instruction to load the skill | `CLAUDE.md` says so explicitly | have |

## 3. Ready-made packages

### Python

| Candidate | Owner | Note |
|---|---|---|
| [fastapi skill](https://github.com/fastapi/fastapi/tree/master/fastapi/.agents/skills/fastapi) | official, MIT, commit 2026-11-07 | Current, but recommends SQLModel over SQLAlchemy, `ty`, `fastapi dev` and FastAPI Cloud. Conflicts with us. |
| [pydantic skill](https://github.com/pydantic/pydantic/tree/main/.agents/skills/pydantic) | official, MIT, 2026-08-25 | Good and restrained; fits our `engine`. |
| [astral-sh/agent-plugins](https://github.com/astral-sh/agent-plugins) | official | ruff/uv advice is sound; adds a `ty@latest` LSP without a pinned version, and we use mypy. |
| [zhanymkanov/fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices/blob/master/AGENTS.md) | community, 18k★, **no licence** | Domain-based structure and async SQLAlchemy; we have layers and a sync `Session`. |
| Jeffallan, wshobson, midudev | community | Errors in the sample (`model_config` imported as a function, `create_all` instead of Alembic, a skill that cannot be invoked). |

### React

| Candidate | Owner | Note |
|---|---|---|
| [shadcn skill](https://github.com/shadcn-ui/ui/tree/main/skills/shadcn) | official, MIT, 2026-10-14, has evals | Concrete rules (semantic colours, `gap` instead of `space-y`, `DialogTitle`). Runs `npx shadcn@latest` without a pinned version; needs checking against our tokens and the `dark:` ban. |
| [vercel react-best-practices](https://github.com/vercel-labs/agent-skills/tree/main/skills/react-best-practices) | Vercel, 230 KB | Aimed at Next.js and Server Components; recommends SWR (we use TanStack Query). |
| [Mindrally tanstack-query](https://github.com/Mindrally/skills/blob/main/tanstack-query/SKILL.md) | community, Apache-2.0 | Correct v5 API, but we already have `@tanstack/eslint-plugin-query`. |

No official skill exists for SQLAlchemy, Alembic, pytest, Tailwind, Vite or TanStack
Query (TanStack PR #10879 was closed without a merge).

Not searched: the Claude Code plugin marketplace and the awesome-claude-skills /
awesome-cursorrules lists (star counts only). The claim "no ready-made package exists"
holds within this scope.

## 4. Evidence on effect

- **Vercel, 2026-01-27** ([article](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals)):
  no docs 53 %, skill 53 %, skill plus an explicit instruction 79 %, an index in AGENTS.md
  100 %. The agent did not invoke the skill in 56 % of cases. The eval measured APIs newer
  than the model's training data, so it transfers only partly to style rules. Our
  `CLAUDE.md` already gives the explicit instruction (the "79 %" level or better).
- **arXiv 2602.11988** (ICLR 2026): repository context files do not generally improve task
  success and raise cost by more than 20 %.
- **Anthropic** ([best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)):
  add only context Claude does not have; write evals first, then the text.
- Not verified (summaries only): SkillsBench (narrow hand-written skills help, generic and
  self-generated ones do not) and Snyk (a large share of skills in registries had issues).

## 5. Risks of a generic package

1. It triggers instead of, or next to, our skills and advises differently (SQLModel, async,
   SWR).
2. Outdated or wrong advice in community skills.
3. More overlapping skills make triggering worse.
4. Context cost (Vercel's AGENTS.md alone is 108 KB).
5. Supply chain: skills run `@latest` packages.
6. Licence: zhanymkanov has none.

## 6. Proposal

1. **Text-only rules → lint first.** Where possible, turn them into a ruff, import-linter,
   ESLint or architecture-test check. *Done in #69.*
2. **The rest → wrong/right examples** in the guides, mainly `frontend-style.md`.
   *Done in #69.*
3. Go through the official FastAPI, Pydantic and shadcn skills and take only rules we lack
   that do not contradict us, citing the source.
4. Optionally add the shadcn skill with a pinned CLI version, adapted to our tokens and the
   `dark:` ban.
5. Check any skill change with a small eval (a few typical tasks before and after); make
   no change without a measurable gain.
