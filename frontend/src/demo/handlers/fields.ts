// Demo handlers: fields (FR-090–FR-094, BR-130–BR-135). The placements come
// with the tournament (GET …/tournaments/{tournament_id}); the screens for
// moving a match and adding or removing fields (6c, 6d) add their writes
// here, as target states (ADR-008).
import type { route } from "../route";

export const fieldHandlers: ReturnType<typeof route>[] = [];
