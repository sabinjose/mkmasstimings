"""CLI: fetch + extract mass times for every configured parish.

Usage:
    uv run main.py                # all parishes, JSON to stdout
    uv run main.py --only "St Augustine"
    uv run main.py --pretty       # pretty-print
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

import fetcher
from extractor import extract_mass_times
from parishes import PARISHES, Parish

load_dotenv()


def gather_text(parish: Parish) -> tuple[str, str | None]:
    """Return (text, source_url_used). Raises on fatal fetch errors."""
    s = parish.strategy
    if s == "page":
        return fetcher.fetch_page_text(parish.source_url), parish.source_url

    if s == "pdf_archive":
        for pdf in fetcher.find_latest_pdf_links(parish.source_url):
            try:
                return fetcher.fetch_pdf_text(pdf), pdf
            except Exception:
                continue
        return "", None

    if s == "drive":
        for drive in fetcher.find_latest_drive_pdf(parish.source_url):
            try:
                return fetcher.fetch_pdf_text(drive), drive
            except Exception:
                continue
        return fetcher.fetch_page_text(parish.source_url), parish.source_url

    if s == "blog_pdf":
        for pdf in fetcher.find_latest_blog_post_pdf(parish.source_url):
            try:
                return fetcher.fetch_pdf_text(pdf), pdf
            except Exception:
                continue
        return fetcher.fetch_page_text(parish.source_url), parish.source_url

    if s == "gdoc":
        gdoc = fetcher.find_google_doc_export_url(parish.source_url)
        if gdoc:
            try:
                return fetcher.fetch_gdoc_text(gdoc), gdoc
            except Exception:
                pass
        return fetcher.fetch_page_text(parish.source_url), parish.source_url

    if s == "mailchimp":
        campaign = fetcher.find_latest_mailchimp_campaign(parish.source_url)
        if campaign:
            return fetcher.fetch_page_text(campaign), campaign
        return fetcher.fetch_page_text(parish.source_url), parish.source_url

    raise ValueError(f"Unknown strategy: {s}")


def process(parish: Parish, verbose: bool = False) -> dict[str, Any]:
    if verbose:
        print(f"  fetching {parish.name}...", file=sys.stderr)
    try:
        text, source = gather_text(parish)
    except Exception as e:
        return {
            "parish": parish.name,
            "location": parish.location,
            "source_url": parish.source_url,
            "error": f"fetch failed: {e}",
            "services": [],
        }
    if not text.strip():
        return {
            "parish": parish.name,
            "location": parish.location,
            "source_url": parish.source_url,
            "error": "no content found",
            "services": [],
        }
    if verbose:
        print(
            f"  extracting {parish.name} ({len(text)} chars from {source})",
            file=sys.stderr,
        )
    try:
        data = extract_mass_times(parish.name, text, hints=parish.hints)
    except Exception as e:
        if verbose:
            traceback.print_exc(file=sys.stderr)
        return {
            "parish": parish.name,
            "location": parish.location,
            "source_url": parish.source_url,
            "error": f"extract failed: {e}",
            "services": [],
        }
    data["location"] = parish.location
    data["source_url"] = source
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch mass times for MK-area parishes.")
    ap.add_argument("--only", help="case-insensitive substring match on parish name")
    ap.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    ap.add_argument("--verbose", "-v", action="store_true", help="log to stderr")
    args = ap.parse_args()

    targets = PARISHES
    if args.only:
        needle = args.only.lower()
        targets = [
            p for p in PARISHES
            if needle in p.name.lower() or needle in p.location.lower()
        ]
        if not targets:
            print(f"no parish matched '{args.only}'", file=sys.stderr)
            return 1

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parishes": [process(p, verbose=args.verbose) for p in targets],
    }

    indent = 2 if args.pretty else None
    json.dump(out, sys.stdout, indent=indent, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
