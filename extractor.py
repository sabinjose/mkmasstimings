"""LLM-based mass-times extractor.

Vendor-agnostic via LiteLLM — set MODEL to any LiteLLM-supported model
(e.g. "anthropic/claude-sonnet-4-5", "openai/gpt-4o-mini", "gemini/gemini-1.5-flash").
The corresponding *_API_KEY env var must be set.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta
from typing import Any

import litellm
from litellm import completion

# gpt-5 family doesn't accept temperature=0 (only =1), and may rename
# `max_tokens` to `max_completion_tokens`. Let LiteLLM silently drop params
# the chosen model rejects, so the same call works across providers.
litellm.drop_params = True

DEFAULT_MODEL = os.environ.get("MASSTIMINGS_MODEL", "openai/gpt-5")

JSON_SCHEMA_HINT = """
Return ONLY a JSON object matching this schema (no prose, no markdown fences):

{
  "parish": string,                        // parish name as given
  "week_of": string | null,                // ISO date (YYYY-MM-DD) of the Sunday this newsletter covers, or null if unclear
  "source_date": string | null,            // ISO date the newsletter itself is dated, if different from week_of
  "services": [
    {
      "date": string | null,               // ISO date (YYYY-MM-DD) if known, else null
      "day": string,                       // "Sunday", "Monday", ... or "Daily"
      "time": string | null,               // 24h "HH:MM" — REQUIRED for non-cancelled services.
                                           // null ONLY when `cancelled` is true. "varies" allowed
                                           // if (and only if) the bulletin literally says the
                                           // time varies week-to-week.
      "type": string,                      // "Mass", "Vigil Mass", "Confession", "Adoration", "Rosary", etc.
      "church": string | null,             // SPECIFIC church/building name when the newsletter
                                           // covers multiple sites (e.g. "St Bernardine's", "St Martin's",
                                           // "St Francis de Sales", "St Mary Magdalene"). Null if the
                                           // newsletter only covers one church or doesn't say.
      "church_location": string | null,    // The town/area for `church` if disambiguated, e.g. "Buckingham"
                                           // when church="St Bernardine's", "Brackley" for "St Martin's"
      "language": string | null,           // e.g. "Polish", null for English
      "cancelled": boolean,                // true ONLY when this liturgy is cancelled
                                           // ("No Mass today", "Adoration cancelled this week").
                                           // When true, `time` MUST be null. When false (the
                                           // normal case), `time` MUST be a concrete HH:MM.
      "notes": string | null               // feast day name, "no mass this week", etc.
    }
  ],
  "confidence": "high" | "medium" | "low", // your confidence the data is current and complete
  "notes": string | null                   // anything the user should know (e.g. "no times found")
}
""".strip()

SYSTEM_PROMPT = (
    "You extract Catholic mass / liturgy schedules from parish newsletters. "
    "The text may be HTML-extracted webpage content or text from a PDF newsletter. "
    "Extract EVERY scheduled liturgy (Mass, Vigil, Confession, Adoration, Rosary, "
    "Benediction, Holy Hour) the newsletter shows. "
    "Use 24-hour times. Be conservative: if a time is ambiguous, omit it rather than guess.\n\n"
    "RECURRING WEEKLY SCHEDULES: newsletters often describe regular liturgies in prose "
    "rather than in the dated schedule grid (e.g. 'Polish Mass each Thursday at 7pm and "
    "Sunday at 2pm', 'Confessions every Saturday 5–5:30pm', 'Rosary each weekday before "
    "Mass'). For each such weekly recurrence, emit ONE service entry per matching day "
    "within the week the newsletter covers (i.e. between the Sunday `week_of` and the "
    "following Saturday). Set the `date` to the actual ISO date for that day. Do this "
    "EVEN IF that day's entry in the dated schedule says 'No Mass' for the English "
    "service — recurring Polish or other-language Masses can still happen.\n\n"
    "COMBINED LITURGIES: when one newsletter line mentions multiple liturgies happening "
    "at the same time, emit a SEPARATE service entry for EACH liturgy at the same time, "
    "NOT one row with the second stuffed into `notes`. The combinator can be ANY of "
    "'&', 'and', 'with', '+', '/', 'followed by', '/ ' (slash plus space — common in "
    "bulletins printed as 'Adoration/ Confession' or 'Adoration/ Rosary'). For each "
    "such pair, emit BOTH liturgies as separate entries — never collapse them. "
    "Examples that MUST split into two rows:\n"
    "  - 'Rosary & Confessions' → Rosary + Confession\n"
    "  - 'Adoration/ Confession' → Adoration + Confession\n"
    "  - 'Adoration/ Rosary' → Adoration + Rosary\n"
    "  - 'Adoration/ Morning Prayer (Lauds)' → Adoration + Rosary (treat Morning "
    "    Prayer / Lauds as a Rosary-style devotion)\n"
    "  - 'Confession + Rosary' → Confession + Rosary\n"
    "  - 'Exposition followed by Benediction' → Adoration + Benediction\n"
    "Reason: the website groups by `type` (Confessions, Adoration, etc.) and a "
    "confession hidden inside a Rosary row's notes won't appear in the Confessions "
    "section.\n\n"
    "CANCELLATIONS: emit a service entry ONLY when a specific LITURGY is cancelled "
    "(e.g. 'No Mass on Wednesday', 'Adoration cancelled this week', 'No Confessions "
    "Saturday'). For these set `cancelled` to true, `time` to null, and `notes` to "
    "the cancellation phrasing from the bulletin (e.g. 'No Mass today'). For every "
    "non-cancelled service, `cancelled` MUST be false. The frontend uses this flag "
    "directly — do NOT rely on `notes` text alone to communicate cancellation. Do "
    "NOT emit cancellation entries for non-liturgical events such as 'No Open "
    "House', 'Office closed', 'No coffee morning', 'No youth group', 'No bingo' — "
    "those aren't liturgies and shouldn't appear on a mass-times page.\n\n"
    "OMIT WITHOUT TIME: every emitted service MUST have a concrete clock time "
    "(HH:MM, or 'varies' if the bulletin literally says the time varies). The "
    "following are NOT times and MUST cause the entry to be skipped entirely:\n"
    "  - 'before Mass', 'after Mass', '30 minutes before Mass'\n"
    "  - 'on request', 'by appointment', 'as announced', 'see notice board'\n"
    "  - 'TBC', 'TBA', dashes, blanks\n"
    "Skip the entry entirely — do NOT emit it with `time=null`. The ONLY services "
    "allowed to carry `time=null` are explicit liturgy cancellations (see the "
    "CANCELLATIONS rule above). A row with no concrete clock time renders as a "
    "useless '—' for users and must not appear.\n\n"
    "LANGUAGE: newsletters may be in English, Polish, or other languages. "
    "Translate liturgy types into English (Msza Św. → 'Mass', Spowiedź → 'Confession', "
    "Adoracja → 'Adoration', Różaniec → 'Rosary', Koronka → 'Chaplet'). Set the "
    "`language` field on each service to the language the liturgy is celebrated in "
    "(e.g. 'Polish' for a Polish-language parish; null for English).\n\n"
    "MULTI-CHURCH NEWSLETTERS: some parishes cover two or more churches in one bulletin "
    "(e.g. 'St Bernardine's at Buckingham AND St Martin's at Brackley', or 'St Francis "
    "de Sales (Wolverton) AND St Mary Magdalene (Stony Stratford)'). The schedule is "
    "often laid out as parallel columns or a table with one column per church, sometimes "
    "with the day on the left. When this is the case, populate the `church` and "
    "`church_location` fields on EACH service so the reader knows which building to go "
    "to. If a Mass time is in the column under 'St Martin's', that service has "
    "church='St Martin's' and church_location='Brackley'. Be careful: in PDFs the "
    "columns may have been linearized into one stream — use cues like the column "
    "header, the church name in the text, or the time pattern (e.g. some churches have "
    "consistent times like 9:00 vs 11:00).\n\n"
    "DATE HANDLING — read carefully:\n"
    "1. Find the newsletter's own date heading (e.g. 'Sunday 3rd May 2026', '5th Sunday of "
    "Easter, 3rd May 2026'). That is the `week_of` Sunday — set it to that ISO date and "
    "use that YEAR for every service entry.\n"
    "2. The schedule may list days as 'Saturday 2nd', 'Sunday 3rd', 'Monday 4th' etc. "
    "Combine those day numbers with the year from step 1 to compute each `date`.\n"
    "3. NEVER shift dates to today's date or to the current week. The newsletter may be "
    "older than today; report what the newsletter actually says. If `week_of` is before "
    "today's date, set `confidence` to 'medium' and add a `notes` line saying the "
    "newsletter appears stale.\n"
    "4. If the newsletter has no explicit year anywhere, fall back to today's year (given "
    "in the user message). Never infer a year from training data or incidental mentions "
    "like 'the 2024 film X'.\n\n"
    "Return only the JSON object specified by the user — no prose, no code fences."
)


_COMBINED_LITURGY_RE = re.compile(
    r"(\d{1,2}[:.]?\d{0,2}\s?(?:am|pm|AM|PM|noon)?)\s*"
    r"(Adoration|Exposition|Rosary|Confession|Reconciliation)\s*"
    r"/\s*"
    r"(Adoration|Exposition|Rosary|Confession|Reconciliation|Morning\s+Prayer\s*\(?Lauds?\)?|Lauds|Benediction)",
)


def _split_slash_combined_liturgies(text: str) -> str:
    """Rewrite 'TIME X/ Y' as two lines so the LLM doesn't have to recognise
    a slash as a list separator. Handles bulletins (notably St Augustine's)
    that print combined liturgies as 'Adoration/ Confession'."""
    def repl(m: "re.Match[str]") -> str:
        return f"{m.group(1)} {m.group(2)}\n{m.group(1)} {m.group(3)}"
    return _COMBINED_LITURGY_RE.sub(repl, text)


def extract_mass_times(
    parish_name: str,
    text: str,
    *,
    hints: str = "",
    model: str = DEFAULT_MODEL,
    max_chars: int = 30_000,
) -> dict[str, Any]:
    """Call the configured LLM to turn raw newsletter text into structured data."""
    text = _split_slash_combined_liturgies(text)
    if len(text) > max_chars:
        text = text[:max_chars]

    today_dt = date.today()
    today = today_dt.isoformat()
    calendar = _build_calendar(today_dt, days_back=14, days_forward=28)
    hints_block = f"\nKNOWN-SCHEDULE HINTS (authoritative — use these to disambiguate):\n{hints}\n" if hints else ""
    user_msg = (
        f"Parish: {parish_name}\n"
        f"Today's date: {today} (use this year if the newsletter has no explicit year)\n"
        f"\n"
        f"CALENDAR REFERENCE — when the bulletin names a weekday under a 'w/c "
        f"<date>' header (or any dated grid), look the weekday up in the table "
        f"below to get the ISO date. Do NOT compute weekday arithmetic yourself.\n"
        f"{calendar}\n"
        f"{hints_block}\n"
        f"Newsletter / page content follows between <<<>>>:\n\n"
        f"<<<\n{text}\n>>>\n\n"
        f"{JSON_SCHEMA_HINT}"
    )

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0,
        "max_tokens": 8000,
        "response_format": {"type": "json_object"},
    }
    # gpt-5 family is a reasoning model that allocates output tokens to
    # internal reasoning by default. 'medium' gives the model enough
    # headroom to follow multi-step instructions consistently — extract
    # both trailing-week and focal-week blocks, split combined liturgies,
    # honour parish hints. Lower levels skip steps under load.
    if "gpt-5" in model:
        kwargs["reasoning_effort"] = "medium"
        kwargs["max_tokens"] = 16000

    resp = completion(**kwargs)
    content = resp.choices[0].message.content or ""
    return _parse_json(content, parish_name)


def _build_calendar(today: date, *, days_back: int, days_forward: int) -> str:
    """Return an ISO-date → weekday lookup table the LLM can grep instead of
    doing weekday arithmetic. Covers a window around today big enough for a
    bulletin's prior-week trailing days plus its next two weeks of content."""
    lines = []
    start = today - timedelta(days=days_back)
    for i in range(days_back + days_forward + 1):
        d = start + timedelta(days=i)
        marker = "  ← today" if d == today else ""
        lines.append(f"  {d.isoformat()} {d.strftime('%A')}{marker}")
    return "\n".join(lines)


def _parse_json(content: str, parish_name: str) -> dict[str, Any]:
    """Forgiving JSON parse — strips code fences if the model added them."""
    stripped = content.strip()
    if stripped.startswith("```"):
        # remove leading ``` or ```json and trailing ```
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped
        if stripped.endswith("```"):
            stripped = stripped[: -3]
        stripped = stripped.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as e:
        return {
            "parish": parish_name,
            "week_of": None,
            "services": [],
            "confidence": "low",
            "notes": f"JSON parse failed: {e}. Raw model output: {content[:500]}",
        }
