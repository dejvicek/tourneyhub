---
name: review-pr
description: Reviews a TourneyHub pull request read-only against its brief file, the PRD, ADRs and BR-xxx rules, runs the checks on the PR's own code and reports numbered findings. Use when asked to review or check a PR. Never edits, commits or pushes.
argument-hint: "<PR number> [brief file]"
---

Review PR $ARGUMENTS. STRICTLY READ-ONLY: no edits, commits, pushes, PR description changes or PR comments. The only allowed change is creating a worktree in step 3.

1. Run `gh pr view <N> --comments` and `gh pr diff <N>`. Check that the PR number matches the reviewer comments and the brief file. If they point to a different PR, stop and say so.
2. If a brief file was given, review against it exactly and do not go beyond its scope. Compare the diff with the relevant documents in `docs/` (PRD `FR-xxx` / `BR-xxx`, ADR, DATA-MODEL). Check that code and tests cite the rule IDs they implement.
3. Run the checks on the PR's code, not on the main checkout (the dev container mounts the main checkout, which is on `main`):
   - Find the worktree of the PR branch (`git worktree list`). If there is none, run `git fetch origin <branch>` and `git worktree add .worktrees/<short-name> <branch>`.
   - Do not pull or reset an existing worktree. If it differs from `origin/<branch>` (local commits, or behind), say so in the report and name the commit you checked.
   - Run `.claude/scripts/check-worktree.sh <worktree>` from the repository root. It checks the changed areas and prints PASS/FAIL per area. Report the result and the test counts. Exit 2 means an environment problem (for example the dev stack is not running): report it and stop; do not start, stop or rebuild containers.
4. Output the findings as a numbered list in exactly this format:
   ```
   <n>. [blocking|non-blocking] <file>:<line> — <rule ID, if any>: <problem in one sentence> → fix: <minimal change>
   ```
   Example: `3. [blocking] backend/src/tourneyhub/engine/swiss.py:142 — BR-057: a repeat pairing is allowed although another pairing exists → fix: check repeats before falling back to the matching.`
   No ADR history, no extra CI checks, no rewording of rules beyond the finding.
5. Stop and wait. I approve findings by number. This skill fixes nothing: approved findings are fixed with `/finish-pr`.

Reply in Czech.
