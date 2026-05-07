"""CLI: fetch + extract mass times for every configured parish.

Usage:
    uv run main.py                          # all parishes, JSON to stdout
    uv run main.py --only "St Augustine"
    uv run main.py --pretty                 # pretty-print
    uv run main.py --pretty --out data/latest.json
        # in-place atomic update: reuse parishes whose source URL hasn't
        # changed and merge old future-dated services with new extractions.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv

import fetcher
from extractor import extract_mass_times
from parishes import PARISHES, Parish, find_church

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


def discover_source(parish: Parish) -> str | None:
    """Return the latest source URL for `parish` without downloading content.

    Used to decide whether the parish bulletin has changed since the last
    successful extraction. Cheap (HTML parse / HEAD request only) — never
    fetches the PDF/Doc body. Returns None when discovery fails.
    """
    s = parish.strategy
    try:
        if s == "page":
            return parish.source_url
        if s == "pdf_archive":
            urls = fetcher.find_latest_pdf_links(parish.source_url)
            return urls[0] if urls else None
        if s == "drive":
            urls = fetcher.find_latest_drive_pdf(parish.source_url)
            return urls[0] if urls else None
        if s == "blog_pdf":
            urls = fetcher.find_latest_blog_post_pdf(parish.source_url)
            return urls[0] if urls else None
        if s == "gdoc":
            return fetcher.find_google_doc_export_url(parish.source_url)
        if s == "mailchimp":
            return fetcher.find_latest_mailchimp_campaign(parish.source_url)
    except Exception:
        return None
    return None


def discover_fallback_source(parish: Parish) -> str | None:
    """Return the SECOND-most-recent source URL for strategies that list
    historical bulletins (pdf_archive, drive, blog_pdf).

    Used to bridge today/tomorrow when the latest bulletin's coverage
    starts after today (e.g., parish publishes next week's bulletin a
    few days early). Returns None when no previous bulletin is listed
    or the strategy doesn't support history.
    """
    s = parish.strategy
    try:
        if s == "pdf_archive":
            urls = fetcher.find_latest_pdf_links(parish.source_url)
        elif s == "drive":
            urls = fetcher.find_latest_drive_pdf(parish.source_url)
        elif s == "blog_pdf":
            urls = fetcher.find_latest_blog_post_pdf(parish.source_url)
        else:
            return None
        return urls[1] if len(urls) > 1 else None
    except Exception:
        return None


def coverage_starts_after_today(services: list[dict], today_str: str) -> bool:
    """True when every dated service in `services` is strictly after today.

    Signals that a parish has published their next bulletin early and the
    current extraction doesn't cover today/tomorrow — triggering a
    fallback fetch of the previous bulletin to bridge the gap.
    """
    dates = [s.get("date") or "" for s in services if s.get("date")]
    if not dates:
        return False
    return min(dates) > today_str


def parish_key(p: Parish | dict) -> str:
    """Stable key for matching old/new parish entries.

    `location` is set from config (we override the LLM's value in process)
    and is unique across PARISHES, so it round-trips cleanly between runs
    even when the model rewrites the parish name.
    """
    if isinstance(p, Parish):
        return p.location
    return p.get("location", "") or ""


def load_old(path: str) -> dict[str, dict]:
    """Load old latest.json into {parish_key: parish_dict}. Empty on miss."""
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    return {parish_key(p): p for p in data.get("parishes", [])}


def can_reuse(old_parish: dict | None, discovered_url: str | None, today_str: str) -> bool:
    """Decide whether to skip fetch+extract and reuse the old parish entry.

    Skip only when the discovered source URL matches what we extracted
    last time AND the old extraction still has at least one service
    today-or-later AND there was no error. Anything else means the
    bulletin has rolled over, the previous run failed, or we'd risk
    losing future-dated services — fall back to a fresh extraction.
    """
    if not old_parish:
        return False
    if old_parish.get("error"):
        return False
    services = old_parish.get("services") or []
    if not services:
        return False
    if not any((s.get("date") or "") >= today_str for s in services):
        return False
    if not discovered_url:
        return False
    if old_parish.get("source_url") != discovered_url:
        return False
    return True


def merge_services(
    old: list[dict], new: list[dict], today_str: str
) -> list[dict]:
    """Combine old + new services, drop past, dedupe with new winning.

    Past services are dropped (date < today). For each (date, time, type,
    church) tuple the new extraction wins. Old services that aren't
    contradicted by new are preserved — covers the case where a parish
    publishes next week's bulletin early and the new file no longer lists
    today/tomorrow's services.
    """
    seen: dict[tuple, dict] = {}
    for s in old:
        if (s.get("date") or "") < today_str:
            continue
        key = (s.get("date"), s.get("time"), s.get("type"), s.get("church"))
        seen[key] = s
    for s in new:
        key = (s.get("date"), s.get("time"), s.get("type"), s.get("church"))
        seen[key] = s
    return sorted(
        seen.values(),
        key=lambda x: ((x.get("date") or ""), (x.get("time") or "")),
    )


def _extract_url(parish: Parish, url: str, verbose: bool) -> dict[str, Any]:
    """Fetch + extract a specific source URL for the parish. Returns a
    services-shaped dict (with `error` set on failure)."""
    try:
        if parish.strategy in ("pdf_archive", "drive", "blog_pdf"):
            text = fetcher.fetch_pdf_text(url)
        elif parish.strategy == "gdoc":
            text = fetcher.fetch_gdoc_text(url)
        elif parish.strategy in ("page", "mailchimp"):
            text = fetcher.fetch_page_text(url)
        else:
            text = ""
    except Exception as e:
        return {"services": [], "error": f"fallback fetch failed: {e}"}
    if not text.strip():
        return {"services": [], "error": "fallback no content"}
    try:
        return extract_mass_times(parish.name, text, hints=parish.hints)
    except Exception as e:
        if verbose:
            traceback.print_exc(file=sys.stderr)
        return {"services": [], "error": f"fallback extract failed: {e}"}


def process(
    parish: Parish,
    old_parish: dict | None,
    today_str: str,
    verbose: bool = False,
) -> dict[str, Any]:
    discovered = discover_source(parish)
    if can_reuse(old_parish, discovered, today_str):
        if verbose:
            print(
                f"  reusing {parish.name} (source unchanged: {discovered})",
                file=sys.stderr,
            )
        # Ensure outside_mk is current with parishes.py — old JSONs from
        # before this field existed wouldn't carry it through the reuse path.
        old_parish["outside_mk"] = parish.outside_mk  # type: ignore[index]
        enrich_with_church_meta(old_parish, parish)
        return old_parish  # type: ignore[return-value]

    if verbose:
        print(f"  fetching {parish.name}...", file=sys.stderr)
    try:
        text, source = gather_text(parish)
    except Exception as e:
        new_data: dict[str, Any] = {
            "parish": parish.name,
            "location": parish.location,
            "source_url": parish.source_url,
            "error": f"fetch failed: {e}",
            "services": [],
        }
    else:
        if not text.strip():
            new_data = {
                "parish": parish.name,
                "location": parish.location,
                "source_url": parish.source_url,
                "error": "no content found",
                "services": [],
            }
        else:
            if verbose:
                print(
                    f"  extracting {parish.name} ({len(text)} chars from {source})",
                    file=sys.stderr,
                )
            try:
                new_data = extract_mass_times(parish.name, text, hints=parish.hints)
            except Exception as e:
                if verbose:
                    traceback.print_exc(file=sys.stderr)
                new_data = {
                    "parish": parish.name,
                    "location": parish.location,
                    "source_url": parish.source_url,
                    "error": f"extract failed: {e}",
                    "services": [],
                }
            else:
                new_data["location"] = parish.location
                new_data["source_url"] = source

    # Bridge: if the latest bulletin's coverage starts strictly after today
    # (parish published next week's bulletin early), fetch the previous
    # bulletin too so today/tomorrow services aren't missing on first
    # contact — even when there's no useful old_parish to merge from.
    services_now = new_data.get("services") or []
    if services_now and coverage_starts_after_today(services_now, today_str):
        fallback_url = discover_fallback_source(parish)
        if fallback_url:
            if verbose:
                print(
                    f"  bridging {parish.name} (latest covers future only) "
                    f"with previous bulletin: {fallback_url}",
                    file=sys.stderr,
                )
            fb = _extract_url(parish, fallback_url, verbose=verbose)
            if fb.get("services"):
                new_data["services"] = merge_services(
                    fb["services"], services_now, today_str
                )

    # Merge with old future-dated services so a failed/early-rolled bulletin
    # doesn't drop today/tomorrow data we already have.
    if old_parish and old_parish.get("services"):
        merged = merge_services(
            old_parish["services"],
            new_data.get("services") or [],
            today_str,
        )
        if merged and new_data.get("services") != merged:
            new_data["services"] = merged
            # If the only services we have came from old data and the new
            # attempt errored, drop the error — the data is stale-but-real,
            # and surfacing it as an error confuses the frontend.
            if new_data.get("error") and merged:
                new_data.pop("error", None)

    # Surface outside_mk so the frontend can hide faraway parishes by default
    # and only include them when their Masses fill a time-bucket gap.
    new_data["outside_mk"] = parish.outside_mk
    enrich_with_church_meta(new_data, parish)
    return new_data


def enrich_with_church_meta(parish_data: dict, parish: Parish) -> None:
    """Attach `area` and `postcode` to every service entry in-place.

    Looks up each service against the CHURCHES registry using its `church`
    name + `church_location`. For single-church parishes the LLM often
    leaves both blank, so we fall back to matching by `parish.location`
    (which can be a multi-area string like "Wolverton / Stony Stratford"
    — in that case only one church will match cleanly and we leave the
    others alone).
    """
    for svc in parish_data.get("services") or []:
        name = svc.get("church")
        area = svc.get("church_location")
        ch = find_church(name, area)
        if ch is None and not name and not area:
            # Single-church parish — try the parish's location verbatim.
            ch = find_church(None, parish.location)
        if ch is None:
            # Multi-area parish_location like "Buckingham / Brackley":
            # try each part.
            for part in (parish.location or "").split("/"):
                ch = find_church(None, part.strip())
                if ch:
                    break
        if ch is not None:
            svc["area"] = ch.area
            svc["postcode"] = ch.postcode
            # Only fill in the church name when the LLM didn't already
            # set one — don't overwrite specific names like "St Bernardine's".
            if not svc.get("church"):
                svc["church"] = ch.name
            if not svc.get("church_location"):
                svc["church_location"] = ch.area


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch mass times for MK-area parishes.")
    ap.add_argument("--only", help="case-insensitive substring match on parish name")
    ap.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    ap.add_argument("--verbose", "-v", action="store_true", help="log to stderr")
    ap.add_argument(
        "--out",
        help=(
            "Read old data from this path (for reuse/merge), then write the "
            "result back atomically. Without this flag, output goes to stdout "
            "and no merging is performed."
        ),
    )
    args = ap.parse_args()

    targets: list[Parish] = list(PARISHES)
    if args.only:
        needle = args.only.lower()
        targets = [
            p for p in PARISHES
            if needle in p.name.lower() or needle in p.location.lower()
        ]
        if not targets:
            print(f"no parish matched '{args.only}'", file=sys.stderr)
            return 1

    today_str = datetime.now(timezone.utc).date().isoformat()
    old_lookup = load_old(args.out) if args.out else {}

    new_parishes: list[dict] = []
    for p in targets:
        old_parish = old_lookup.get(parish_key(p))
        new_parishes.append(
            process(p, old_parish, today_str, verbose=args.verbose)
        )

    # If filtering with --only and writing back to --out, preserve every
    # other parish's old entry untouched — otherwise --only + --out would
    # silently drop them.
    if args.only and args.out:
        kept = {parish_key(p) for p in targets}
        for key, old_p in old_lookup.items():
            if key not in kept:
                new_parishes.append(old_p)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parishes": new_parishes,
    }

    indent = 2 if args.pretty else None
    if args.out:
        tmp = args.out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=indent, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, args.out)
    else:
        json.dump(out, sys.stdout, indent=indent, ensure_ascii=False)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
