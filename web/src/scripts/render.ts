import { fetchData, flattenServices, todayISO, tomorrowISO, urlDateOverride } from "./flatten";
import { buildVisibilityFilter } from "./visibility";
import { formatTime, friendlyDay, friendlyGenerated } from "./format";
import type { Service } from "./types";

type Day = "today" | "tomorrow";

const $ = (id: string) => document.getElementById(id) as HTMLElement | null;

const STATE = {
  data: null as Awaited<ReturnType<typeof fetchData>> | null,
  selected: "today" as Day,
  includeNearby: false,
};

const CANCEL_RE = /\b(no\s+(?:[a-z]+\s+){0,3}(?:mass|service|liturgy)|mass\s+cancelled)\b/i;
function isCancellation(s: Service): boolean {
  return s.cancelled === true ||
    CANCEL_RE.test(s.type || "") ||
    CANCEL_RE.test(s.notes || "");
}

const baseDate = () => urlDateOverride() ?? todayISO();
function nextDate(): string {
  const base = baseDate();
  const [y, m, d] = base.split("-").map(Number);
  const dt = new Date(y!, m! - 1, d! + 1);
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
}
const selectedDate = () => STATE.selected === "tomorrow" ? nextDate() : baseDate();

function renderRow(s: Service): string {
  const time = isCancellation(s) ? "—" : formatTime(s.time);
  const place = s.postcode ? `${s.church || s.area || ""}, ${s.postcode}` : (s.church || s.area || "");
  const cancelled = isCancellation(s);
  const lang = s.language
    ? `<span class="ml-1 inline-block bg-tag-bg text-tag-ink rounded px-1.5 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide">${escapeHTML(s.language)}</span>`
    : "";
  const cancelPill = cancelled
    ? `<span class="ml-1 inline-block bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300 rounded px-1.5 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide">No Mass</span>`
    : "";
  const link = s.source_url
    ? `<a href="${escapeAttr(s.source_url)}" target="_blank" rel="noopener" title="Open parish newsletter" aria-label="Open parish newsletter" class="ml-1 text-ink-3 hover:text-accent no-underline">↗</a>`
    : "";
  const placeClass = cancelled ? "line-through text-ink-3" : "";
  const timeClass = cancelled ? "text-ink-3" : "text-accent";
  const areaClass = cancelled ? "text-ink-3" : "text-ink";
  return `
    <div class="grid grid-cols-[64px_minmax(0,1.1fr)_minmax(0,2fr)] gap-x-2.5 px-3 py-2 border-t border-rule first:border-t-0 items-baseline">
      <div class="tabular-nums font-bold text-[0.95rem] leading-snug whitespace-nowrap ${timeClass}">${time}</div>
      <div class="font-semibold break-words ${areaClass}">${escapeHTML(s.area || "")}</div>
      <div class="text-ink-2 break-words leading-snug min-w-0">
        <span class="${placeClass}">${escapeHTML(place)}</span>${lang}${cancelPill}${link}
      </div>
    </div>`;
}

function renderBucket(title: string, services: Service[], emptyText: string): string {
  if (!services.length) {
    return `
      <section class="my-3.5">
        <h3 class="flex items-center gap-1.5 text-[0.7rem] uppercase tracking-[0.1em] text-ink-3 m-0 mb-1.5 font-bold">${title}</h3>
        <div class="text-ink-3 text-[0.85rem] py-1">${emptyText}</div>
      </section>`;
  }
  return `
    <section class="my-3.5">
      <h3 class="flex items-center gap-1.5 text-[0.7rem] uppercase tracking-[0.1em] text-ink-3 m-0 mb-1.5 font-bold">${title} <span class="text-ink-3 font-medium text-[0.65rem]">${services.length}</span></h3>
      <div class="bg-surface border border-rule rounded-[10px] overflow-hidden">
        ${services.map(renderRow).join("")}
      </div>
    </section>`;
}

function escapeHTML(s: string): string {
  return s.replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!
  ));
}
function escapeAttr(s: string): string { return escapeHTML(s); }

function render(): void {
  if (!STATE.data) return;
  const all = flattenServices(STATE.data.parishes);
  const dayServices = all.filter(s => s.date === selectedDate());

  const visible = buildVisibilityFilter(dayServices, STATE.includeNearby);
  const display = dayServices.filter(visible).filter(s => !isCancellation(s));

  const masses = display.filter(s => s.bucket === "mass");
  const confessions = display.filter(s => s.bucket === "confession");
  const adoration = display.filter(s => s.bucket === "adoration");

  const sortByTime = (xs: Service[]) =>
    [...xs].sort((a, b) => (a.time || "99") < (b.time || "99") ? -1 : 1);

  const html = [
    renderBucket("Holy Mass", sortByTime(masses), "No Masses listed for this day."),
    renderBucket("Confession", sortByTime(confessions), "No confessions listed for this day."),
    renderBucket("Adoration", sortByTime(adoration), "No adoration listed for this day."),
  ].join("");

  const container = $("dayContainer");
  if (container) container.innerHTML = html;

  // Header + meta
  const subhead = $("subhead");
  if (subhead) subhead.textContent = friendlyDay(selectedDate());
  const meta = $("meta");
  if (meta && STATE.data.generated_at) {
    meta.innerHTML = `
      <span>Refreshed ${escapeHTML(friendlyGenerated(STATE.data.generated_at))}</span>
      <span class="dot opacity-50">·</span>
      <span>${STATE.data.parishes.length} parishes</span>`;
  }

  // Day toggle state
  $("btnToday")?.classList.toggle("day-btn-active", STATE.selected === "today");
  $("btnTomorrow")?.classList.toggle("day-btn-active", STATE.selected === "tomorrow");

  // Nearby toggle state
  $("btnNearby")?.setAttribute("aria-pressed", String(STATE.includeNearby));

  // Readings link tracks toggle
  const readings = $("btnReadings") as HTMLAnchorElement | null;
  if (readings) {
    readings.href = STATE.selected === "tomorrow"
      ? `/readings?date=${selectedDate()}`
      : "/readings";
  }

  // Reveal share actions only after first successful render
  $("actions")?.classList.remove("hidden");
}

async function init() {
  try {
    STATE.data = await fetchData();
    render();
  } catch (e) {
    const subhead = $("subhead");
    if (subhead) subhead.textContent = "Couldn't load mass times.";
  }

  $("btnToday")?.addEventListener("click", () => { STATE.selected = "today"; render(); });
  $("btnTomorrow")?.addEventListener("click", () => { STATE.selected = "tomorrow"; render(); });
  $("btnNearby")?.addEventListener("click", () => {
    STATE.includeNearby = !STATE.includeNearby;
    render();
  });
}

init();
