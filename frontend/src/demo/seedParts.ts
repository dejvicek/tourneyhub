// The screen areas' additions to the demo seed, applied by createSeed() in
// seed.ts in this order. Each area adds one line for its own file, which
// exports a SeedPart and takes its ids from its range in ids.ts:
//
//   setup    seedSetup.ts    1000–1999
//   play     seedPlay.ts     2000–2999
//   finals   seedFinals.ts   3000–3999
//   outside  seedOutside.ts  4000–4999
import type { SeedPart } from "./seed";
import { seedFinals } from "./seedFinals";
import { seedSetup } from "./seedSetup";

export const seedParts: SeedPart[] = [seedSetup, seedFinals];
