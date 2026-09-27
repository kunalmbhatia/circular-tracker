"""
extract_text.py — given a SEBI circular's detail-page URL, fetch the full
text of the circular (from its attached PDF if there is one, else from the
HTML page body) so the classifier prompt has real source text to work from.

Same caveat as scrape_sebi.py: written defensively from general knowledge of
how SEBI publishes circulars (an HTML landing page with an attached PDF),
not verified against a live fetch from this environment. If PDF extraction
comes back empty, fall back to the HTML body text before giving up.
"""

import io
import re
import sys
from urllib.parse import urljoin

import requests
import pdfplumber
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CircularTracker/2.0 (open-source regulatory circular tracker))"
}


def _extract_pdf_text(pdf_bytes):
    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            text_parts.append(t)
    return "\n".join(text_parts).strip()


def _extract_html_body_text(html, base_url):
    soup = BeautifulSoup(html, "lxml")
    # Drop obvious chrome so it doesn't pollute the extracted text.
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    # Prefer a main-content-looking container if one exists; else the whole body.
    main = soup.find(["main", "article"]) or soup.find(id=re.compile("content", re.I)) or soup.body or soup
    text = main.get_text("\n", strip=True) if main else soup.get_text("\n", strip=True)
    return text


def _text_from_zip(blob):
    """Exchange circulars often ship as a ZIP holding the PDF plus annexures.
    The main circular is usually the first PDF; annexure text is appended so
    deadlines stated in annexures are not lost."""
    import zipfile
    parts = []
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        pdfs = sorted([n for n in zf.namelist() if n.lower().endswith(".pdf")], key=lambda n: ("annex" in n.lower(), n))
        for name in pdfs[:4]:
            try:
                parts.append(_extract_pdf_text(zf.read(name)))
            except Exception as e:
                print(f"[extract_text] WARNING: unreadable PDF {name} in ZIP: {e}", file=sys.stderr)
    return "\n\n".join(p for p in parts if p).strip()


def fetch_circular_text(detail_url, session=None):
    """Returns (text, pdf_url_or_none). Raises requests.RequestException on network failure."""
    session = session or requests.Session()
    resp = session.get(detail_url, headers=HEADERS, timeout=60)
    resp.raise_for_status()

    # Exchanges and depositories link straight to the document, not to a web page.
    path = detail_url.lower().split("?")[0]
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if path.endswith(".pdf") or "application/pdf" in ctype:
        return _extract_pdf_text(resp.content), detail_url
    if path.endswith(".zip") or "zip" in ctype:
        return _text_from_zip(resp.content), detail_url

    html = resp.text

    soup = BeautifulSoup(html, "lxml")
    pdf_link = None
    for a in soup.find_all("a", href=True):
        if a["href"].lower().endswith(".pdf"):
            pdf_link = urljoin(detail_url, a["href"])
            break

    if pdf_link:
        try:
            pdf_resp = session.get(pdf_link, headers=HEADERS, timeout=60)
            pdf_resp.raise_for_status()
            pdf_text = _extract_pdf_text(pdf_resp.content)
            if pdf_text and len(pdf_text) > 200:
                return pdf_text, pdf_link
            print(f"[extract_text] PDF at {pdf_link} yielded little/no text, falling back to HTML", file=sys.stderr)
        except (requests.RequestException, Exception) as e:
            print(f"[extract_text] WARNING: could not extract PDF ({pdf_link}): {e}", file=sys.stderr)

    return _extract_html_body_text(html, detail_url), pdf_link
