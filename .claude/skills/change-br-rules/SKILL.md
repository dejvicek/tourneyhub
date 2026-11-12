---
name: change-br-rules
description: Changes TourneyHub business rules (BR-xxx in docs/product/PRD.md §7) according to a review, then has two independent subagents check the new wording for contradictions and edge cases. Use when asked to revise, add or fix BR rules.
argument-hint: "<BR IDs> <review: PR or issue number, or link>"
---

Change the rules $ARGUMENTS in `docs/product/PRD.md` (§7 Business rules) according to the review I point to.

1. Read the review and the affected rules. If the review is on a different PR or issue than I said, stop and say so.
2. Make the minimal change. No ADR history, no extra CI checks, no rewording beyond what the review asks. If a rewording changes meaning or gets longer, show before/after and ask first.
3. Then start two independent subagents in parallel, both `sonnet` with effort `medium`, read-only (they change no files in the repository):
   - A) Looks for contradictions in the order and priority of the changed rules and in their interaction with the other BR rules.
   - B) Checks edge cases with a throwaway simulation of the **new wording**: a standalone pure-Python model of the changed rules, run on many random tournaments plus the edge cases. It does not use the code in `backend/`, because that code still implements the old rules. The script lives in a temporary directory outside the repository and runs with `python3 -I`.
   Each subagent returns at most ~200 words: only real problems, each with the rule ID and evidence.
4. Output the findings as a numbered list: `<n>. <rule ID>: <problem in one sentence> → fix: <minimal change>`. Nothing beyond real problems.
5. Do not commit or push. Wait for my approval of specific findings.

Reply in Czech.
