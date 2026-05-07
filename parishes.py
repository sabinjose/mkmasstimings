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
            "This parish has two churches. The newsletter lays them out in two "
            "columns; column extraction is unreliable. Use this regular schedule "
            "to assign each service its church/church_location:\n"
            "- St Mary Magdalene (Stony Stratford): Sunday 9:15am Mass.\n"
            "- St Francis de Sales (Wolverton): Saturday 6:30pm Vigil, Sunday "
            "11:30am Mass, weekday Masses (Mon/Tue/Wed/Fri 12:00pm, Thu 10:00am, "
            "Sat morning 10:00am), Wednesday 12:30pm Adoration, Saturday morning "
            "Confessions.\n"
            "If a service doesn't match the regular pattern, note it in `notes`."
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
    ),
    Parish(
        name="MK Parishes Newsletter (Mailchimp)",
        source_url="https://us19.campaign-archive.com/home/?u=24790f2492cfb4670c635f745&id=2ebd0e3fcd",
        strategy="mailchimp",
        location="St Barnabas Cluster",
    ),
]
