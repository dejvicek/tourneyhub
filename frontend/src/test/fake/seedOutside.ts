// The outside area's part of the fake API's seed (auth, leagues, players, public), ids
// testId(4000)–testId(4999). It adds another organizer's league, which the
// seeded organizer never sees (FR-007), and holds the fake API's accounts and
// sessions. The credentials are fake seed values for tests only.
import { DEFAULT_PLACEMENT_POINTS } from "@/lib/rules";

import type { UserRead } from "./contract";
import { TEST_USER_ID, testId } from "./ids";
import type { SeedPart } from "./seed";

/** The seeded organizer's password: 15 characters or more, as P2b requires. */
export const TEST_PASSWORD = "thursday-foosball-test";
/** The instance's sign-up code in the fake API (FR-001). */
export const TEST_SIGNUP_CODE = "FOOSBALL-2026";

/** A second organizer, so that ownership shows (FR-007). */
export const OTHER_ORGANIZER_ID = testId(4000, "outside");
const OTHER_LEAGUE_ID = testId(4001, "outside");

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
      share_token: "test-share-token-friday-Zp4mQ8rTv2Lw",
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
   * out. The fake API starts signed in as the organizer, so that every screen
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
        password: TEST_PASSWORD,
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
          id: testId(4003, "outside"),
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
          id: testId(4004, "outside"),
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
    signedInUserId: TEST_USER_ID,
    signupCode: TEST_SIGNUP_CODE,
    signupCodeUpdatedAt: "2026-08-20T17:30:00Z",
    loginThrottle: { failures: [], blockedUntil: 0 },
    signupThrottle: { failures: [], blockedUntil: 0 },
  };
}
