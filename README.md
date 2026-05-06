# mkmasstimings

Aggregates Catholic mass times from parish newsletters across Milton Keynes
and the surrounding area into one weekly JSON.

For each parish, the pipeline:

1. Fetches the latest newsletter (PDF, web page, Google Doc, Drive iframe, or
   Mailchimp campaign — handled by per-parish strategies in `parishes.py`).
2. Sends the text to an LLM (vendor-agnostic via LiteLLM; default
   `openai/gpt-4o-mini`) to extract a structured schedule of every Mass,
   Vigil, Confession, Adoration, Rosary etc.
3. Writes a single unified JSON.

## Quick start

```bash
cp .env.example .env       # add your OPENAI_API_KEY (or ANTHROPIC / GEMINI)
uv run main.py --pretty    # full sweep, JSON to stdout
uv run main.py --only "Augustine" -v
uv run probe.py            # cheap update-detection (no LLM calls)
```

## Files

- `parishes.py` — registry of parishes + their newsletter strategy
- `fetcher.py` — HTML / PDF / Google Doc / Drive iframe / Mailchimp helpers
- `extractor.py` — LLM call → structured JSON
- `main.py` — CLI: loops parishes, emits unified JSON
- `probe.py` — records `Last-Modified` + content hash per parish to
  `data/update_log.csv` so we can learn each parish's publishing cadence
