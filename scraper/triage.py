"""
triage.py — decides which notices belong in the register.

NSE alone publishes roughly 30 notices a day, most of them routine (a new
listing, a fund launch, one company's suspension). Classifying all of them
in full would bury the few that change how brokers and fintechs operate,
and would cost far more. So titles from mixed feeds are screened first by a
small, cheap model, in batches.

Three safeguards keep the filter from hiding something that matters:
  1. The model is told to include anything it's unsure about.
  2. A deterministic keyword list overrides the model. Any title naming
     brokers, KYC, margins, cyber security and so on is always kept.
  3. Every item set aside is written to data/filtered.json with the reason,
     and the dashboard lists them so anyone can audit the filter.
"""

import os
import re
import json
import sys

TRIAGE_MODEL = os.environ.get("TRIAGE_MODEL", "claude-haiku-4-5-20251001")
BATCH = 40

ALWAYS_KEEP = re.compile(
    r"master circular|master direction|framework|cyber|\bkyc\b|know your client|anti.?money|\baml\b|\bcft\b|"
    r"margin|risk management|trading members?|stock ?brokers?|authori[sz]ed persons?|sub.?brokers?|"
    r"depository participants?|\bdps?\b|clearing members?|investment advis|research analyst|"
    r"payment aggregator|payment system|digital lending|\bupi\b|\bnbfc|investor protection|"
    r"grievance|unlawful activities|designat|sanction|compliance|reporting|inspection|penalt",
    re.I,
)

PROMPT = """You screen regulatory notices for a tracker used by India's broking and fintech ecosystem: stock brokers and authorised persons, depository participants, clearing members, investment advisers and research analysts, mutual fund distributors, payment system operators and payment aggregators, fintech apps, NBFCs and digital lenders.

For each numbered notice, decide whether it belongs in the tracker.

Include it if it could change what any of those entities must do: obligations, processes, systems or technology, risk or margin rules, reporting, KYC or anti-money-laundering (including sanctions or terrorist designations that require client screening), cyber security, client-facing requirements, fees, or market-wide trading operations (trading hours, settlement holidays, new trading-system versions to deploy).

Set it aside if it only concerns one company, security or scheme, or is a prudential matter only for banks, with no obligation for those entities. Examples: new listings, further issues, suspension of a named company, trade-for-trade transfers, corporate actions, face value splits, a single mutual fund scheme's launch or suspension, stock-specific surveillance lists, government lines of credit, investment-portfolio rules for banks.

When unsure, include it. Wrongly setting aside a relevant notice is far worse than including a routine one.

Respond with only a JSON array, one object per notice, in order: {"i": <number>, "include": true or false, "reason": "<under 15 words>"}"""


def _parse(raw, n):
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    data = json.loads(raw)
    out = {}
    for d in data:
        try:
            out[int(d["i"])] = (bool(d.get("include", True)), str(d.get("reason", ""))[:160])
        except (KeyError, ValueError, TypeError):
            continue
    return out


def apply_rules(item, include, reason):
    """Deterministic override: never set aside a title that names a core obligation."""
    if not include:
        m = ALWAYS_KEEP.search(item["title"])
        if m:
            return True, f"Kept by keyword rule (mentions “{m.group(0)}”); model suggested setting aside: {reason}"
    return include, reason


def triage(items, client=None):
    """Returns [(item, include, reason)]. Raises on API failure so the caller
    leaves these items unseen and retries them on the next run."""
    if not items:
        return []
    from anthropic import Anthropic
    client = client or Anthropic()
    results = []
    for start in range(0, len(items), BATCH):
        batch = items[start:start + BATCH]
        listing = "\n".join(f"{i + 1}. [{it['regulator']}] {it['title']}" for i, it in enumerate(batch))
        msg = client.messages.create(model=TRIAGE_MODEL, max_tokens=4000, system=PROMPT,
                                     messages=[{"role": "user", "content": listing}])
        try:
            decided = _parse(msg.content[0].text, len(batch))
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            print(f"[triage] WARNING: unreadable triage response ({e}); keeping the whole batch.", file=sys.stderr)
            decided = {}
        for i, it in enumerate(batch, 1):
            include, reason = decided.get(i, (True, "No triage decision returned; kept by default."))
            results.append((it,) + apply_rules(it, include, reason))
    return results
