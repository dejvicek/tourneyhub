// Demo handlers: accounts and login (FR-001–FR-004, ADR-006). The backend
// serves these routes; the handlers follow its schema (src/api/schema.d.ts).
// Any email and password log in the demo organizer; the tokens are
// placeholders and no cookie is set.
import { apiError, route } from "../route";
import { db } from "../store";

const DEMO_ACCESS_TOKEN = "demo-access-token";

export const authHandlers = [
  route("get", "/api/v1/me", () => db().me),

  route("patch", "/api/v1/me", ({ body }) => {
    const me = db().me;
    me.display_name = body.display_name ?? me.display_name;
    me.language = body.language ?? me.language;
    return me;
  }),

  route("post", "/api/v1/auth/login", () => ({
    access_token: DEMO_ACCESS_TOKEN,
  })),
  route("post", "/api/v1/auth/refresh", () => ({
    access_token: DEMO_ACCESS_TOKEN,
  })),

  // Any sign-up code is accepted; the account becomes the demo organizer.
  route(
    "post",
    "/api/v1/auth/signup",
    ({ body }) => {
      const me = db().me;
      me.email = body.email;
      me.display_name = body.display_name;
      me.language = body.language;
      return { access_token: DEMO_ACCESS_TOKEN };
    },
    201,
  ),

  route("post", "/api/v1/auth/password", ({ body }) => {
    if (body.new_password === body.current_password) {
      return apiError(422, "password_unchanged");
    }
    db().me.must_change_password = false;
    return null;
  }),

  route("post", "/api/v1/auth/logout", () => null),
];
