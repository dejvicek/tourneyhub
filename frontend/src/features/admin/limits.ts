/** P4's sign-up code length (ADR-007): 12 to 256 characters. */
export const SIGNUP_CODE_MIN_LENGTH = 12;
export const SIGNUP_CODE_MAX_LENGTH = 256;
/** The longest password the server accepts (ADR-006). */
export const MAX_PASSWORD_LENGTH = 1024;

/** Length as the server counts it: in characters, not UTF-16 units. */
export function lengthOf(value: string): number {
  return Array.from(value).length;
}
