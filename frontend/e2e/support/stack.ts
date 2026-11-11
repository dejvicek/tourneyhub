import { execFileSync } from "node:child_process";

// Things only the stack's operator can do: the sign-up code is set with the
// CLI on the server, never over HTTP (ADR-007).

/**
 * Sets a new sign-up code with `tourneyhub set-signup-code --generate` in the
 * api container of the production stack and returns it. The project and its
 * configuration come from the environment, as in CI (COMPOSE_PROJECT_NAME,
 * COMPOSE_ENV_FILES) and from a .env locally (README).
 *
 * E2E_SIGNUP_CODE skips the CLI, for a runner that has no Docker: set the code
 * yourself with the same command, then pass it in.
 */
export function setSignupCode(): string {
  const given = process.env.E2E_SIGNUP_CODE;
  if (given !== undefined && given !== "") {
    return given;
  }
  const output = execFileSync(
    "docker",
    [
      "compose",
      "exec",
      "-T",
      "api",
      "tourneyhub",
      "set-signup-code",
      "--generate",
    ],
    // The repository root, where the Compose files are.
    { cwd: new URL("../../..", import.meta.url), encoding: "utf8" },
  );
  return output.trim();
}
