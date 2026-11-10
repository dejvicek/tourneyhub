// Demo handlers: accounts and login (FR-001–FR-004, ADR-006). Any email and
// password log in the demo organizer; the tokens are placeholders and no
// cookie is set.
import { DEMO_EMAIL } from "../ids";
import { route } from "../route";
import { db } from "../store";

const DEMO_ACCESS_TOKEN = "demo-access-token";

export const authHandlers = [
  route("get", "/api/v1/me", () => db().me),

  route("post", "/api/v1/auth/login", () => ({
    access_token: DEMO_ACCESS_TOKEN,
  })),
  route("post", "/api/v1/auth/refresh", () => ({
    access_token: DEMO_ACCESS_TOKEN,
  })),

  route(
    "post",
    "/api/v1/auth/signup",
    ({ body }) => {
      const me = db().me;
      me.email = body.email || DEMO_EMAIL;
      me.display_name = body.display_name || me.display_name;
      return me;
    },
    201,
  ),

  route("post", "/api/v1/auth/logout", () => null),
];
