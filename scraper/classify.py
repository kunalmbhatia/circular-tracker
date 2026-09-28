"""
classify.py — runs one circular's source text through Claude to extract:
doc type, parent-circular mapping, impact areas, intent/action/impact, and
per-field confidence — with validation checks layered on top of the model's
own self-reported confidence so nothing is published as fact that the model
merely inferred or guessed.

Model: defaults to `claude-sonnet-5`. Override with the ANTHROPIC_MODEL env
var if you want a cheaper/faster model (e.g. a Haiku-class model) for this
volume of text, or if the model string above has since been superseded —
check https://docs.claude.com for the current list before assuming this one
still exists.
"""

import os
import re
import json
import sys

from anthropic import Anthropic

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

SYSTEM_PROMPT = """You are a Regulatory Circular Classification & Extraction Engine
for India's broking and fintech ecosystem. You are given the full text of one
circular, notification or communiqué, and the body that issued it (SEBI, RBI,
an exchange, a clearing corporation, a depository, IFSCA or NPCI). You extract
structured data for a public tracking dashboard used by regulators, brokers,
fintechs, compliance teams and investors. Accuracy matters more than completeness: an empty field is
fine, a fabricated one is not.

HARD RULES:
- Every circular number, date and cross-reference you output must appear
  verbatim in the source text you were given. If a value is not in the text,
  output the exact string "NOT STATED IN SOURCE" for that field — never infer
  or recall a circular number from your own training data.
- Never guess at the expansion of an abbreviation you don't recognize from
  the text itself. Say so in impact_summary instead of guessing.
- Ground every non-obvious claim in a short verbatim excerpt (under 25 words)
  in source_excerpt_citations, so a human can verify it against the source.

Classify and extract the following, and respond with ONLY a JSON object
(no markdown fences, no commentary) matching this exact shape:

{
  "circular_no": string or "NOT STATED IN SOURCE",
  "date": "YYYY-MM-DD or null",
  "doc_type": one of ["Fresh Circular","Amendment","Addendum","Corrigendum","Master Circular","FAQ/Clarification"],
  "parent_circular_no": string, "NOT STATED IN SOURCE", or null (null only if the text is explicitly standalone with no parent referenced),
  "parent_circular_date": "YYYY-MM-DD", "NOT STATED IN SOURCE", or null,
  "implements": array of circulars issued by ANOTHER body that this document carries out or is issued in pursuance of (typically an exchange or depository circular implementing a SEBI circular, or an NPCI circular implementing an RBI direction), each as {"regulator": "SEBI" | "RBI" | other issuing body, "circular_no": the number exactly as written in the text, "date": "YYYY-MM-DD" or null}. Empty array if none is cited. Parent/amended circulars from the SAME body go in parent_circular_no instead,
  "impact_areas": array of strings, chosen only from: ["Stock Brokers","Depository Participants","Clearing Corporations","Stock Exchanges","Mutual Funds/AMCs","AIFs/PMS","Investment Advisers/Research Analysts","KYC/AML","Margin Trading","Surveillance/Market Abuse","Cyber Security/Cyber Resilience","Listed Companies (LODR/Disclosure)","FPI","Insider Trading","Takeover Code","Investor Grievance/SCORES","Corporate Bonds/Debt Market","Commodity Derivatives Segment","ESG/BRSR","Payments/UPI","Digital Lending/NBFC","Data Protection/Privacy","Foreign Exchange (FEMA)","Trading Operations","GIFT City/IFSC","Other"],
  "applicability": short free-text string naming who this applies to (e.g. "Stock Exchanges / Clearing Corporations"),
  "intent": 1-2 sentence paraphrase (not a quote) of the regulatory problem/goal being addressed,
  "action_required": what the regulated entity must concretely do, including any deadline exactly as stated,
  "effective_date": "YYYY-MM-DD", "NOT STATED IN SOURCE", or null,
  "key_dates": array of every compliance-relevant date the text states (effective dates, implementation or compliance deadlines, reporting start dates, extended timelines), each as {"label": short plain label such as "Compliance deadline", "date": "YYYY-MM-DD", "quote": the verbatim sentence fragment (under 25 words) from the source that states this date}. Empty array if the text states none. Never compute a date the text does not state outright (e.g. do not turn "within 30 days" into a calendar date),
  "impact_summary": 1-2 sentences on who is affected and how,
  "overall_confidence": one of ["Certain","Inferred","Needs Review"],
  "confidence_flags": object mapping any uncertain field name to a short explanation of why,
  "source_excerpt_citations": array of short verbatim excerpts (each under 25 words) supporting the classification
}

If the source text is too short, garbled, or clearly not a regulatory circular
to classify responsibly, set overall_confidence to "Needs Review" and explain
why in confidence_flags rather than filling fields with best guesses."""


