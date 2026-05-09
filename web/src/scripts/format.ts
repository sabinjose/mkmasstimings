/** Format a 24h "HH:MM" as 12-hour with am/pm; missing time renders as em-dash. */
export function formatTime(t?: string | null): string {
  if (!t) return "—";
  const m = /^(\d{1,2}):(\d{2})$/.exec(t);
  if (!m) return t;
  let h = parseInt(m[1]!, 10);
  const min = m[2]!;
  const am = h < 12;
  if (h === 0) h = 12;
  else if (h > 12) h -= 12;
  return min === "00" ? `${h}${am ? "am" : "pm"}` : `${h}:${min}${am ? "am" : "pm"}`;
}

/** Friendly day label for a YYYY-MM-DD string (e.g. "Saturday, May 9"). */
export function friendlyDay(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y!, m! - 1, d!);
  return dt.toLocaleDateString("en-GB", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

/** Friendly timestamp for the data's generated_at field. */
export function friendlyGenerated(ts?: string): string {
  if (!ts) return "";
  const dt = new Date(ts);
  if (isNaN(dt.getTime())) return "";
  return dt.toLocaleString("en-GB", {
    month: "long",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
