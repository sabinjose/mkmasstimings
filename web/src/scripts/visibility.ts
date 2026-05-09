import type { Service } from "./types";

type TimeBucket = "morning" | "afternoon" | "evening" | "anytime";

function timeOfDay(t?: string | null): TimeBucket {
  if (!t) return "anytime";
  const m = /^(\d{1,2}):/.exec(t);
  if (!m) return "anytime";
  const h = parseInt(m[1]!, 10);
  if (h < 12) return "morning";
  if (h < 17) return "afternoon";
  return "evening";
}

/** Decide which services to show given the user's outside-MK toggle.
 *
 * Rules when toggle OFF:
 * - MK parishes: always shown.
 * - Outside-MK Mass: shown only when its time-of-day bucket is NOT covered
 *   by an MK Mass that day.
 * - Outside-MK Confession / Adoration: shown only when its parish has at
 *   least one Mass that passed the gap rule.
 *
 * Toggle ON: include everything.
 */
export function buildVisibilityFilter(
  services: Service[],
  includeNearby: boolean,
): (s: Service) => boolean {
  if (includeNearby) return () => true;

  const mkMassBuckets = new Set<TimeBucket>();
  for (const s of services) {
    if (!s.outside_mk && s.bucket === "mass" && !s.cancelled && s.time) {
      mkMassBuckets.add(timeOfDay(s.time));
    }
  }

  const massGapFillers = new WeakSet<Service>();
  const massGapParishes = new Set<string>();
  for (const s of services) {
    if (!s.outside_mk) continue;
    if (s.bucket !== "mass" || s.cancelled || !s.time) continue;
    if (!mkMassBuckets.has(timeOfDay(s.time))) {
      massGapFillers.add(s);
      massGapParishes.add(s.parish_key);
    }
  }

  return (s) => {
    if (!s.outside_mk) return true;
    if (s.bucket === "mass") return massGapFillers.has(s);
    return massGapParishes.has(s.parish_key);
  };
}
