import { useSyncExternalStore } from "react";

/** The three layouts of the Figma frames: phone, tablet and desktop. */
export type Layout = "phone" | "tablet" | "desktop";

// Tailwind's md and lg breakpoints, where the Figma frames change layout.
// The shell picks its navigation in script, so that each layout renders one
// navigation, and tests can choose a layout through matchMedia.
const TABLET = "(min-width: 48rem)";
const DESKTOP = "(min-width: 64rem)";

function subscribe(onChange: () => void): () => void {
  const queries = [matchMedia(TABLET), matchMedia(DESKTOP)];
  for (const query of queries) {
    query.addEventListener("change", onChange);
  }
  return () => {
    for (const query of queries) {
      query.removeEventListener("change", onChange);
    }
  };
}

function currentLayout(): Layout {
  if (matchMedia(DESKTOP).matches) {
    return "desktop";
  }
  return matchMedia(TABLET).matches ? "tablet" : "phone";
}

/** The layout for the viewport's width, mobile-first. */
export function useLayout(): Layout {
  return useSyncExternalStore(subscribe, currentLayout);
}
