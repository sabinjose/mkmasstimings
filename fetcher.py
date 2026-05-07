"""Fetching helpers: HTML→text, PDF→text, latest-newsletter discovery."""

from __future__ import annotations

import io
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import pdfplumber
import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

HEADERS = {"User-Agent": USER_AGENT}
TIMEOUT = 30


def http_get(url: str) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    return r


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    # collapse runs of blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def pdf_to_text(pdf_bytes: bytes) -> str:
    """Extract text preserving column layout — important for parishes whose
    bulletins use a multi-column schedule (one column per church)."""
    chunks: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            try:
                chunks.append(page.extract_text(layout=True) or "")
            except Exception:
                chunks.append(page.extract_text() or "")
    return "\n".join(chunks)


def fetch_pdf_text(url: str) -> str:
    return pdf_to_text(http_get(url).content)


def fetch_page_text(url: str) -> str:
    return html_to_text(http_get(url).text)


# ---------------------------------------------------------------------------
# Latest-newsletter discovery
# ---------------------------------------------------------------------------

DATE_IN_URL = re.compile(r"(20\d{2})[.\-_/](\d{1,2})[.\-_/](\d{1,2})")
DATE_IN_FILENAME = re.compile(r"(\d{1,2})[.\-_](\d{1,2})[.\-_](\d{2,4})")


def _score_pdf_link(href: str, text: str) -> tuple[datetime, str] | None:
    """Try to extract a date from a PDF link; return (date, href) or None.

    Order matters because URL paths often encode the *upload* month, not
    the bulletin date. We try the English form ("3rd May 2026", month
    name spelt out) first because a month name in a filename is a strong
    signal that the filename itself encodes the bulletin date — for
    example St Joseph's Bedford uploads `…/2026/04/03-May-2026.pdf` for
    the May 3 newsletter; matching `2026/04/03` from the path would
    misdate it as April 3. The numeric URL/filename patterns are tried
    only when no month name is present.
    """
    for cand in (href, text):
        if not cand:
            continue
        normalized = cand.replace("-", " ").replace("_", " ").replace("/", " ")
        d = _parse_english_date(normalized)
        if d:
            return d, href
        m = DATE_IN_URL.search(cand)
        if m:
            y, mo, d = (int(x) for x in m.groups())
            try:
                return datetime(y, mo, d), href
            except ValueError:
                pass
        m = DATE_IN_FILENAME.search(cand)
        if m:
            d, mo, y = (int(x) for x in m.groups())
            if y < 100:
                y += 2000
            try:
                return datetime(y, mo, d), href
            except ValueError:
                pass
    return None


def find_latest_pdf_links(page_url: str) -> list[str]:
    """Return PDF URLs in best-first (most-recent-date-first) order."""
    r = http_get(page_url)
    soup = BeautifulSoup(r.text, "lxml")
    scored: list[tuple[datetime, str]] = []
    unscored: list[str] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"])
        if not href.lower().endswith(".pdf"):
            continue
        s = _score_pdf_link(href, a.get_text(" ", strip=True))
        if s:
            scored.append(s)
        else:
            unscored.append(href)
    scored.sort(key=lambda x: x[0], reverse=True)
    ordered: list[str] = []
    seen: set[str] = set()
    for _, href in scored:
        if href not in seen:
            ordered.append(href)
            seen.add(href)
    for href in unscored:
        if href not in seen:
            ordered.append(href)
            seen.add(href)
    return ordered


def find_latest_pdf_link(page_url: str) -> str | None:
    links = find_latest_pdf_links(page_url)
    return links[0] if links else None


def find_latest_blog_post_pdf(blog_url: str) -> list[str]:
    """For sites where each blog entry links to a PDF: find the most recent
    post via its "Read More" link, then return PDF URLs from that post in
    best-first order (most recent year/month folder first)."""
    r = http_get(blog_url)
    soup = BeautifulSoup(r.text, "lxml")
    # First "Read More" link wins (blog is reverse-chronological)
    post_url: str | None = None
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True).lower()
        if "read more" in text:
            post_url = urljoin(blog_url, a["href"])
            break
    if not post_url:
        return find_latest_pdf_links(blog_url)
    # Fetch the post and pick PDFs ordered by year/month in the URL
    return find_latest_pdf_links(post_url)


_DATE_HEAD = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|"
    r"September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r"\s+(20\d{2})",
    re.IGNORECASE,
)


def _parse_english_date(s: str) -> datetime | None:
    m = _DATE_HEAD.search(s)
    if not m:
        return None
    d, mo_name, y = m.group(1), m.group(2), m.group(3)
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(f"{int(d)} {mo_name} {y}", fmt)
        except ValueError:
            continue
    return None


def _drive_export(href: str) -> str:
    m = re.search(r"/file/d/([^/]+)/", href)
    return f"https://drive.google.com/uc?export=download&id={m.group(1)}" if m else href


