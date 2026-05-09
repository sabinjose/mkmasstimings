import type { Bucket, RawData, RawParish, RawService, Service } from "./types";

const HIDDEN_TYPES = new Set(["rosary"]);

export function classify(svc: RawService): Bucket {
  const t = (svc.type || "").toLowerCase();
  if (t.includes("vigil") || t === "mass") return "mass";
  if (t.includes("confession") || t.includes("reconciliation")) return "confession";
  return "adoration";
}

export function flattenServices(parishes: RawParish[]): Service[] {
  const out: Service[] = [];
  for (const p of parishes) {
    if (p.error) continue;
    for (const s of p.services || []) {
      if (HIDDEN_TYPES.has((s.type || "").toLowerCase())) continue;
      const cancelled = !!s.cancelled;
      out.push({
        ...s,
        parish: p.parish,
        location: p.location || "",
        source_url: p.source_url || "",
        outside_mk: !!p.outside_mk,
        parish_key: p.location || p.parish || "",
        bucket: cancelled ? "mass" : classify(s),
        cancelled,
      });
    }
  }
  return out;
}

export function isToday(s: Service, isoDate: string): boolean {
  return s.date === isoDate;
}

export function todayISO(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

export function tomorrowISO(): string {
  const now = new Date();
  now.setDate(now.getDate() + 1);
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

/** Resolve `?date=YYYY-MM-DD` query override (QA hook). */
export function urlDateOverride(): string | null {
  if (typeof window === "undefined") return null;
  const q = new URLSearchParams(window.location.search).get("date");
  return q && /^\d{4}-\d{2}-\d{2}$/.test(q) ? q : null;
}

export async function fetchData(): Promise<RawData> {
  const r = await fetch("/data/latest.json", { cache: "no-cache" });
  if (!r.ok) throw new Error(`fetch failed: ${r.status}`);
  return await r.json();
}