# Any issuer's reference: a letter group plus a 4-digit year somewhere
# (SEBI/HO/..., NSE/SURV/..., FEMA 23(R)/(1)/2026-RB, RBI/2026-27/41...).
CIRCULAR_NO_HINT_RE = re.compile(r"[A-Za-z]{2,}.*\d{3,}|\d{3,}.*[A-Za-z]{2,}|\d+\s*/\s*(19|20)\d{2}")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALIDATOR_VERSION = 3
ELLIPSIS_RE = re.compile(r"\.{3,}|\u2026|\[\s*\.\.\.\s*\]")


def _norm_ws(s):
    """Collapse whitespace and unify quote/dash characters."""
    s = (s or "").replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", s).strip().lower()


def _letters(s):
    """Letters and digits only. PDF extraction mangles punctuation, hyphenation,
    ligatures and spacing; comparing on this form tolerates all of that while an
    invented sentence still won't match."""
    s = (s or "").replace("\ufb01", "fi").replace("\ufb02", "fl")
    return re.sub(r"[^0-9a-z]", "", s.lower())


def quote_in_source(quote, source_letters):
    """True if the quote appears in the source. An elided quote ('A ... B') passes
    when every part appears in order; parts under 12 characters are ignored."""
    parts = [_letters(p) for p in ELLIPSIS_RE.split(quote or "")]
    parts = [p for p in parts if len(p) >= 12] or [_letters(quote)]
    pos = 0
    for p in parts:
        i = source_letters.find(p, pos)
        if i < 0:
            return False
        pos = i + len(p)
    return True


def _validate(record, known_circular_numbers, source_text=None):
    """Layer deterministic checks on top of the model's own confidence.

    Two severities:
      Needs Review  - something may be WRONG (a quote not in the text, a malformed
                      field, an internal contradiction).
      Inferred      - nothing is wrong, but something is unconfirmed (the parent
                      circular isn't in this register yet).
    The model's own flags are never removed."""
    flags = dict(record.get("confidence_flags") or {})
    record["model_confidence"] = record.get("overall_confidence", "Needs Review")
    rank = {"Certain": 0, "Inferred": 1, "Needs Review": 2}
    worst = record["model_confidence"] if record["model_confidence"] in rank else "Needs Review"

    def flag(key, reason, level="Needs Review"):
        nonlocal worst
        flags[key] = reason
        if rank[level] > rank[worst]:
            worst = level

    src = _letters(source_text) if source_text else None

    # Every quote offered as evidence must exist in the source text: a model can
    # invent a plausible excerpt, but it can't make it appear in the PDF.
    if src is not None:
        missing = [q for q in (record.get("source_excerpt_citations") or []) if q and not quote_in_source(q, src)]
        if missing:
            flag("source_excerpt_citations",
                 f"{len(missing)} quoted excerpt(s) could not be found in the circular text — possible fabrication: "
                 + "; ".join(repr(m[:80]) for m in missing[:2]))

    clean_dates = []
    for kd in record.get("key_dates") or []:
        if not isinstance(kd, dict):
            continue
        date, quote = kd.get("date"), kd.get("quote")
        if date in (None, "", "NOT STATED IN SOURCE"):
            continue                      # nothing asserted, nothing to check
        if not (isinstance(date, str) and ISO_DATE_RE.match(date)):
            flag("key_dates", f"A key date was not in YYYY-MM-DD form: {date!r}.")
            continue
        if src is not None and (not quote or not quote_in_source(quote, src)):
            flag("key_dates", f"The quote supporting key date {date} was not found in the circular text.")
            kd["unverified"] = True
        clean_dates.append(kd)
    record["key_dates"] = clean_dates

    # Cross-regulator links are only as good as the number they cite.
    kept = []
    for im in record.get("implements") or []:
        no = (im or {}).get("circular_no") if isinstance(im, dict) else None
        if not no or no == "NOT STATED IN SOURCE":
            continue
        if src is not None and _letters(no) not in src:
            flag("implements", f"Cited circular number {no!r} was not found in the document text.")
            continue
        kept.append(im)
    record["implements"] = kept

    circ_no = record.get("circular_no")
    if circ_no and circ_no != "NOT STATED IN SOURCE":
        if not CIRCULAR_NO_HINT_RE.search(circ_no):
            flag("circular_no", f"{circ_no!r} doesn't look like a circular reference number — verify manually.")
        elif src is not None and _letters(circ_no) not in src:
            flag("circular_no", f"Circular number {circ_no!r} was not found in the document text.")

    parent_no = record.get("parent_circular_no")
    if parent_no and parent_no != "NOT STATED IN SOURCE":
        # The model sometimes lists several parents in one field ("A, B and C dated ...").
        # Check each reference-looking part; ignore joining words and dates.
        parts = [p.strip() for p in re.split(r",|;|\band\b|\bdated\b", parent_no)]
        refs = [p for p in parts if CIRCULAR_NO_HINT_RE.search(p) and "/" in p] or [parent_no]
        missing_refs = [p for p in refs if src is not None and _letters(p) not in src]
        if missing_refs:
            flag("parent_circular_no", f"Parent circular number(s) not found in the document text: {', '.join(missing_refs)[:160]}.")
        elif known_circular_numbers is not None and not any(p in known_circular_numbers for p in refs):
            flag("parent_circular_no",
                 "The parent circular is cited in the text but isn't in this register yet (it may predate the "
                 "tracker), so the link can't be followed here.", level="Inferred")

    doc_type = record.get("doc_type")
    valid_types = {"Fresh Circular", "Amendment", "Addendum", "Corrigendum", "Master Circular", "FAQ/Clarification"}
    if doc_type not in valid_types:
        flag("doc_type", f"Model returned an unrecognized doc_type value: {doc_type!r}.")

    if doc_type in {"Amendment", "Addendum", "Corrigendum"} and not parent_no:
        flag("parent_circular_no", f"doc_type is {doc_type!r} but no parent circular was identified — inconsistent, needs a human look.")

    record["confidence_flags"] = flags
    record["overall_confidence"] = worst
    record["validator_version"] = VALIDATOR_VERSION
    return record


