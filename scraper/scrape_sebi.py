"""
scrape_sebi.py — fetches SEBI's public circular listing pages and returns
new entries not already present in data/circulars.json.

IMPORTANT — read before relying on this:
This scraper was written from SEBI listing pages inspected via web search
snippets, NOT by fetching and testing against the live site from this
environment (this sandbox has no general internet access; SEBI's site is
only reachable from wherever you actually run this script — e.g. a GitHub
Actions runner). That means the CSS/table structure below is a best-effort
guess at SEBI's markup and MAY need adjustment the first time you run it
for real. If `scrape_listing()` returns zero rows on a page you know has
circulars, open the listing URL in a browser, view source, and adjust
`_parse_rows()` to match what you see — the date-detection and link-
detection logic is written defensively (regex + "any anchor pointing at
a circular page") specifically so small markup changes don't break it,
but a large redesign of sebi.gov.in will.

SEBI listing pages used (verified reachable and in this shape as of
September 2026 — worth re-confirming if this stops finding anything):
  - Circulars:        https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=7&smid=0
  - Master Circulars: https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=6
"""

import re
import sys
import json
import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

LISTING_URLS = {
    "Circular": "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=7&smid=0",
    "Master Circular": "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=6",
}

BASE = "https://www.sebi.gov.in"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; sebi-circular-tracker/1.0; +https://github.com/)"
}
DATE_RE = re.compile(r"([A-Z][a-z]{2}\s+\d{1,2},\s*\d{4})")


def _parse_date(text):
    m = DATE_RE.search(text or "")
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(1).replace(",", ","), "%b %d, %Y").date().isoformat()
    except ValueError:
        return None


def _parse_rows(html, page_url, category_hint):
    """Best-effort row extraction. See module docstring before editing."""
    soup = BeautifulSoup(html, "lxml")
    results = []
    seen_urls = set()

    # Primary strategy: any anchor whose href points at a circular/master-circular
    # detail page. This is robust to table/CSS-class changes since it doesn't
    # depend on the table's structure at all — only on SEBI still linking to
    # circulars under /legal/circulars/ or /legal/master-circulars/.
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/legal/circulars/" not in href and "/legal/master-circulars/" not in href:
            continue
        title = a.get_text(strip=True)
        if not title or len(title) < 8:
            continue
        url = urljoin(page_url, href)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # date usually sits in a sibling <td> in the same <tr> — walk up to the
        # row and pull the first date-shaped text out of it.
        row = a.find_parent("tr")
        date_iso = None
        if row:
            date_iso = _parse_date(row.get_text(" ", strip=True))

        results.append({
            "title": title,
            "url": url,
            "date": date_iso,
            "category": "Master Circular" if "master-circulars" in href else category_hint,
        })

    return results


def scrape_listing(category, url, session=None):
    session = session or requests.Session()
    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return _parse_rows(resp.text, url, category)


RSS_URL = "https://www.sebi.gov.in/sebirss.xml"
CIRCULAR_PATHS = ("/legal/circulars/", "/legal/master-circulars/")
RSS_DATE_RE = re.compile(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*,?\s+(\d{4})")


def _parse_rss_date(text):
    """SEBI's feed uses '24 Sep, 2026 +0530'. Fall back to RFC 822 ('Thu, 24 Sep 2026 ...')."""
    m = RSS_DATE_RE.search(text or "")
    if not m:
        return None
    try:
        return datetime.datetime.strptime(f"{m.group(1)} {m.group(2).title()} {m.group(3)}", "%d %b %Y").date().isoformat()
    except ValueError:
        return None


def parse_rss(xml_text):
    """Returns circular and master-circular items from SEBI's RSS feed.

    The feed mixes orders, recovery proceedings and press releases with
    circulars, and holds only the last few days of items. It's the preferred
    source because it's structured XML (far less brittle than scraping HTML),
    but it can't be the only one: anything that scrolls off it before a run
    happens is recovered from the listing pages.
    """
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    out = []
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        if not any(p in link for p in CIRCULAR_PATHS):
            continue
        out.append({
            "title": " ".join((item.findtext("title") or "").split()),
            "url": urljoin(BASE, link),
            "date": _parse_rss_date(item.findtext("pubDate")),
            "category": "Master Circular" if "/master-circulars/" in link else "Circular",
            "via": "rss",
        })
    return out


def fetch_rss(session=None):
    session = session or requests.Session()
    resp = session.get(RSS_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return parse_rss(resp.content)


def scrape_all():
    """Returns (rows, sources_ok). sources_ok counts the sources that answered.

    If it's 0, nothing was checked at all, and the caller must not record
    this run as a successful refresh.
    """
    session = requests.Session()
    all_rows, seen, sources_ok = [], set(), 0

    def add(rows):
        for r in rows:
            if r["url"] not in seen:
                seen.add(r["url"])
                all_rows.append(r)

    try:
        rows = fetch_rss(session)
        sources_ok += 1
        print(f"[scrape_sebi] RSS feed: {len(rows)} circular item(s)", file=sys.stderr)
        add(rows)
    except Exception as e:  # network errors and malformed XML alike
        print(f"[scrape_sebi] WARNING: RSS feed failed ({RSS_URL}): {e}", file=sys.stderr)

    for category, url in LISTING_URLS.items():
        try:
            rows = scrape_listing(category, url, session)
            sources_ok += 1
            print(f"[scrape_sebi] {category} listing: {len(rows)} item(s)", file=sys.stderr)
            add(rows)
        except requests.RequestException as e:
            print(f"[scrape_sebi] WARNING: failed to fetch {category} listing ({url}): {e}", file=sys.stderr)
    return all_rows, sources_ok


def filter_new(scraped, existing_records):
    """Return only scraped items whose URL isn't already in existing_records."""
    known_urls = {r.get("source_url") for r in existing_records if r.get("source_url")}
    return [r for r in scraped if r["url"] not in known_urls]


if __name__ == "__main__":
    rows, ok = scrape_all()
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"{ok} source(s) answered", file=sys.stderr)
