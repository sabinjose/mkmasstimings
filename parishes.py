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
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Parish:
    name: str
    source_url: str
    strategy: str
    location: str = ""
    # Optional ground-truth hint passed to the LLM. Use for multi-church parishes
    # where column layout in the PDF is too ambiguous to disambiguate from text alone.
    hints: str = ""


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
    ),
    Parish(
        name="Polska Parafia (Matki Bożej Częstochowskiej)",
        source_url="https://parafiadunstable.co.uk/informacje/biuletyn-parafialny",
        strategy="pdf_archive",
        location="Dunstable (Polish)",
    ),
    Parish(
        name="St Bernardine's & St Martin's",
        source_url="https://stbernardines.org/latest-parish-newsletter/",
        strategy="gdoc",
        location="Buckingham / Brackley",
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
    ),
    Parish(
        name="MK Parishes Newsletter (Mailchimp)",
        source_url="https://us19.campaign-archive.com/home/?u=24790f2492cfb4670c635f745&id=2ebd0e3fcd",
        strategy="mailchimp",
        location="St Barnabas Cluster",
    ),
]
