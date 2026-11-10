/**
 * A UUIDv7 for a tournament the client creates (ADR-008): 48 bits of time,
 * the rest random. `getRandomValues` also works on pages served over plain
 * HTTP, where `randomUUID` does not exist.
 */
export function newTournamentId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  const now = Date.now();
  for (let i = 0; i < 6; i++) {
    bytes[i] = Math.floor(now / 2 ** (8 * (5 - i))) % 256;
  }
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x70;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0"));
  return [
    hex.slice(0, 4).join(""),
    hex.slice(4, 6).join(""),
    hex.slice(6, 8).join(""),
    hex.slice(8, 10).join(""),
    hex.slice(10).join(""),
  ].join("-");
}
