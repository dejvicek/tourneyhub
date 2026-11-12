// Demo handlers: the instance admin's screens (FR-005, FR-006, ADR-007). The
// backend serves these routes; the handlers follow its schema
// (src/api/schema.d.ts) and P4's rules: every route is for an admin only,
// a code has 12 to 256 characters, a reset revokes the logins and requires a
// new password at the next login.
import { newId } from "@/lib/newId";

import { outsideError, validationFailed } from "../outsideErrors";
import { route } from "../route";
import type { StoredAccount } from "../seedOutside";
import { outsideDb } from "../store";

const SIGNUP_CODE_MIN_LENGTH = 12;
const SIGNUP_CODE_MAX_LENGTH = 256;
/** P2b's password rule (ADR-006), also for a temporary password. */
const MIN_PASSWORD_LENGTH = 15;
const MAX_PASSWORD_LENGTH = 1024;

/** The admin behind the request, or the error the server answers. */
function admin(): StoredAccount | Response {
  const { accounts, signedInUserId } = outsideDb();
  const account = accounts.find((row) => row.user.id === signedInUserId);
  if (!account) {
    return outsideError(401, "not_authenticated");
  }
  if (account.user.must_change_password) {
    return outsideError(403, "password_change_required");
  }
  return account.user.is_admin ? account : outsideError(403, "forbidden");
}

function signupCode() {
  const { signupCode: signup_code, signupCodeUpdatedAt: updated_at } =
    outsideDb();
  return { signup_code, updated_at };
}

function setCode(code: string | null): void {
  const state = outsideDb();
  state.signupCode = code;
  state.signupCodeUpdatedAt = new Date().toISOString();
}

export const adminHandlers = [
  route("get", "/api/v1/admin/signup-code", () => {
    const caller = admin();
    return caller instanceof Response ? caller : signupCode();
  }),

  route("put", "/api/v1/admin/signup-code", ({ body }) => {
    const caller = admin();
    if (caller instanceof Response) {
      return caller;
    }
    if (body.signup_code !== null) {
      const code = body.signup_code.trim();
      const length = Array.from(code).length;
      if (length < SIGNUP_CODE_MIN_LENGTH) {
        return validationFailed([
          {
            loc: ["body", "signup_code"],
            type: "string_too_short",
            min_length: SIGNUP_CODE_MIN_LENGTH,
          },
        ]);
      }
      if (length > SIGNUP_CODE_MAX_LENGTH) {
        return validationFailed([
          {
            loc: ["body", "signup_code"],
            type: "string_too_long",
            max_length: SIGNUP_CODE_MAX_LENGTH,
          },
        ]);
      }
      setCode(code);
    } else {
      setCode(null);
    }
    return signupCode();
  }),

  route("post", "/api/v1/admin/signup-code/generate", () => {
    const caller = admin();
    if (caller instanceof Response) {
      return caller;
    }
    // demo only: the backend makes it with `secrets`.
    setCode(`demo-${newId().replaceAll("-", "").slice(-17)}`);
    return signupCode();
  }),

  route("get", "/api/v1/admin/organizers", () => {
    const caller = admin();
    if (caller instanceof Response) {
      return caller;
    }
    return outsideDb()
      .accounts.toSorted((a, b) => {
        const [first, second] = [
          a.user.email.toLowerCase(),
          b.user.email.toLowerCase(),
        ];
        return Number(first > second) - Number(first < second);
      })
      .map(({ user, createdAt }) => ({
        id: user.id,
        email: user.email,
        display_name: user.display_name,
        is_admin: user.is_admin,
        must_change_password: user.must_change_password,
        created_at: createdAt,
      }));
  }),

  route(
    "post",
    "/api/v1/admin/organizers/{user_id}/password-reset",
    ({ params, body }) => {
      const caller = admin();
      if (caller instanceof Response) {
        return caller;
      }
      if (params.user_id === caller.user.id) {
        return outsideError(422, "own_account");
      }
      const target = outsideDb().accounts.find(
        (row) => row.user.id === params.user_id,
      );
      if (!target) {
        return outsideError(404, "user_not_found");
      }
      if (target.user.is_admin) {
        return outsideError(422, "admin_target");
      }
      const chosen = body.temporary_password ?? null;
      if (chosen !== null) {
        const length = Array.from(chosen).length;
        if (length < MIN_PASSWORD_LENGTH || length > MAX_PASSWORD_LENGTH) {
          return validationFailed([
            {
              loc: ["body", "temporary_password"],
              type:
                length < MIN_PASSWORD_LENGTH
                  ? "string_too_short"
                  : "string_too_long",
              min_length: MIN_PASSWORD_LENGTH,
            },
          ]);
        }
      }
      // demo only: the backend makes it with `secrets`.
      const generated = chosen === null ? `demo-${newId()}` : null;
      target.password = chosen ?? generated ?? "";
      target.user.must_change_password = true;
      return { temporary_password: generated };
    },
  ),
];
