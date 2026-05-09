import type { RawData, Service } from "./types";
import { flattenServices } from "./flatten";
import { buildVisibilityFilter } from "./visibility";
import { formatTime, friendlyDay } from "./format";

interface ShareContext {
  data: RawData;
  date: string;        // selected ISO date
  label: "Today" | "Tomorrow";
  includeNearby: boolean;
}

function placeText(s: Service): string {
  const place = s.postcode ? `${s.church || s.area || ""}, ${s.postcode}` : (s.church || s.area || "");
  return s.language ? `${place} (${s.language})` : place;
}

/** Pad rows into three space-aligned columns (time | area | place) inside
 * a monospace block. WhatsApp / Telegram / Slack render ``` ``` as fixed-
 * width so columns line up; on clients without monospace support the
 * spaces still read fine because ` · ` separators were dropped — the gaps
 * themselves serve as the divider. */
function formatBlock(label: string, services: Service[]): string {
  if (!services.length) return "";
  const rows = services.map((s) => ({
    time: formatTime(s.time),
    area: s.area || "",
    place: placeText(s),
  }));
  const w1 = Math.max(...rows.map((r) => r.time.length));
  const w2 = Math.max(...rows.map((r) => r.area.length));
  const lines = rows.map((r) =>
    `${r.time.padEnd(w1)}  ${r.area.padEnd(w2)}  ${r.place}`
  );
  return [`*${label}*`, "```", ...lines, "```"].join("\n");
}

function plainTextForDay(ctx: ShareContext): string {
  const all = flattenServices(ctx.data.parishes);
  const dayServices = all.filter((s) => s.date === ctx.date);
  const visible = buildVisibilityFilter(dayServices, ctx.includeNearby);
  const services = dayServices.filter(visible).filter((s) => !s.cancelled);

  const sortByTime = (xs: Service[]) =>
    [...xs].sort((a, b) => (a.time || "99") < (b.time || "99") ? -1 : 1);

  const sections = [
    formatBlock("Holy Mass",  sortByTime(services.filter((s) => s.bucket === "mass"))),
    formatBlock("Confession", sortByTime(services.filter((s) => s.bucket === "confession"))),
    formatBlock("Adoration",  sortByTime(services.filter((s) => s.bucket === "adoration"))),
  ].filter(Boolean);

  const head = `*Mass Times — ${ctx.label}, ${friendlyDay(ctx.date)}*`;
  if (!sections.length) return [head, "", "_(no services listed)_"].join("\n");
  return [head, "", sections.join("\n\n")].join("\n");
}

export function buildShareText(ctx: ShareContext): string {
  const host = (location.host || "mkmasstimings.pages.dev").replace(/^www\./, "");
  return [plainTextForDay(ctx), "", host].join("\n");
}

export function shareWhatsApp(ctx: ShareContext): void {
  window.open("https://wa.me/?text=" + encodeURIComponent(buildShareText(ctx)), "_blank", "noopener");
}

export async function copyText(ctx: ShareContext, btn: HTMLElement): Promise<void> {
  const text = buildShareText(ctx);
  const original = btn.innerHTML;
  try {
    await navigator.clipboard.writeText(text);
    btn.innerHTML = `<span class="inline-flex items-center gap-1.5">✓ Copied</span>`;
    btn.classList.add("btn-copied");
    setTimeout(() => {
      btn.innerHTML = original;
      btn.classList.remove("btn-copied");
    }, 1800);
  } catch {
    const w = window.open("", "_blank");
    if (w) {
      w.document.write(
        "<pre style='white-space:pre-wrap;font:14px monospace;padding:24px'>" +
        text.replace(/[<>&]/g, (c) => ({"<":"&lt;",">":"&gt;","&":"&amp;"}[c]!)) +
        "</pre>",
      );
    }
  }
}

let _html2canvasPromise: Promise<any> | null = null;
function loadHtml2Canvas(): Promise<any> {
  if (_html2canvasPromise) return _html2canvasPromise;
  _html2canvasPromise = new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js";
    s.onload = () => resolve((window as any).html2canvas);
    s.onerror = reject;
    document.head.appendChild(s);
  });
  return _html2canvasPromise;
}

export async function saveAsImage(ctx: ShareContext, btn: HTMLButtonElement): Promise<void> {
  const original = btn.innerHTML;
  btn.innerHTML = `<span class="inline-flex items-center gap-1.5">⏳ Generating…</span>`;
  btn.disabled = true;
  try {
    const html2canvas = await loadHtml2Canvas();
    const dayContainer = document.getElementById("dayContainer");
    if (!dayContainer) throw new Error("no content");

    const stage = document.createElement("div");
    const bs = getComputedStyle(document.body);
    stage.style.cssText = `
      position: fixed; left: -9999px; top: 0;
      width: 720px; padding: 24px 28px;
      background: ${bs.backgroundColor};
      color: ${bs.color};
      font: ${bs.font};
    `;
    stage.innerHTML = `
      <div style="margin-bottom:14px">
        <div style="font-weight:700; font-size:1.15rem; margin-bottom:2px">
          Mass Times — ${ctx.label}, ${friendlyDay(ctx.date)}
        </div>
        <div style="color: var(--color-ink-3); font-size: 0.78rem">
          mkmasstimings.pages.dev · refreshed ${
            ctx.data.generated_at
              ? new Date(ctx.data.generated_at).toLocaleDateString(undefined, { dateStyle: "medium" })
              : ""
          }
        </div>
      </div>
      ${dayContainer.innerHTML}
    `;
    document.body.appendChild(stage);
    try {
      const canvas = await html2canvas(stage, {
        backgroundColor: bs.backgroundColor,
        scale: window.devicePixelRatio > 1 ? 2 : 1.5,
        useCORS: true,
        logging: false,
      });
      const blob: Blob | null = await new Promise((r) => canvas.toBlob(r, "image/png"));
      if (!blob) throw new Error("toBlob failed");
      const filename = `mass-times-${ctx.label.toLowerCase()}-${ctx.date}.png`;
      const file = new File([blob], filename, { type: "image/png" });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        await navigator.share({ files: [file], title: "Mass Times" });
      } else {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    } finally {
      stage.remove();
    }
    btn.innerHTML = `<span class="inline-flex items-center gap-1.5">✓ Saved</span>`;
    btn.classList.add("btn-copied");
    setTimeout(() => {
      btn.innerHTML = original;
      btn.classList.remove("btn-copied");
    }, 1800);
  } catch (e) {
    console.error(e);
    btn.innerHTML = `<span class="inline-flex items-center gap-1.5">❌ Failed</span>`;
    setTimeout(() => { btn.innerHTML = original; }, 1800);
  } finally {
    btn.disabled = false;
  }
}
