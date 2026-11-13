// Stand-ins for the request and response types of routes the backend does
// not have yet: the participants, late players and disabling (P14). The
// demo's contract (src/demo/contract.ts) builds its provisional paths on them,
// and the screens read them from here. Each type goes away once its route is
// generated into schema.d.ts (D4).
type Uuid = string;

export interface ParticipantRead {
  entry_id: Uuid;
  state: "playing" | "sat_out" | "disabled";
  /** The round a late player joined in; null for everyone from round 1. */
  joined_round: number | null;
  /** The round a disabled player was disabled in. */
  disabled_since_round: number | null;
  /** The newest round the entry sat out, if it sat out the latest round. */
  sat_out_round: number | null;
}

export interface DisabledWrite {
  disabled: boolean;
}

export interface LateEntryWrite {
  player_id: Uuid;
  /** The round the player is expected to start in. */
  from_round_no: number;
}
