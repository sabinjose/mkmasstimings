"""Probe each parish source to detect when its newsletter changes.

Cheap (no LLM calls): for each parish, find the latest newsletter URL using
the same logic as `main.py`, fetch the bytes, and record:

  - timestamp (when we probed)
  - parish name + location
  - resolved URL (the actual newsletter file we'd hand to the LLM)
  - HTTP `Last-Modified` header (if the server provides one)
  - byte size
  - sha256 of the content

Each run appends one row per parish to `data/update_log.csv`. Compare runs to
see when each parish replaces or rewrites its newsletter — that tells us the
optimal cron schedule for the full LLM-extraction job.
"""

from __future__ import annotations

import csv
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import fetcher
from parishes import PARISHES, Parish

LOG_PATH = Path(__file__).parent / "data" / "update_log.csv"

CSV_FIELDS = [
    "probed_at",
    "parish",
    "location",
    "resolved_url",
    "last_modified",
    "size_bytes",
    "sha256",
    "error",
]


def resolve_source(parish: Parish) -> str | None:
    """Return the URL we'd actually fetch for content (PDF, gdoc, page)."""
    s = parish.strategy
    try:
        if s == "page":
            return parish.source_url
        if s == "pdf_archive":
            links = fetcher.find_latest_pdf_links(parish.source_url)
            return links[0] if links else None
        if s == "drive":
            links = fetcher.find_latest_drive_pdf(parish.source_url)
            return links[0] if links else parish.source_url
        if s == "blog_pdf":
            links = fetcher.find_latest_blog_post_pdf(parish.source_url)
            return links[0] if links else parish.source_url
        if s == "gdoc":
            return fetcher.find_google_doc_export_url(parish.source_url) or parish.source_url
        if s == "mailchimp":
            return fetcher.find_latest_mailchimp_campaign(parish.source_url) or parish.source_url
    except Exception as e:
        print(f"  resolve failed for {parish.name}: {e}", file=sys.stderr)
        return None
    return None


def probe_one(parish: Parish) -> dict[str, str]:
    row = {f: "" for f in CSV_FIELDS}
    row["probed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    row["parish"] = parish.name
    row["location"] = parish.location

    url = resolve_source(parish)
    if not url:
        row["error"] = "could not resolve source URL"
        return row
    row["resolved_url"] = url

    try:
        r = fetcher.http_get(url)
    except Exception as e:
        row["error"] = f"fetch failed: {e}"
        return row

    row["last_modified"] = r.headers.get("Last-Modified", "")
    row["size_bytes"] = str(len(r.content))
    row["sha256"] = hashlib.sha256(r.content).hexdigest()
    return row


def main() -> int:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    new_file = not LOG_PATH.exists()

    rows = []
    for parish in PARISHES:
        print(f"probing {parish.name} ({parish.location})...", file=sys.stderr)
        rows.append(probe_one(parish))

    with LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)

    print(f"\nlogged {len(rows)} rows to {LOG_PATH}", file=sys.stderr)

    # Print a one-line-per-parish summary to stdout
    print(f"\n{'Parish':<48} {'Location':<28} {'Last-Modified':<32} {'Size':>8}  Hash")
    print("-" * 130)
    for r in rows:
        name = r["parish"][:47]
        loc = r["location"][:27]
        lm = (r["last_modified"] or "—")[:31]
        size = r["size_bytes"] or "—"
        h = (r["sha256"] or r["error"] or "—")[:16]
        print(f"{name:<48} {loc:<28} {lm:<32} {size:>8}  {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
