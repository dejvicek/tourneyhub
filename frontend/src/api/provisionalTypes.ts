// Stand-ins for the request and response types of routes the backend does
// not have yet: late players (P14). The
// provisional paths (src/api/provisionalPaths.ts) are built on them,
// and the screens read them from here. Each type goes away once its route is
// generated into schema.d.ts (D4).
type Uuid = string;

export interface LateEntryWrite {
  player_id: Uuid;
  /** The round the player is expected to start in. */
  from_round_no: number;
}
