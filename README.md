# mkmasstimings

Aggregates Catholic Mass times from ~17 parish newsletters across Milton
Keynes and surrounding area into one weekly JSON and renders a "today /
tomorrow" page at <https://mkmasstimings.pages.dev>.

For each parish, the pipeline:

1. **Discover** the latest newsletter URL via a per-parish strategy in
   `parishes.py` (PDF archive, Google Doc, Drive download, Mailchimp
   campaign, blog post, or static HTML page).
2. **Skip if unchanged** — if the discovered URL is the same one we
   extracted from last time and the previous JSON still covers today,
   reuse it as-is. Saves the LLM call entirely on most runs.
3. **Fetch + extract** with an LLM (vendor-agnostic via LiteLLM; default
   `openai/gpt-4o-mini`) to produce a structured list of services.
4. **Bridge early-published bulletins** — if the latest bulletin's
   coverage starts strictly after today (a parish published next week's
   bulletin a few days early), automatically fetch the previous one too
   and merge so today/tomorrow services aren't missing.
5. **Resolve church metadata** — every service is enriched with `area`
   and `postcode` from the `CHURCHES` registry in `parishes.py`.
6. **Merge with previous JSON** — keep any future-dated services from
   the old data that the new extraction didn't supersede.
7. **Atomic write** of `data/latest.json`.

## Quick start

```bash
cp .env.example .env       # OPENAI_API_KEY (or ANTHROPIC / GEMINI)
uv run main.py --pretty    # full sweep, JSON to stdout
uv run main.py --only "Augustine" -v

# In-place update with skip-if-unchanged + merge:
uv run main.py --pretty --out data/latest.json

uv run probe.py            # cheap update-detection (no LLM calls)
python3 -m http.server 8000  # serve the frontend locally
```

`?date=YYYY-MM-DD` is a preview helper that pretends today is the given
date — handy when QA-ing the toggle / fallback / bridge logic.

## Files

- `parishes.py` — registry of parishes (each with strategy, location,
  optional hints) plus the master `CHURCHES` list mapping every church
  to its area and postcode.
- `fetcher.py` — HTML / PDF (column-preserving) / Google Doc HTML
  export / Drive iframe / Mailchimp helpers.
- `extractor.py` — LLM call → structured JSON.
- `main.py` — CLI with `--out PATH` for atomic in-place updates that
  reuse, merge, and bridge automatically.
- `probe.py` — records `Last-Modified` + content hash per parish to
  `data/update_log.csv` for cadence analysis.
- `index.html` — single-page frontend (vanilla JS, no build step).
- `data/latest.json` — current week's extracted services, committed by
  the cron workflow.
- `.github/workflows/refresh.yml` — Fri/Sat/Sun 04:00 UTC cron that runs
  the pipeline and pushes to Cloudflare Pages via wrangler-action.

## Frontend

The page renders `data/latest.json` as a `TIME · TOWN · CHURCH NAME,
POSTCODE` schedule with three sections (Holy Mass, Confession,
Adoration). It includes:

- **Today / Tomorrow** day toggle.
- **+ Nearby** toggle (default off): MK parishes always show; outside-MK
  parishes only surface when one of their Masses fills a time-of-day
  bucket (morning / afternoon / evening) that no MK Mass covers. Toggle
  on to include every nearby parish wholesale; the choice persists in
  localStorage.
- **Share / Copy / Save image** — the last lazy-loads `html2canvas`
  and renders the full schedule as a PNG suitable for WhatsApp.

## Deployment

GitHub Actions runs the refresh cron and deploys the resulting
`index.html` + `data/latest.json` to Cloudflare Pages via
`cloudflare/wrangler-action`. The repo's Pages project is set up as
Direct Upload so deploys happen entirely from CI — no GitHub-side
integration to break. Required repo secrets:

- `OPENAI_API_KEY` (or whichever LiteLLM provider)
- `CLOUDFLARE_API_TOKEN` (Account → Cloudflare Pages → Edit)
- `CLOUDFLARE_ACCOUNT_ID`
