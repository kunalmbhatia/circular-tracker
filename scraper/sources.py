"""
sources.py — every regulator and market body the tracker reads, and how.

Each source is one entry in SOURCES. Three kinds exist:

  rss           Structured feed. Preferred: it changes shape far less often
                than a web page does.
  sebi_listing  SEBI's circular listing pages (see scrape_sebi.py). Catches
                anything that scrolled off SEBI's short RSS feed.
  page          A listing web page read by a generic parser: it keeps links
                that match `link_filter` and takes the date from the same row.
  none          Listed for transparency, not fetched (see `note`).

`triage` marks sources that mix routine notices (new listings, scheme
launches, company-specific actions) with circulars that change how brokers
and fintechs operate. Their items go through triage.py first.

`verified` states honestly how far each parser has been checked. Page
parsers for the depositories, NCDEX, NSE Clearing, IFSCA and NPCI were
written without a live fetch, because the build environment couldn't
reach those sites. The first real run's source health report (shown on the
dashboard) tells you which ones need adjusting.

Every fetch checks the site's robots.txt first and skips anything the site
disallows. A public tool used by regulators shouldn't scrape against a
site's stated wishes.
"""

import re
import sys
import datetime
import xml.etree.ElementTree as ET
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "CircularTracker/2.0 (open-source regulatory circular tracker)"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/rss+xml, application/xml;q=0.9, text/html;q=0.8, */*;q=0.5",
}

REGULATORS = {
    "SEBI": "Securities and Exchange Board of India",
    "RBI": "Reserve Bank of India",
    "NSE": "National Stock Exchange of India",
    "BSE": "BSE Limited",
    "NSE Clearing": "NSE Clearing Limited",
    "NSDL": "National Securities Depository Limited",
    "CDSL": "Central Depository Services (India) Limited",
    "NCDEX": "National Commodity & Derivatives Exchange",
    "MCX": "Multi Commodity Exchange of India",
    "IFSCA": "International Financial Services Centres Authority",
    "NPCI": "National Payments Corporation of India",
}

CHECKED = "Feed format checked against the live feed on 27 Sep 2026."
UNTESTED_PAGE = "Page parser written without a live fetch. Check the first run's result."

SOURCES = [
    {"id": "sebi-rss", "regulator": "SEBI", "name": "SEBI RSS feed", "kind": "rss",
     "url": "https://www.sebi.gov.in/sebirss.xml", "link_filter": r"/legal/(master-)?circulars/",
     "triage": False, "verified": CHECKED,
     "note": "Holds about five days of items, mixed with orders and press releases. Only circulars are kept."},
    {"id": "sebi-circulars", "regulator": "SEBI", "name": "SEBI circulars listing", "kind": "sebi_listing",
     "url": "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=7&smid=0",
     "category": "Circular", "triage": False, "verified": UNTESTED_PAGE,
     "note": "Backstop for circulars that scroll off the RSS feed."},
    {"id": "sebi-master", "regulator": "SEBI", "name": "SEBI master circulars listing", "kind": "sebi_listing",
     "url": "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=6",
     "category": "Master Circular", "triage": False, "verified": UNTESTED_PAGE, "note": ""},
    {"id": "rbi", "regulator": "RBI", "name": "RBI notifications feed", "kind": "rss",
     "url": "https://rbi.org.in/notifications_rss.xml", "triage": True, "verified": CHECKED,
     "note": "Includes bank-only prudential rules and foreign-exchange regulations. Triage keeps the ones that affect brokers and fintechs."},
    {"id": "nse", "regulator": "NSE", "name": "NSE circulars feed", "kind": "rss",
     "url": "https://nsearchives.nseindia.com/content/RSS/Circulars.xml", "triage": True, "verified": CHECKED,
     "note": "Carries about one day of circulars (around 30 a day, mostly routine), so it's checked every 2 hours."},
    {"id": "bse", "regulator": "BSE", "name": "BSE notices feed", "kind": "rss",
     "url": "https://www.bseindia.com/data/xml/notices.xml", "triage": True,
     "verified": "Feed address confirmed through a third-party reader. BSE refused a direct test fetch (HTTP 403), so it may block automated access.",
     "note": "Dominated by mutual fund platform notices."},
    {"id": "nse-clearing", "regulator": "NSE Clearing", "name": "NSE Clearing circulars", "kind": "page",
     "url": "https://www.nseclearing.in/resources/circulars", "link_filter": r"\.(pdf|zip)(\?|$)",
     "triage": True, "verified": UNTESTED_PAGE, "note": ""},
    {"id": "nsdl", "regulator": "NSDL", "name": "NSDL circulars to participants", "kind": "page",
     "url": "https://nsdl.co.in/business/circular.php", "link_filter": r"\.pdf(\?|$)",
     "triage": True, "verified": UNTESTED_PAGE, "note": ""},
    {"id": "cdsl", "regulator": "CDSL", "name": "CDSL communiqués to DPs", "kind": "page",
     "url": "https://www.cdslindia.com/Publications/Communique.aspx/DP-COMMUNIQUES-INDEX.aspx",
     "link_filter": r"/Communique/.+\.pdf", "triage": True, "verified": UNTESTED_PAGE, "note": ""},
    {"id": "ncdex", "regulator": "NCDEX", "name": "NCDEX circulars", "kind": "page",
     "url": "https://www.ncdex.com/Circulars/CircularHome.aspx", "link_filter": r"\.pdf(\?|$)",
     "triage": True, "verified": UNTESTED_PAGE, "note": ""},
    {"id": "ifsca", "regulator": "IFSCA", "name": "IFSCA legal framework", "kind": "page",
     "url": "https://ifsca.gov.in/Legal/Index/ogGPf3wx5GE=", "link_filter": r"(/Document/Legal/.+\.pdf|ViewFile)",
     "triage": True, "verified": UNTESTED_PAGE,
     "note": "Relevant to brokers and fintechs operating in GIFT City."},
    {"id": "npci", "regulator": "NPCI", "name": "NPCI UPI circulars", "kind": "page",
     "url": "https://www.npci.org.in/circulars/upi", "link_filter": r"\.pdf(\?|$)",
     "triage": True, "verified": UNTESTED_PAGE, "note": "UPI operating circulars for payment apps and PSPs."},
    {"id": "mcx", "regulator": "MCX", "name": "MCX circulars", "kind": "none", "url": "https://www.mcxindia.com/",
     "triage": True, "verified": "",
     "note": "Not connected. MCX's robots.txt disallows automated access to its RSS page. Connect it once a permitted source is confirmed."},
]
SOURCE_BY_ID = {s["id"]: s for s in SOURCES}


# ---------------------------------------------------------------- robots.txt
_robots = {}


def allowed(url, session=None):
    """True if the site's robots.txt lets this tool fetch `url`."""
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    rp = _robots.get(base)
    if rp is None:
        rp = robotparser.RobotFileParser()
        try:
            r = (session or requests).get(base + "/robots.txt", headers=HEADERS, timeout=15)
            if r.status_code in (401, 403):
                rp.disallow_all = True
            elif r.status_code >= 400:
                rp.allow_all = True          # no robots.txt: no restrictions stated
            else:
                rp.parse(r.text.splitlines())
        except requests.RequestException:
            rp.allow_all = True              # unreachable: the real fetch will fail and be reported
        _robots[base] = rp
    return rp.can_fetch(USER_AGENT, url)


# ---------------------------------------------------------------- dates
_MON = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_D_MON_Y = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s\-/]+([A-Za-z]{3,9})[\s,\-/]+(\d{4})\b")
_MON_D_Y = re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b")
_DMY_NUM = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b")
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def _mk(y, m, d):
    try:
        return datetime.date(int(y), int(m), int(d)).isoformat()
    except (ValueError, TypeError):
        return None


def parse_date(text):
    """Best-effort date from free text. Numeric dates are read as Indian day/month/year."""
    text = text or ""
    for rx, order in ((_ISO, "ymd"), (_D_MON_Y, "dmy"), (_MON_D_Y, "mdy"), (_DMY_NUM, "dmy_num")):
        for m in rx.finditer(text):
            if order == "ymd":
                out = _mk(*m.groups())
            elif order == "dmy":
                mon = _MON.get(m.group(2)[:3].lower())
                out = mon and _mk(m.group(3), mon, m.group(1))
            elif order == "mdy":
                mon = _MON.get(m.group(1)[:3].lower())
                out = mon and _mk(m.group(3), mon, m.group(2))
            else:
                out = _mk(m.group(3), m.group(2), m.group(1))
            if out:
                return out
    return None


# ---------------------------------------------------------------- parsers
def _local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _clean(s):
    return " ".join((s or "").split())


def parse_rss(content, src):
    """RSS 2.0 or Atom. Falls back to a lenient parser for slightly broken XML."""
    entries = []
    try:
        root = ET.fromstring(content if isinstance(content, bytes) else content.encode("utf-8"))
        for node in root.iter():
            if _local(node.tag) not in ("item", "entry"):
                continue
            f = {}
            for ch in node:
                name = _local(ch.tag)
                if name == "link" and ch.get("href"):
                    f.setdefault("link", ch.get("href"))
                elif ch.text and name not in f:
                    f[name] = ch.text
            entries.append(f)
    except ET.ParseError:
        soup = BeautifulSoup(content, "xml")
        for node in soup.find_all(["item", "entry"]):
            link = node.find("link")
            entries.append({
                "title": node.title.get_text() if node.title else "",
                "link": (link.get("href") or link.get_text()) if link else "",
                "pubdate": (node.find("pubDate") or node.find("published") or node.find("updated") or node.find("date") or BeautifulSoup("", "xml")).get_text(),
            })
    pat = re.compile(src["link_filter"], re.I) if src.get("link_filter") else None
    out = []
    for e in entries:
        link = _clean(e.get("link"))
        title = _clean(e.get("title"))
        if not link or not title or (pat and not pat.search(link)):
            continue
        out.append({
            "title": title,
            "url": urljoin(src["url"], link),
            "date": parse_date(e.get("pubdate") or e.get("published") or e.get("updated") or e.get("date") or ""),
            "category": "Master Circular" if "master-circular" in link.lower() else "Circular",
            "source": src["id"], "regulator": src["regulator"],
        })
    return out


_GENERIC_LINK_TEXT = {"download", "view", "pdf", "click here", "read more", "details", "open", "english", "hindi", "file"}


def parse_page(html, src):
    """Generic listing page: links matching link_filter, date from the same row."""
    soup = BeautifulSoup(html, "lxml")
    pat = re.compile(src["link_filter"], re.I)
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not pat.search(href):
            continue
        url = urljoin(src["url"], href)
        if url in seen:
            continue
        seen.add(url)
        row = a.find_parent(["tr", "li"]) or a.parent
        row_text = _clean(row.get_text(" ", strip=True)) if row else ""
        title = _clean(a.get_text(" ", strip=True))
        if len(title) < 12 or title.lower() in _GENERIC_LINK_TEXT:
            # The link is an icon or "Download": the subject is elsewhere in the row.
            title = _clean(re.sub(r"\b(download|view|pdf|click here)\b", "", row_text, flags=re.I))
            for rx in (_ISO, _D_MON_Y, _MON_D_Y, _DMY_NUM):
                title = _clean(rx.sub("", title))
        if len(title) < 12:
            continue
        out.append({"title": title[:400], "url": url, "date": parse_date(row_text),
                    "category": "Circular", "source": src["id"], "regulator": src["regulator"]})
    return out


# ---------------------------------------------------------------- fetch
def _now():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_source(src, session):
    """Returns (items, health). Never raises: failures are reported in `health`."""
    health = {k: src.get(k, "") for k in ("id", "regulator", "name", "kind", "url", "verified", "note")}
    health.update({"checked_at": _now(), "items": 0, "status": "ok", "error": ""})
    if src["kind"] == "none":
        health["status"] = "not_connected"
        return [], health
    try:
        if not allowed(src["url"], session):
            health.update(status="blocked", error="The site's robots.txt disallows this address.")
            return [], health
        resp = session.get(src["url"], headers=HEADERS, timeout=40)
        resp.raise_for_status()
        if src["kind"] == "rss":
            items = parse_rss(resp.content, src)
        elif src["kind"] == "sebi_listing":
            from scrape_sebi import _parse_rows
            items = [dict(r, source=src["id"], regulator="SEBI") for r in _parse_rows(resp.text, src["url"], src.get("category", "Circular"))]
        else:
            items = parse_page(resp.text, src)
        health["items"] = len(items)
        if not items and src["kind"] != "rss":
            # A listing page that yields nothing almost always means its layout changed.
            health.update(status="empty", error="Page loaded but no circular links matched. The page layout may have changed.")
        return items, health
    except Exception as e:  # network, HTTP and parse errors alike
        health.update(status="failed", error=f"{type(e).__name__}: {str(e)[:200]}")
        return [], health


def collect_all(source_ids=None):
    """Fetch every configured source. Returns (items de-duplicated by URL, health list)."""
    session = requests.Session()
    items, health, seen = [], [], set()
    for src in SOURCES:
        if source_ids and src["id"] not in source_ids:
            continue
        got, h = fetch_source(src, session)
        health.append(h)
        print(f"[sources] {src['id']:<14} {h['status']:<13} {h['items']:>4} item(s) {h['error']}", file=sys.stderr)
        for it in got:
            if it["url"] not in seen:
                seen.add(it["url"])
                items.append(it)
    return items, health