def find_latest_drive_pdf(page_url: str) -> list[str]:
    """Return Drive PDF candidate URLs in best-first order.

    Priority:
      1. Any <iframe> embedding a Drive file (parishes typically embed the
         *current* newsletter).
      2. Anchors paired with the most recent date heading.
      3. The first Drive anchor as a fallback.

    Returns a list so callers can try the next candidate if one is broken.
    """
    r = http_get(page_url)
    soup = BeautifulSoup(r.text, "lxml")

    # Priority 1: iframes embedding a Drive file.
    iframe_links: list[str] = []
    for f in soup.find_all("iframe"):
        src = f.get("src") or ""
        if "drive.google.com/file/d/" in src:
            iframe_links.append(src)

    # Walk the rendered text + links in order.
    # Strategy: iterate over all descendants, accumulate the most recent date
    # we've seen, and when we hit a Drive anchor, pair it with that date.
    scored: list[tuple[datetime, str]] = []
    seen_links: list[str] = []
    pending_date: datetime | None = None

    for el in soup.body.descendants if soup.body else []:
        name = getattr(el, "name", None)
        if name is None:
            # NavigableString — check for date
            t = str(el).strip()
            if t:
                d = _parse_english_date(t)
                if d:
                    pending_date = d
            continue
        if name == "a" and el.get("href") and "drive.google.com/file/d/" in el["href"]:
            href = el["href"]
            seen_links.append(href)
            # also peek inside the link text for a date
            d = _parse_english_date(el.get_text(" ", strip=True)) or pending_date
            if d:
                scored.append((d, href))

    scored.sort(key=lambda x: x[0], reverse=True)
    ordered: list[str] = []
    seen: set[str] = set()
    # iframes win
    for href in iframe_links:
        if href not in seen:
            ordered.append(href)
            seen.add(href)
    for _, href in scored:
        if href not in seen:
            ordered.append(href)
            seen.add(href)
    for href in seen_links:
        if href not in seen:
            ordered.append(href)
            seen.add(href)
    return [_drive_export(h) for h in ordered]


def find_google_doc_export_url(page_url: str) -> str | None:
    """Find a Google Docs link on a page and return its HTML export URL.

    HTML preserves table structure (<tr>/<td>) which is essential for
    multi-column timetables — plain-text export interleaves cells.
    """
    r = http_get(page_url)
    soup = BeautifulSoup(r.text, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.search(r"docs\.google\.com/document/d/([a-zA-Z0-9_\-]+)", href)
        if m:
            return f"https://docs.google.com/document/d/{m.group(1)}/export?format=html"
    # iframe fallback
    for f in soup.find_all("iframe"):
        src = f.get("src") or ""
        m = re.search(r"docs\.google\.com/document/d/([a-zA-Z0-9_\-]+)", src)
        if m:
            return f"https://docs.google.com/document/d/{m.group(1)}/export?format=html"
    return None


def fetch_gdoc_text(url: str) -> str:
    """Fetch a Google Docs HTML-export URL and return cleaned body HTML.

    The HTML structure (<table>/<tr>/<td>) disambiguates multi-column
    timetables that the plain-text export interleaves. We strip Google's
    cosmetic noise — class/style/id attributes, default colspan/rowspan,
    and <span>/<p> wrappers around plain text — to keep the payload
    LLM-friendly without losing semantic structure.
    """
    r = http_get(url)
    html = r.content.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")
    # Strip cosmetic attributes everywhere.
    for tag in soup.find_all(True):
        for attr in ("class", "style", "id"):
            tag.attrs.pop(attr, None)
        # colspan/rowspan="1" are defaults — drop them.
        for attr in ("colspan", "rowspan"):
            if tag.attrs.get(attr) == "1":
                tag.attrs.pop(attr, None)
    # Unwrap span / p — they only add bulk; whitespace already separates text.
    for tag in soup.find_all(["span"]):
        tag.unwrap()
    for tag in soup.find_all("p"):
        tag.insert_after("\n")
        tag.unwrap()
    body = soup.body or soup
    out = str(body)
    # Collapse runs of whitespace inside tags (Google emits long blank padding).
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out


def find_latest_mailchimp_campaign(archive_url: str) -> str | None:
    """Mailchimp's campaign-archive page lists campaign URLs in the first <a>."""
    r = http_get(archive_url)
    soup = BeautifulSoup(r.text, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # campaign URLs look like https://mailchi.mp/... or .../e/<id>
        host = urlparse(href).netloc
        if host.endswith("mailchi.mp") or "/campaign-archive" in href and "id=" in href:
            if "mailchi.mp" in href:
                return href
    # fallback: any link in the campaigns table
    for a in soup.select("li.campaign a[href]"):
        return a["href"]
    return None
