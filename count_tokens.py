"""Estimate token + cost for one full extraction run across all parishes."""

from __future__ import annotations

import sys

import tiktoken

import fetcher
from extractor import JSON_SCHEMA_HINT, SYSTEM_PROMPT
from main import gather_text
from parishes import PARISHES

# gpt-4o family uses the o200k_base encoding
enc = tiktoken.get_encoding("o200k_base")

# Pricing (USD per 1M tokens) — gpt-4o-mini as of early 2026
PRICE_INPUT_PER_M = 0.15
PRICE_OUTPUT_PER_M = 0.60
ASSUMED_OUTPUT_TOKENS = 800  # typical structured JSON for ~10-15 services


def count(text: str) -> int:
    return len(enc.encode(text))


def main() -> int:
    total_in = 0
    total_out = 0
    print(f"{'Parish':<48} {'Location':<28} {'Input tok':>10} {'Output tok':>11}")
    print("-" * 104)
    for parish in PARISHES:
        try:
            text, _ = gather_text(parish)
        except Exception as e:
            print(f"{parish.name[:47]:<48} {parish.location[:27]:<28}  fetch err: {e}")
            continue

        # Mirror what extractor.py builds:
        # system + user(parish + today + schema hint + content)
        user_msg = (
            f"Parish: {parish.name}\n"
            f"Today's date: 2026-05-06 (use this year ...)\n\n"
            f"Newsletter / page content follows between <<<>>>:\n\n"
            f"<<<\n{text[:30_000]}\n>>>\n\n"
            f"{JSON_SCHEMA_HINT}"
        )
        in_tok = count(SYSTEM_PROMPT) + count(user_msg)
        out_tok = ASSUMED_OUTPUT_TOKENS
        total_in += in_tok
        total_out += out_tok
        print(f"{parish.name[:47]:<48} {parish.location[:27]:<28} {in_tok:>10,} {out_tok:>11,}")

    print("-" * 104)
    print(f"{'TOTAL per run':<48} {'':<28} {total_in:>10,} {total_out:>11,}")
    print()

    cost_in = total_in / 1_000_000 * PRICE_INPUT_PER_M
    cost_out = total_out / 1_000_000 * PRICE_OUTPUT_PER_M
    cost_run = cost_in + cost_out
    print(f"Cost / run  (gpt-4o-mini, ${PRICE_INPUT_PER_M}/M in, ${PRICE_OUTPUT_PER_M}/M out): ${cost_run:.5f}")
    print()

    schedules = [
        ("1× / week",            1),
        ("2× / week (Wed+Sun)",  2),
        ("5× / week (Wed–Sun)",  5),
        ("daily",                7),
    ]
    print(f"{'Schedule':<28} {'Tokens / week':>16} {'Tokens / month':>18} {'Cost / month':>14} {'Cost / year':>14}")
    print("-" * 96)
    for label, runs_per_week in schedules:
        toks_week = (total_in + total_out) * runs_per_week
        toks_month = toks_week * 4.345  # avg weeks/month
        cost_month = cost_run * runs_per_week * 4.345
        cost_year = cost_run * runs_per_week * 52
        print(f"{label:<28} {toks_week:>16,} {toks_month:>18,.0f} {'$'+format(cost_month,'.3f'):>14} {'$'+format(cost_year,'.2f'):>14}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
