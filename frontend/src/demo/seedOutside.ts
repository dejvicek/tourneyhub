// The outside area's part of the demo (auth, leagues, players, public), ids
// demoId(4000)–demoId(4999). It adds another organizer's league, which the
// demo organizer never sees (FR-007), and holds the demo's accounts and
// sessions. The credentials are fake seed values; the login screen shows
// them in demo mode only, read through GET /api/v1/demo/account, so they
// never reach a production bundle.
import type { UserRead } from "./contract";
import { DEMO_USER_ID, demoId } from "./ids";
import { DEFAULT_PLACEMENT_POINTS } from "./rules";
import type { SeedPart } from "./seed";

/** The demo organizer's password: 15 characters or more, as P2b requires. */
export const DEMO_PASSWORD = "thursday-foosball-demo";
/** The instance's sign-up code in the demo (FR-001). */
export const DEMO_SIGNUP_CODE = "FOOSBALL-2026";

/** A second organizer, so that ownership shows (FR-007). */
export const OTHER_ORGANIZER_ID = demoId(4000, "outside");
const OTHER_LEAGUE_ID = demoId(4001, "outside");

export const seedOutside: SeedPart = {
  area: "outside",
  add(state, kit) {
    state.leagues.push({
      id: OTHER_LEAGUE_ID,
      name: "Friday Kicker Club",
      created_at: "2026-09-04T18:00:00Z",
      updated_at: null,
      owner_id: OTHER_ORGANIZER_ID,
      draws_allowed: true,
      default_field_count: 1,
      default_match_format: "bo3",
      default_goals_per_game: 7,
      share_token: "demo-share-token-friday-Zp4mQ8rTv2Lw",
    });
    state.seasons.push({
      id: kit.id(4002),
      league_id: OTHER_LEAGUE_ID,
      number: 1,
      name: null,
      state: "active",
      placement_points: [...DEFAULT_PLACEMENT_POINTS],
      started_at: "2026-09-04T18:00:00Z",
      closed_at: null,
    });
    ["Karel Dvořák", "Ivana Malá"].forEach((name, i) => {
      state.players.push({
        id: kit.id(4010 + i),
        league_id: OTHER_LEAGUE_ID,
        name,
        removed_at: null,
      });
    });
  },
};

export interface StoredAccount {
  user: UserRead;
  password: string;
}

/** Failed attempts and the waiting period of one throttle (ADR-006). */
export interface Throttle {
  failures: number[];
  blockedUntil: number;
}

export interface OutsideState {
  accounts: StoredAccount[];
  /**
   * The user whose refresh cookie the browser holds, or null after a log
   * out. The demo starts signed in as the organizer, so that every screen
   * opens; a reload starts again from here.
   */
  signedInUserId: string | null;
  loginThrottle: Throttle;
  signupThrottle: Throttle;
}

export function createOutsideState(organizer: UserRead): OutsideState {
  return {
    accounts: [
      {
        // The seed's own user, so that PATCH /me and the shells agree.
        user: organizer,
        password: DEMO_PASSWORD,
      },
      {
        user: {
          id: OTHER_ORGANIZER_ID,
          email: "another@demo.tourneyhub.test",
          display_name: "Another Organizer",
          language: "cs",
          is_admin: false,
          must_change_password: false,
        },
        password: "another-organizer-password",
      },
    ],
    signedInUserId: DEMO_USER_ID,
    loginThrottle: { failures: [], blockedUntil: 0 },
    signupThrottle: { failures: [], blockedUntil: 0 },
  };
}
