interface ReadingPayload {
  heading?: string;
  source?: string;
  text?: string;
}

interface UniversalisData {
  number?: number;
  date?: string;
  day?: string;
  Mass_R1?: ReadingPayload;
  Mass_Ps?: ReadingPayload;
  Mass_R2?: ReadingPayload;
  Mass_GA?: ReadingPayload;
  Mass_G?: ReadingPayload;
  copyright?: { text?: string };
}

declare global {
  interface Window {
    universalisCallback?: (d: UniversalisData) => void;
  }
}

const FONT_KEY = "mkmt-readings-font-size";

function pickDate() {
  const q = new URLSearchParams(location.search).get("date");
  if (q && /^\d{4}-\d{2}-\d{2}$/.test(q)) {
    const [y, m, d] = q.split("-");
    return { iso: q, compact: `${y}${m}${d}` };
  }
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return { iso: `${y}-${m}-${d}`, compact: `${y}${m}${d}` };
}

function applyFontSize(size: string) {
  document.documentElement.style.setProperty("--reading-fs", size);
  localStorage.setItem(FONT_KEY, size);
  document.querySelectorAll<HTMLButtonElement>(".font-controls button").forEach((btn) => {
    btn.setAttribute("aria-pressed", btn.dataset.size === size ? "true" : "false");
  });
}

function initFontSize() {
  const saved = localStorage.getItem(FONT_KEY) || "1.05rem";
  applyFontSize(saved);
  document.querySelectorAll<HTMLButtonElement>(".font-controls button").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.size) applyFontSize(btn.dataset.size);
    });
  });
}

function readingSection(title: string, payload?: ReadingPayload): string {
  if (!payload) return "";
  const heading = payload.heading
    ? `<div class="italic text-ink-2 text-[1rem] mb-3 leading-snug">${payload.heading}</div>`
    : "";
  const source = payload.source
    ? `<div class="text-accent font-semibold text-[0.92rem] mb-2.5">${payload.source}</div>`
    : "";
  return `
    <section class="universalis-html bg-surface border border-rule rounded-xl p-4 sm:p-5 mb-3.5">
      <h2 class="text-[0.7rem] uppercase tracking-[0.12em] text-ink-3 m-0 mb-1.5 font-bold">${title}</h2>
      ${source}
      ${heading}
      <div class="reading-text leading-[1.7] text-ink" style="font-size: var(--reading-fs, 1.05rem);">
        ${payload.text || ""}
      </div>
    </section>`;
}

function showError(humanUrl: string, msg: string) {
  const main = document.getElementById("main");
  if (main) {
    main.innerHTML = `
      <div class="text-center py-8 text-ink-3 text-[0.95rem]">
        ${msg} <a href="${humanUrl}" class="text-accent">Open at Universalis →</a>
      </div>`;
  }
}

function render(d: UniversalisData, humanUrl: string) {
  const dateLine = document.getElementById("dateLine");
  if (dateLine) dateLine.textContent = d.date || "";
  const dayLine = document.getElementById("dayLine");
  if (dayLine) dayLine.innerHTML = d.day || "";

  const html = [
    readingSection("First Reading", d.Mass_R1),
    readingSection("Responsorial Psalm", d.Mass_Ps),
    readingSection("Second Reading", d.Mass_R2),
    readingSection("Gospel Acclamation", d.Mass_GA),
    readingSection("Gospel", d.Mass_G),
  ].join("");

  const main = document.getElementById("main");
  if (main) main.innerHTML = html;

  const attribution = document.getElementById("attribution");
  if (attribution) {
    const copy = (d.copyright && d.copyright.text) || "";
    attribution.innerHTML = `
      <a class="inline-block my-1.5 text-[0.92rem] font-semibold text-accent no-underline" href="${humanUrl}" target="_blank" rel="noopener">Read at Universalis →</a>
      <div class="universalis-html">${copy}</div>`;
  }
}

function init() {
  initFontSize();
  const date = pickDate();
  const url = `https://universalis.com/Europe.England.Northampton/${date.compact}/jsonpmass.js`;
  const humanUrl = `https://universalis.com/Europe.England.Northampton/${date.compact}/mass.htm`;

  window.universalisCallback = (d: UniversalisData) => {
    try { render(d, humanUrl); }
    catch { showError(humanUrl, "Couldn't display the readings."); }
  };

  const tag = document.createElement("script");
  tag.src = url;
  tag.onerror = () => showError(humanUrl, "Couldn't reach Universalis.");
  document.head.appendChild(tag);

  setTimeout(() => {
    if (document.getElementById("loadingMsg")) showError(humanUrl, "Universalis is taking a while.");
  }, 12000);
}

init();
