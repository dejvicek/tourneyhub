import { vi } from "vitest";

/**
 * A matchMedia for a viewport `width` px wide, answering min-width queries
 * in px or rem (16 px), as useLayout asks them. jsdom has no matchMedia.
 */
export function stubViewport(width: number): void {
  vi.stubGlobal("matchMedia", (query: string) => {
    const match = /min-width:\s*([\d.]+)(px|rem)/.exec(query);
    const min = match ? Number(match[1]) * (match[2] === "rem" ? 16 : 1) : 0;
    return {
      matches: width >= min,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    };
  });
}
