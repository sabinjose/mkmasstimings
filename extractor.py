"""LLM-based mass-times extractor.

Vendor-agnostic via LiteLLM — set MODEL to any LiteLLM-supported model
(e.g. "anthropic/claude-sonnet-4-5", "openai/gpt-4o-mini", "gemini/gemini-1.5-flash").
The corresponding *_API_KEY env var must be set.
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

import litellm
from litellm import completion

# gpt-5 family doesn't accept temperature=0 (only =1), and may rename
# `max_tokens` to `max_completion_tokens`. Let LiteLLM silently drop params
# the chosen model rejects, so the same call works across providers.
litellm.drop_params = True

DEFAULT_MODEL = os.environ.get("MASSTIMINGS_MODEL", "openai/gpt-4o-mini")

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
      "time": string,                      // 24h "HH:MM", or "varies" if unspecified
      "type": string,                      // "Mass", "Vigil Mass", "Confession", "Adoration", "Rosary", etc.
      "church": string | null,             // SPECIFIC church/building name when the newsletter
                                           // covers multiple sites (e.g. "St Bernardine's", "St Martin's",
                                           // "St Francis de Sales", "St Mary Magdalene"). Null if the
                                           // newsletter only covers one church or doesn't say.
      "church_location": string | null,    // The town/area for `church` if disambiguated, e.g. "Buckingham"
                                           // when church="St Bernardine's", "Brackley" for "St Martin's"
      "language": string | null,           // e.g. "Polish", null for English
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
    "at the same time (e.g. 'Rosary & Confessions', 'Adoration with Confession', "
    "'Confession + Rosary', 'Exposition followed by Benediction'), emit a SEPARATE "
    "service entry for EACH liturgy at the same time, NOT one row with the second "
    "stuffed into `notes`. Reason: the website groups by `type` (Confessions, Adoration, "
    "etc.) and a confession hidden inside a Rosary row's notes won't appear in the "
    "Confessions section.\n\n"
    "CANCELLATIONS: emit a service entry ONLY when a specific LITURGY is cancelled "
    "(e.g. 'No Mass on Wednesday', 'Adoration cancelled this week', 'No Confessions "
    "Saturday'). Set `time` to null and `notes` to the cancellation text (e.g. 'No "
    "Mass today'). The frontend renders these distinctly. Do NOT emit cancellation "
    "entries for non-liturgical events such as 'No Open House', 'Office closed', "
    "'No coffee morning', 'No youth group', 'No bingo' — those aren't liturgies and "
    "shouldn't appear on a mass-times page.\n\n"
    "OMIT WITHOUT TIME: if a recurring liturgy is mentioned but you can't determine "
    "any time for it (the newsletter doesn't say when), do NOT emit it — a row with "
    "no time is not actionable for users.\n\n"
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


def extract_mass_times(
    parish_name: str,
    text: str,
    *,
    hints: str = "",
    model: str = DEFAULT_MODEL,
    max_chars: int = 30_000,
) -> dict[str, Any]:
    """Call the configured LLM to turn raw newsletter text into structured data."""
    if len(text) > max_chars:
        text = text[:max_chars]

    today = date.today().isoformat()
    hints_block = f"\nKNOWN-SCHEDULE HINTS (authoritative — use these to disambiguate):\n{hints}\n" if hints else ""
    user_msg = (
        f"Parish: {parish_name}\n"
        f"Today's date: {today} (use this year if the newsletter has no explicit year)\n"
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
        "max_tokens": 4000,
        "response_format": {"type": "json_object"},
    }
    # gpt-5 reasoning models waste the token budget on reasoning by default.
    # Disable reasoning so the budget goes to JSON output.
    if "gpt-5" in model:
        kwargs["reasoning_effort"] = "none"
        kwargs["max_tokens"] = 8000

    resp = completion(**kwargs)
    content = resp.choices[0].message.content or ""
    return _parse_json(content, parish_name)


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
