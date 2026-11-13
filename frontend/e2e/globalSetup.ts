import { setSignupCode } from "./support/stack";

/**
 * One sign-up code for the whole run (ADR-007). Each spec signs up its own
 * organizer, and the spec files run in parallel workers: a code generated per
 * spec would replace the one another worker is about to use. The workers
 * inherit E2E_SIGNUP_CODE, which setSignupCode() then returns as it is.
 */
export default function globalSetup(): void {
  process.env.E2E_SIGNUP_CODE = setSignupCode();
}
