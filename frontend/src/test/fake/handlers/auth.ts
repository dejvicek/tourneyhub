// Fake handlers: accounts, login and the session (FR-001–FR-004, ADR-006).
// The backend serves these routes; the handlers follow its schema
// (src/api/schema.d.ts) and P2b's rules. The browser's refresh cookie is
// stood in for by outsideDb().signedInUserId; the tokens are placeholders.
import { http, HttpResponse } from "msw";

import { newId } from "@/lib/newId";

import type { UserRead } from "../contract";
import { TEST_EMAIL } from "../ids";
import {
  nameProblem,
  outsideError,
  type Problem,
  validationFailed,
} from "../outsideErrors";
import { route } from "../route";
import {
  type StoredAccount,
  TEST_PASSWORD,
  TEST_SIGNUP_CODE,
  type Throttle,
} from "../seedOutside";
import { outsideDb } from "../store";

const TEST_ACCESS_TOKEN = "demo-access-token";
/** P2b's MIN_PASSWORD_LENGTH (ADR-006; FR-002 says 12, a PRD question). */
const MIN_PASSWORD_LENGTH = 15;
const EMAIL = /^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$/;

interface ThrottleRule {
  freeFailures: number;
  windowMs: number;
  maxWaitSeconds: number;
}

// ADR-006 as P2b implements it: login 3 free failures in 15 minutes, then a
// wait doubling from 1 s up to 8 s; sign-up 5 in an hour, up to 15 minutes.
const LOGIN: ThrottleRule = {
  freeFailures: 3,
  windowMs: 15 * 60_000,
  maxWaitSeconds: 8,
};
const SIGNUP: ThrottleRule = {
  freeFailures: 5,
  windowMs: 60 * 60_000,
  maxWaitSeconds: 15 * 60,
};

/** 429 while the waiting period runs; the attempt is not counted. */
function throttled(throttle: Throttle): Response | undefined {
  const waitMs = throttle.blockedUntil - Date.now();
  if (waitMs <= 0) {
    return undefined;
  }
  const seconds = Math.ceil(waitMs / 1000);
  return outsideError(
    429,
    "too_many_attempts",
    { retry_after: seconds },
    { "Retry-After": String(seconds) },
  );
}

function fail(throttle: Throttle, rule: ThrottleRule): void {
  const now = Date.now();
  throttle.failures = [
    ...throttle.failures.filter((at) => now - at < rule.windowMs),
    now,
  ];
  const over = throttle.failures.length - rule.freeFailures;
  if (over > 0) {
    const seconds = Math.min(rule.maxWaitSeconds, 2 ** (over - 1));
    throttle.blockedUntil = now + seconds * 1000;
  }
}

function findAccount(email: string): StoredAccount | undefined {
  const wanted = email.trim().toLowerCase();
  return outsideDb().accounts.find(
    (account) => account.user.email.toLowerCase() === wanted,
  );
}

function signedInAccount(): StoredAccount | undefined {
  const { accounts, signedInUserId } = outsideDb();
  return accounts.find((account) => account.user.id === signedInUserId);
}

const notAuthenticated = () => outsideError(401, "not_authenticated");

function passwordProblem(password: string, field: string): Problem | undefined {
  // Counted in characters, not bytes (P2b decision 1).
  return Array.from(password).length < MIN_PASSWORD_LENGTH
    ? {
        loc: ["body", field],
        type: "string_too_short",
        min_length: MIN_PASSWORD_LENGTH,
      }
    : undefined;
}

export const authHandlers = [
  route("get", "/api/v1/me", () => {
    const account = signedInAccount();
    return account ? account.user : notAuthenticated();
  }),

  route("patch", "/api/v1/me", ({ body }) => {
    const account = signedInAccount();
    if (!account) {
      return notAuthenticated();
    }
    const me = account.user;
    me.display_name = body.display_name ?? me.display_name;
    me.language = body.language ?? me.language;
    return me;
  }),

  // Demo only: what the login screen shows in demo mode.
  route("get", "/api/v1/demo/account", () => ({
    email: TEST_EMAIL,
    password: TEST_PASSWORD,
    signup_code: outsideDb().signupCode ?? TEST_SIGNUP_CODE,
  })),

  route("post", "/api/v1/auth/login", ({ body }) => {
    const state = outsideDb();
    const wait = throttled(state.loginThrottle);
    if (wait) {
      return wait;
    }
    const account = findAccount(body.email);
    // A wrong password and an unknown email get the same 401 (P2a).
    if (account?.password !== body.password) {
      fail(state.loginThrottle, LOGIN);
      return notAuthenticated();
    }
    state.signedInUserId = account.user.id;
    return { access_token: TEST_ACCESS_TOKEN };
  }),

  // Refresh and logout send no body, which route() would parse.
  http.post("/api/v1/auth/refresh", () =>
    signedInAccount()
      ? HttpResponse.json({ access_token: TEST_ACCESS_TOKEN })
      : notAuthenticated(),
  ),

  http.post("/api/v1/auth/logout", () => {
    outsideDb().signedInUserId = null;
    return new HttpResponse(null, { status: 204 });
  }),

  route(
    "post",
    "/api/v1/auth/signup",
    ({ body }) => {
      const state = outsideDb();
      // The body is validated before the throttle counts it (P2b decision 2).
      const problems = [
        EMAIL.test(body.email)
          ? undefined
          : { loc: ["body", "email"], type: "string_pattern_mismatch" },
        nameProblem(body.display_name, ["body", "display_name"]),
        passwordProblem(body.password, "password"),
      ].filter((problem) => problem !== undefined);
      if (problems.length > 0) {
        return validationFailed(problems);
      }
      const wait = throttled(state.signupThrottle);
      if (wait) {
        return wait;
      }
      // The code first, so a stranger learns no email address (P2b decision 3).
      // Sign-up is closed while the admin has cleared the code (FR-005).
      if (
        state.signupCode === null ||
        body.signup_code.trim() !== state.signupCode
      ) {
        fail(state.signupThrottle, SIGNUP);
        return outsideError(422, "invalid_signup_code");
      }
      if (findAccount(body.email)) {
        fail(state.signupThrottle, SIGNUP);
        return outsideError(422, "email_taken");
      }
      const user: UserRead = {
        id: newId(),
        email: body.email.trim(),
        display_name: body.display_name.trim(),
        language: body.language,
        is_admin: false,
        must_change_password: false,
      };
      state.accounts.push({
        user,
        password: body.password,
        createdAt: new Date().toISOString(),
      });
      state.signedInUserId = user.id;
      return { access_token: TEST_ACCESS_TOKEN };
    },
    201,
  ),

  route("post", "/api/v1/auth/password", ({ body }) => {
    const account = signedInAccount();
    if (!account) {
      return notAuthenticated();
    }
    const problem = passwordProblem(body.new_password, "new_password");
    if (problem) {
      return validationFailed([problem]);
    }
    // 422, never 401, which would make the client refresh (P2b decision 5).
    if (body.current_password !== account.password) {
      return outsideError(422, "wrong_password");
    }
    if (body.new_password === account.password) {
      return outsideError(422, "password_unchanged");
    }
    account.password = body.new_password;
    account.user.must_change_password = false;
    return null;
  }),
];
