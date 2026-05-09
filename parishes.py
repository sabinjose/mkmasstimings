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
    Church(name="Matki Bożej Częstochowskiej", area="Dunstable",           postcode="LU6 3AZ"),
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
    # Optional church-name fallback for single-church parishes that share an
    # `area` with another church (e.g. English St Mary's vs Polish parish in
    # Dunstable). Used by main.py when the LLM hasn't set `church` on a
    # service. Multi-church parishes leave this blank — the LLM fills `church`
    # per service from the bulletin's columns.
    church_name: str = ""


PARISHES: list[Parish] = [
    Parish(
        name="St Augustine's",
        source_url="https://www.st-augustinesmk.org.uk/web/newsletter/",
        strategy="page",
        location="Milton Keynes",
        hints=(
            "The PARISH LITURGIES block has TWO 'w/c <Sunday-date>' "
            "subheadings:\n"
            "  1. EARLIER block ('w/c <prior-Sunday>'): trailing days of "
            "     the week just ending — usually Friday and Saturday.\n"
            "  2. LATER block ('w/c <focal-Sunday>'): the upcoming "
            "     week — Sunday plus Mon/Tue/Wed/Thu/Fri/Sat.\n"
            "\n"
            "Extract EVERY service in BOTH blocks — do NOT stop after "
            "the focal Sunday. Each weekday named in a block belongs to "
            "the corresponding ISO date in the CALENDAR REFERENCE table "
            "above; look up the date there rather than computing it.\n"
            "\n"
            "Set `week_of` to the focal Sunday — the date in the main "
            "page heading at the top of the newsletter (the line that "
            "names the Sunday's liturgical title and ISO date). Sunday "
            "English Masses (08:00, 09:30, 11:30, 18:30) belong to "
            "`week_of`, never to the prior Sunday.\n"
            "\n"
            "Recurring services not in the dated grid: Polish Mass "
            "Thursday 19:00 and Sunday 14:00 — emit one entry per "
            "matching day in the focal week.\n"
            "\n"
            "Combined liturgies in the grid MUST be split into separate "
            "service entries at the same time — e.g. 'Adoration/ "
            "Confession' becomes one Adoration entry AND one Confession "
            "entry; 'Adoration/ Rosary' becomes one Adoration entry "
            "AND one Rosary entry; 'Adoration/ Morning Prayer (Lauds)' "
            "becomes Adoration + Rosary (treat 'Morning Prayer/ Lauds' "
            "as a Rosary-style devotion)."
        ),
    ),
    Parish(
        name="Catholic Bletchley (All Saints / St Thomas Aquinas)",
        source_url="https://catholic-bletchley.com/",
        strategy="pdf_archive",
        location="Bletchley",
        hints=(
            "The bulletin sometimes mentions a Rosary 'daily, 30 minutes "
            "before morning Mass' or similar. Do NOT emit a Rosary entry "
            "unless the bulletin gives a concrete clock time for it. "
            "'Before Mass', 'after Mass', 'daily', 'before/after the "
            "weekday Masses' are not times — skip those entries."
        ),
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
            "Saturdays in this bulletin commonly have multiple service "
            "blocks (morning Mass + Confessions at one church AND an "
            "evening Vigil Mass at the other). Read every line under the "
            "Saturday heading and emit every printed time — don't stop "
            "after the first Mass.\n"
            "\n"
            "Holy days of obligation (Ascension, Assumption, etc.) usually "
            "have multiple Masses across both churches at different times "
            "of day. Emit every Mass time printed under the feast — do "
            "not collapse them into one.\n"
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
        church_name="St. Mary's",
    ),
    Parish(
        name="Sacred Heart",
        source_url="https://sacredheartflitwick.co.uk/newsletters/",
        strategy="pdf_archive",
        location="Flitwick",
        hints=(
            "The bulletin describes Confession as 'Before Mass on "
            "Saturday or on request' and Rosary as '30 minutes before "
            "Mass'. Do NOT emit those entries: 'before Mass', 'on "
            "request', '30 minutes before Mass' are not concrete clock "
            "times. Only emit Confession or Rosary entries when the "
            "bulletin prints an explicit HH:MM time."
        ),
    ),
    Parish(
        name="Sacred Heart",
        source_url="https://www.sacredheartlb.org.uk/service-times/",
        strategy="pdf_archive",
        location="Leighton Buzzard",
        outside_mk=True,
        hints=(
            "Bulletin lists every weekday with a Mass intention beside "
            "it. Holy days of obligation (e.g. 'The Ascension') still "
            "have a Mass at the time printed in the bulletin — extract "
            "it, don't skip it just because the day's heading reads as "
            "a feast title rather than 'Mass'. Day-specific "
            "cancellations such as 'No Mass today' on a particular "
            "weekday must be emitted with cancelled=true."
        ),
    ),
    Parish(
        name="Polska Parafia (Matki Bożej Częstochowskiej)",
        source_url="https://parafiadunstable.co.uk/informacje/biuletyn-parafialny",
        strategy="pdf_archive",
        location="Dunstable",
        outside_mk=True,
        church_name="Matki Bożej Częstochowskiej",
        hints=(
            "STRICT RULE: every emitted service MUST have an HH:MM "
            "clock time. The Polish bulletin frequently contains prose "
            "such as 'Litanie odmawiane podczas adoracji' / 'Litanies "
            "recited during adoration'. This is NOT a separate dated "
            "Adoration service — it is commentary on something that "
            "happens during another scheduled liturgy. Do NOT emit an "
            "Adoration entry for it. Do NOT emit any service at all "
            "unless the bulletin prints a specific HH:MM time for that "
            "service on a specific date. If you can't read a clock time "
            "off the bulletin for a given liturgy, skip it entirely."
        ),
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
            "church_location='Kempston'.\n"
            "\n"
            "Benediction is sometimes named in the bulletin without a "
            "clock time (e.g. 'Benediction follows Mass'). Do NOT emit a "
            "Benediction entry unless the bulletin prints an explicit "
            "HH:MM time for it."
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
        hints=(
            "Each weekday in the schedule lists the daily Mass at one "
            "or more churches in the cluster (Christ the Cornerstone, "
            "Our Lady of Lourdes, St Edward's, Christ the King, St "
            "Bede's, St Mary's Woburn Sands). EVERY printed time + "
            "church entry under each weekday is a real Mass — do not "
            "skip any. Set `church` to the church name and "
            "`church_location` to its area (Coffee Hall / Shenley "
            "Church End / Kents Hill / Newport Pagnell / Woburn Sands "
            "/ Central MK). Cancellations like 'NO MORNING MASS' must "
            "be emitted with cancelled=true."
        ),
    ),
]
