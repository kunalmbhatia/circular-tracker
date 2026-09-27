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


CIRCULAR_NO_HINT_RE = re.compile(r"[A-Z]{2,}.*\d{4}.*\d")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _norm_ws(s):
    """Collapse whitespace and unify quote/dash characters so a verbatim quote
    still matches text extracted from a PDF (line breaks, curly quotes)."""
    s = (s or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip().lower()


def _validate(record, known_circular_numbers, source_text=None):
    """Layer deterministic checks on top of the model's own confidence flags.
    Mutates and returns record. Never removes a Needs Review flag the model set."""
    flags = dict(record.get("confidence_flags") or {})
    worst = record.get("overall_confidence", "Needs Review")

    def downgrade(reason_key, reason):
        nonlocal worst
        flags[reason_key] = reason
        worst = "Needs Review"

    # Every quote the model offers as evidence must exist in the source text.
    # This is the strongest anti-fabrication check available: a model can
    # invent a plausible-sounding excerpt, but it can't make it appear in the PDF.
    if source_text:
        haystack = _norm_ws(source_text)
        missing = [q for q in (record.get("source_excerpt_citations") or []) if q and _norm_ws(q) not in haystack]
        if missing:
            downgrade("source_excerpt_citations",
                      f"{len(missing)} quoted excerpt(s) could not be found in the circular text — possible fabrication.")

    clean_dates = []
    for kd in record.get("key_dates") or []:
        if not isinstance(kd, dict):
            continue
        date, quote = kd.get("date"), kd.get("quote")
        if not (isinstance(date, str) and ISO_DATE_RE.match(date)):
            downgrade("key_dates", f"A key date was not in YYYY-MM-DD form: {date!r}.")
            continue
        if source_text and (not quote or _norm_ws(quote) not in _norm_ws(source_text)):
            downgrade("key_dates", f"The quote supporting key date {date} was not found in the circular text.")
            kd["unverified"] = True
        clean_dates.append(kd)
    record["key_dates"] = clean_dates

    # Cross-regulator links are only as good as the number they cite: it must
    # appear in this document's own text.
    kept = []
    for im in record.get("implements") or []:
        no = (im or {}).get("circular_no") if isinstance(im, dict) else None
        if not no or no == "NOT STATED IN SOURCE":
            continue
        if source_text and _norm_ws(no) not in _norm_ws(source_text):
            downgrade("implements", f"Cited circular number {no!r} was not found in the document text.")
            continue
        kept.append(im)
    record["implements"] = kept

    circ_no = record.get("circular_no")
    if circ_no and circ_no != "NOT STATED IN SOURCE" and not CIRCULAR_NO_HINT_RE.search(circ_no):
        downgrade("circular_no", "Extracted value doesn't look like a SEBI circular number format — verify manually.")

    parent_no = record.get("parent_circular_no")
    if parent_no and parent_no not in (None, "NOT STATED IN SOURCE") and known_circular_numbers is not None:
        if parent_no not in known_circular_numbers:
            downgrade(
                "parent_circular_no",
                "Parent circular number not found in this tracker's existing dataset — it may predate this "
                "tracker, or the number may be mistyped. Verify against the source before treating the mapping as confirmed.",
            )

    doc_type = record.get("doc_type")
    valid_types = {"Fresh Circular", "Amendment", "Addendum", "Corrigendum", "Master Circular", "FAQ/Clarification"}
    if doc_type not in valid_types:
        downgrade("doc_type", f"Model returned an unrecognized doc_type value: {doc_type!r}.")

    if doc_type in {"Amendment", "Addendum", "Corrigendum"} and not parent_no:
        downgrade("parent_circular_no", f"doc_type is {doc_type!r} but no parent circular was identified — inconsistent, needs a human look.")

    record["confidence_flags"] = flags
    record["overall_confidence"] = worst
    return record


def classify_circular(source_text, source_url, known_circular_numbers=None, client=None, regulator="SEBI"):
    """Returns a dict matching data/circulars.json's record schema, with
    validation checks applied on top of the model's own output."""
    client = client or Anthropic()

    truncated = source_text[:60000]  # keep prompts bounded; SEBI circulars are short relative to this
    message = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"ISSUED BY: {regulator}\n\nSOURCE TEXT:\n\n{truncated}"}],
    )
    raw = message.content[0].text.strip()
    # Model is instructed to return bare JSON; strip fences defensively if it doesn't.
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())

    try:
        record = json.loads(raw)
    except json.JSONDecodeError as e:
        return {
            "circular_no": "NOT STATED IN SOURCE",
            "date": None,
            "doc_type": "Fresh Circular",
            "parent_circular_no": None,
            "parent_circular_date": None,
            "impact_areas": [],
            "applicability": "Not resolved",
            "intent": "Classifier output could not be parsed as JSON — needs manual review.",
            "action_required": None,
            "effective_date": None,
            "impact_summary": f"JSON parse error: {e}",
            "overall_confidence": "Needs Review",
            "confidence_flags": {"all_fields": "Classifier response was not valid JSON; raw output discarded."},
            "source_excerpt_citations": [],
            "source_url": source_url,
            "sample_data": False,
        }

    record = _validate(record, known_circular_numbers, source_text=truncated)
    record["source_url"] = source_url
    record["sample_data"] = False
    return record


if __name__ == "__main__":
    text = sys.stdin.read()
    result = classify_circular(text, source_url="stdin")
    print(json.dumps(result, indent=2, ensure_ascii=False))