def response_text(message):
    """Joins the reply's text blocks. A reply can open with a thinking block (and
    may contain other block types); only text blocks carry the answer."""
    return "".join(getattr(b, "text", "") for b in (message.content or [])
                   if getattr(b, "type", "text") == "text").strip()


def parse_json_object(raw):
    """Parses the JSON answer, tolerating code fences or a stray sentence around it."""
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    for candidate in (raw, raw[raw.find("{"):raw.rfind("}") + 1] if "{" in raw else ""):
        if not candidate:
            continue
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


def classify_circular(source_text, source_url, known_circular_numbers=None, client=None, regulator="SEBI", feedback=None):
    """Returns a dict matching data/circulars.json's record schema, with
    validation checks applied on top of the model's own output."""
    # New API accounts have low per-minute limits; the SDK waits and retries on 429s.
    client = client or Anthropic(max_retries=8)

    truncated = source_text[:60000]  # keep prompts bounded; SEBI circulars are short relative to this
    message = client.messages.create(
        model=MODEL,
        # Thinking, when the model uses it, counts toward this limit, so leave ample room
        # for the JSON answer after it.
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"ISSUED BY: {regulator}\n\nSOURCE TEXT:\n\n{truncated}" + (
            "\n\nA PREVIOUS ATTEMPT ON THIS DOCUMENT FAILED THESE AUTOMATED CHECKS:\n" + feedback +
            "\nFix them. Copy every quote character for character from the source text above, without "
            "shortening or joining sentences. If a value can't be confirmed from the text, use "
            "\"NOT STATED IN SOURCE\" rather than guessing." if feedback else "")}],
    )
    if getattr(message, "stop_reason", None) == "max_tokens":
        raise ValueError("The model's answer was cut off by the length limit; will retry next run.")
    raw = response_text(message)
    record = parse_json_object(raw)
    if record is None:
        # Don't store a placeholder: an unreadable answer is retried next run, and the
        # reason is recorded in last_run so it can be investigated.
        raise ValueError(f"The model's answer wasn't valid JSON: {raw[:160]!r}")

    record = _validate(record, known_circular_numbers, source_text=source_text)  # check against the WHOLE document
    record["source_url"] = source_url
    record["sample_data"] = False
    return record


if __name__ == "__main__":
    text = sys.stdin.read()
    result = classify_circular(text, source_url="stdin")
    print(json.dumps(result, indent=2, ensure_ascii=False))
