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
  /** ISO 8601, for the admin's list. */
  createdAt: string;
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
  /** The instance's sign-up code, or null while sign-up is closed (FR-005). */
  signupCode: string | null;
  /** When the code last changed, ISO 8601. */
  signupCodeUpdatedAt: string | null;
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
        createdAt: "2026-08-20T17:30:00Z",
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
        createdAt: "2026-09-04T17:45:00Z",
      },
      {
        user: {
          id: demoId(4003, "outside"),
          email: "eva.novakova@demo.tourneyhub.test",
          display_name: "Eva Nováková",
          language: "cs",
          is_admin: false,
          // Reset by the admin, has not logged in since (ADR-006).
          must_change_password: true,
        },
        password: "temporary-password-eva",
        createdAt: "2026-09-18T19:10:00Z",
      },
      {
        user: {
          id: demoId(4004, "outside"),
          email: "tomas.cerny@demo.tourneyhub.test",
          display_name: "Tomáš Černý",
          language: "en",
          is_admin: false,
          must_change_password: false,
        },
        password: "tomas-organizer-password",
        createdAt: "2026-10-02T16:20:00Z",
      },
    ],
    signedInUserId: DEMO_USER_ID,
    signupCode: DEMO_SIGNUP_CODE,
    signupCodeUpdatedAt: "2026-08-20T17:30:00Z",
    loginThrottle: { failures: [], blockedUntil: 0 },
    signupThrottle: { failures: [], blockedUntil: 0 },
  };
}
