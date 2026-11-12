---
name: finish-pr
description: Finishes a TourneyHub pull request in its own worktree with approval gates - lists the findings (what is missing), implements only approved findings, repeats the checks until they pass, commits locally and pushes only after an explicit "push". Use when asked to finish, complete or carry a PR to done.
argument-hint: "<PR number> [brief file]"
---

Finish PR $ARGUMENTS. Work in stages and stop at every gate marked STOP.

Copy this checklist into your first reply and tick it off as you go:

```
- [ ] 0. Worktree ready
- [ ] 1. Findings listed — STOP for approval
- [ ] 2. Approved findings implemented
- [ ] 3. Checks pass (max 5 rounds)
- [ ] 4. Committed locally, summary sent — STOP for "push"
- [ ] 5. Pushed, CI passes, PR description and comment updated
```

## 0. Worktree
- `gh pr view <N>` for the branch name, then `git fetch origin <branch>`. Use its worktree in `.worktrees/` (`git worktree list`); if there is none, create one: `git worktree add .worktrees/<short-name> <branch>`.
- Do not pull or reset an existing worktree. If it differs from `origin/<branch>` (local commits, or behind), say so with the findings in step 1.
- Edit files only inside that worktree. Never edit the main checkout.
- Never run `docker compose up`/`down` from the worktree: the Compose project name is fixed, so it would replace the main stack. Step 3 has the right command.

## 1. Findings → STOP
- Read the brief file if given, the PR description and comments (`gh pr view <N> --comments`), the diff (`gh pr diff <N>`) and the relevant `docs/` (PRD `FR-xxx`/`BR-xxx`, ADR, DATA-MODEL).
- Output the findings (missing or wrong points) as a numbered list: `<n>. <file>:<line> — <rule ID, if any>: <what is missing or wrong> → fix: <minimal change>`.
- STOP. Change nothing until I approve specific numbers.

## 2. Implement approved findings only
- Exactly the approved numbers, minimal. No ADR history, no extra CI checks, no rule rewording beyond what was approved. Follow the `python-style` / `frontend-style` skills and cite rule IDs as CLAUDE.md says.
- After changing an API route or model, regenerate the worktree's `backend/openapi.json` from the repository root with `docker compose run --rm --no-deps -T -v "$PWD/.worktrees/<short-name>/backend:/src" api sh -c 'python -W error -m tourneyhub.openapi > openapi.json'`. The command in CLAUDE.md writes to the main checkout.

## 3. Checks until they pass (max 5 rounds)
- Run `.claude/scripts/check-worktree.sh <worktree>` from the repository root. It runs the CI checks for the changed areas on the worktree's code and prints PASS/FAIL per area. Exit 2 means an environment problem (for example the dev stack is not running): report it and STOP.
- Fix and run the checks again. If they still fail after 5 rounds, STOP and report what blocks.

## 4. Commit locally → STOP
- Small focused commits in the project's gitmoji Conventional Commits style.
- Send a short summary: commits, what changed, check results.
- STOP. Do not push until I write "push".

## 5. After "push"
- Push, then watch CI (`gh pr checks <N> --watch`). If CI fails, report it and go back to step 3 (a new push needs a new "push"); do not change the PR description or comment while CI fails.
- When CI passes, update the PR description to match the pushed state and add a short comment summarising the change. The "push" covers these two updates.

Reply in Czech.
