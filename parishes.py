"""Parish source registry.

Each parish describes:
  - name: human-readable parish name
  - source_url: where we start fetching
  - strategy: how to find the actual newsletter content
      - "page"        : mass times sit directly on the source_url HTML page
      - "pdf_archive" : source_url lists PDF links; pick the most recent
      - "drive"       : source_url has a Google Drive file link to a PDF
      - "blog_pdf"    : blog/archive listing where each entry links to a PDF
      - "gdoc"        : source_url has a link to a Google Doc newsletter
      - "mailchimp"   : Mailchimp campaign archive listing email campaigns

The CHURCHES registry below is a flat list of every individual church we
know about (typically the building, not the canonical parish). Multi-church
parishes such as the Barnabas Cluster (Mailchimp digest) cover several
churches; main.py looks each service up here to attach an `area` and
`postcode` for display.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Church:
    name: str       # display name e.g. "St. Augustine"
    area: str       # neighbourhood / town shown to the user
    postcode: str


# Master list. Order doesn't matter; lookups are by (name, area).
CHURCHES: list[Church] = [
    # Barnabas Cluster (covered by the Mailchimp digest)
    Church(name="Christ the Cornerstone",     area="Central MK",          postcode="MK9 2ES"),
    Church(name="Our Lady of Lourdes",        area="Coffee Hall",         postcode="MK6 5NA"),
    Church(name="St. Edward the Confessor",   area="Shenley Church End",  postcode="MK5 6DX"),
    Church(name="Christ the King",            area="Kents Hill",          postcode="MK7 6HG"),
    Church(name="St. Bede",                   area="Newport Pagnell",     postcode="MK16 8EN"),
    Church(name="St. Mary's",                 area="Woburn Sands",        postcode="MK17 8NN"),
    # Standalone parishes around MK
    Church(name="St. Augustine",              area="Heelands",            postcode="MK13 7PL"),
    Church(name="All Saints",                 area="Bletchley",           postcode="MK3 6AN"),
    Church(name="St. Thomas Aquinas",         area="Bletchley",           postcode="MK2 2JE"),
    Church(name="St. Francis de Sales",       area="Wolverton",           postcode="MK12 5LJ"),
    Church(name="St. Mary Magdalene",         area="Stony Stratford",     postcode="MK11 1AT"),
    # Outside MK
    Church(name="Our Lady Help of Christians & St. Lawrence", area="Olney", postcode="MK46 5HH"),
    Church(name="St. Bernardine of Siena",    area="Buckingham",          postcode="MK18 1AL"),
    Church(name="St. Martin of Tours",        area="Brackley",            postcode="NN13 6AN"),
    Church(name="St. Joseph's",               area="Bedford",             postcode="MK40 1HU"),
    Church(name="Catholic Church of our Lady",area="Kempston",            postcode="MK42 8QB"),
    Church(name="St. Alban's Chapel",         area="Winslow",             postcode="MK18 3AB"),
    Church(name="Sacred Heart Catholic Church", area="Leighton Buzzard",  postcode="LU7 1HZ"),
    Church(name="Sacred Heart Catholic Church", area="Flitwick",          postcode="MK45 1JP"),
    Church(name="St. Mary's",                 area="Dunstable",           postcode="LU6 3SP"),
]


def _normalize(s: str) -> str:
    """Lowercase + strip punctuation so 'St. Augustine' matches 'St Augustine'."""
    return "".join(ch for ch in s.lower() if ch.isalnum() or ch.isspace()).strip()


def find_church(name: str | None, area: str | None) -> Church | None:
    """Best-effort lookup of a church by (name, area).

    Area is the more specific axis (postcodes are 1:1 with area, not name —
    we have multiple "Sacred Heart Catholic Church" entries). Name match
    is fuzzy: case + punctuation insensitive, partial allowed.
    """
    if not (name or area):
        return None
    n = _normalize(name) if name else ""
    a = _normalize(area) if area else ""
    # Apply parish-location-to-area alias when the area looks like a
    # parish-level label (e.g. St Augustine's lives in "Milton Keynes" the
    # parish, but the CHURCH is in "Heelands").
    if a and a in _PARISH_LOCATION_ALIASES:
        a = _PARISH_LOCATION_ALIASES[a]
    if a:
        in_area = [c for c in CHURCHES if _normalize(c.area) == a]
        if len(in_area) == 1:
            return in_area[0]
        if n:
            for c in in_area:
                cn = _normalize(c.name)
                if cn == n or n in cn or cn in n:
                    return c
    if n:
        candidates = [c for c in CHURCHES if _normalize(c.name) == n]
        if len(candidates) == 1:
            return candidates[0]
    return None


# parish.location strings that don't exactly match any Church.area entry.
# Keys/values are normalised (lowercase, punctuation stripped).
_PARISH_LOCATION_ALIASES: dict[str, str] = {
    "milton keynes": "heelands",         # St Augustine's
    "dunstable polish": "dunstable",     # Polska Parafia (location: "Dunstable (Polish)")
}


@dataclass(frozen=True)
class Parish:
    name: str
    source_url: str
    strategy: str
    location: str = ""
    # Optional ground-truth hint passed to the LLM. Use for multi-church parishes
    # where column layout in the PDF is too ambiguous to disambiguate from text alone.
    hints: str = ""
    # True when the parish is outside Milton Keynes / its immediate suburbs.
    # The frontend hides outside-MK services by default and exposes a toggle
    # at the top of the page to include them on demand.
    outside_mk: bool = False


PARISHES: list[Parish] = [
    Parish(
        name="St Augustine's",
        source_url="https://www.st-augustinesmk.org.uk/web/newsletter/",
        strategy="page",
        location="Milton Keynes",
    ),
    Parish(
        name="Catholic Bletchley (All Saints / St Thomas Aquinas)",
        source_url="https://catholic-bletchley.com/",
        strategy="pdf_archive",
        location="Bletchley",
    ),
    Parish(
        name="St Francis & St Mary Magdalene",
        source_url="https://www.stfrancisandmary.org/newsletter",
        strategy="drive",
        location="Wolverton / Stony Stratford",
        hints=(
            "This parish has two churches. The newsletter is a two-column "
            "timetable but plain-text column extraction is unreliable, so use "
            "the schedule below ONLY to set church/church_location.\n"
            "\n"
            "The newsletter remains authoritative for everything else: extract "
            "times, dates, service types, intentions/notes, and cancellations "
            "exactly as printed. Include cancellations (e.g. 'No Mass') as "
            "services with time=null. Include one-off / special services even "
            "if not in the schedule below — match them to whichever church "
            "they appear in.\n"
            "\n"
            "Regular church assignment (use to populate church/"
            "church_location only):\n"
            "- St Francis de Sales (Wolverton): Saturday evening Vigil Mass, "
            "Sunday late-morning Mass, Tuesday Mass, Thursday Mass.\n"
            "- St Mary Magdalene (Stony Stratford): Sunday morning Mass, "
            "Monday Mass, Wednesday Mass + Adoration, Friday Mass, Saturday "
            "morning Mass + Confessions."
        ),
    ),
    Parish(
        name="Our Lady of Lourdes",
        source_url="https://www.ourladysolney.co.uk/blog/",
        strategy="blog_pdf",
        location="Olney",
    ),
    Parish(
        name="St Mary's",
        source_url="https://www.stmarys-dunstable.org/home/newsletter",
        strategy="page",
        location="Dunstable",
        outside_mk=True,
    ),
    Parish(
        name="Sacred Heart",
        source_url="https://sacredheartflitwick.co.uk/newsletters/",
        strategy="pdf_archive",
        location="Flitwick",
    ),
    Parish(
        name="Sacred Heart",
        source_url="https://www.sacredheartlb.org.uk/service-times/",
        strategy="pdf_archive",
        location="Leighton Buzzard",
        outside_mk=True,
    ),
    Parish(
        name="Polska Parafia (Matki Bożej Częstochowskiej)",
        source_url="https://parafiadunstable.co.uk/informacje/biuletyn-parafialny",
        strategy="pdf_archive",
        location="Dunstable (Polish)",
        outside_mk=True,
    ),
    Parish(
        name="St Bernardine's & St Martin's",
        source_url="https://stbernardines.org/latest-parish-newsletter/",
        strategy="gdoc",
        location="Buckingham / Brackley",
        outside_mk=True,
        hints=(
            "This parish has two churches. The newsletter is rendered as a "
            "3-column HTML table: column 1 is the date, column 2 is "
            "St Bernardine's (Buckingham), column 3 is St Martin's (Brackley). "
            "Use each <td> cell's column position to set church/"
            "church_location for any services it contains."
        ),
    ),
    Parish(
        name="St Joseph's & Our Lady's",
        source_url="https://www.stjosephsbedford.org/category/church/",
        strategy="pdf_archive",
        location="Bedford / Kempston",
        outside_mk=True,
        hints=(
            "This parish has two churches and the weekly newsletter labels "
            "Mass times under two clearly named sections. Use the section "
            "heading each service appears under to set its church/"
            "church_location:\n"
            "- 'Mass Times – St Joseph's, Bedford' → church='St Joseph's', "
            "church_location='Bedford'.\n"
            "- 'Mass Times – Our Lady's, Kempston' → church='Our Lady's', "
            "church_location='Kempston'."
        ),
    ),
    Parish(
        name="St Alban's",
        source_url="https://www.stalbanswinslow.org.uk/newsletters/",
        strategy="pdf_archive",
        location="Winslow",
        outside_mk=True,
    ),
    Parish(
        name="MK Parishes Newsletter (Mailchimp)",
        source_url="https://us19.campaign-archive.com/home/?u=24790f2492cfb4670c635f745&id=2ebd0e3fcd",
        strategy="mailchimp",
        location="St Barnabas Cluster",
    ),
]
