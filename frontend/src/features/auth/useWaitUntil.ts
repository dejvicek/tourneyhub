import { useEffect, useState } from "react";

/**
 * The seconds left of a 429's waiting period (ADR-006), counting down once a
 * second; 0 when there is none. `start` begins a wait of `seconds`.
 */
export function useWaitUntil(): {
  remaining: number;
  start: (seconds: number) => void;
} {
  const [until, setUntil] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (until === null) {
      return undefined;
    }
    const timer = setInterval(() => {
      const time = Date.now();
      setNow(time);
      if (time >= until) {
        setUntil(null);
      }
    }, 250);
    return () => {
      clearInterval(timer);
    };
  }, [until]);

  return {
    remaining:
      until === null ? 0 : Math.max(0, Math.ceil((until - now) / 1000)),
    start: (seconds) => {
      const time = Date.now();
      setNow(time);
      setUntil(time + seconds * 1000);
    },
  };
}
