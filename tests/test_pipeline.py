"""
End-to-end pipeline tests with every network call and model call faked.

Run:  python -m pytest tests/ -q      (or: python tests/test_pipeline.py)

Fixtures mirror the real feeds as observed on 27 Sep 2026 (RSS field layout,
date formats, the kind of titles each body publishes). They do not prove the
live page parsers work: only a real run can, and its source health report
on the dashboard shows the result.
"""
import os, sys, json, shutil, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scraper"))

import requests
import sources, triage as triage_mod

SEBI_RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Settlement Order in the matter of Adani Group Companies</title><link>https://www.sebi.gov.in/enforcement/orders/sep-2026/x_104647.html</link><pubDate>22 Sep, 2026 +0530</pubDate></item>
<item><title>Framework for trading preferences of retail investors</title><link>https://www.sebi.gov.in/legal/circulars/sep-2026/framework_104800.html</link><pubDate>26 Sep, 2026 +0530</pubDate></item>
</channel></rss>"""
RBI_RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Designation of terrorist organisation under clause (a) of sub-section (1) of section 35 of the Unlawful Activities (Prevention) Act, 1967</title><link>https://www.rbi.org.in/scripts/NotificationUser.aspx?Id=13713&amp;Mode=0</link><pubDate>Thu, 24 Sep 2026 17:15:00</pubDate></item>
<item><title>Exim Bank&amp;#8217;s GOI-supported Line of Credit (LOC) for &amp;#8377; 4,850 crore to the Government of Maldives</title><link>https://www.rbi.org.in/scripts/NotificationUser.aspx?Id=13712&amp;Mode=0</link><pubDate>Wed, 23 Sep 2026 16:55:00</pubDate></item>
</channel></rss>"""
NSE_RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Submission of Associates details by Clearing Members</title><link>https://nsearchives.nseindia.com/content/circulars/CMPL76570.zip</link><pubDate>Fri, 25 Sep 2026 18:10:00 +0530</pubDate></item>
<item><title>Listing of further issues of securities</title><link>https://nsearchives.nseindia.com/content/circulars/CML76569.pdf</link><pubDate>Fri, 25 Sep 2026 17:40:00 +0530</pubDate></item>
<item><title>Face Value Split - BLS E-Services Limited (BLSE)</title><link>https://nsearchives.nseindia.com/content/circulars/CML76548.pdf</link><pubDate>Fri, 25 Sep 2026 16:00:00 +0530</pubDate></item>
</channel></rss>"""
NSDL_PAGE = """<ul class="menu"><li><a href="https://nsdl.com/nsdl/2026-07/Composition%20of%20Board%20Committees.pdf">Composition of Committee <span class="sr">(opens in new tab)</span></a></li></ul>
<table><tr><td>24 September 2026</td><td><a href="/downloadables/pdf/2026-0101-Policy-Revised_procedure_for_KYC.pdf">2026-0101-Policy-Revised procedure for KYC of Beneficial Owners (opens in new tab)</a></td></tr>
<tr><td>22/09/2026</td><td><a href="/downloadables/pdf/2026-0099-Policy-Holiday.pdf">2026-0099-Policy-Holiday on account of Id-e-Milad</a></td></tr></table>"""
SEBI_LIST = """<table><tr><td>Sep 26, 2026</td><td><a href="/legal/circulars/sep-2026/framework_104800.html">Framework for trading preferences of retail investors</a></td></tr></table>"""

ROBOTS = {"www.mcxindia.com": "User-agent: *\nDisallow: /tools/", "www.bseindia.com": "User-agent: *\nDisallow: /"}


class Resp:
    def __init__(self, body, status=200, ctype="text/html"):
        self.content = body if isinstance(body, bytes) else body.encode()
        self.text = self.content.decode("utf-8", "replace")
        self.status_code = status
        self.headers = {"Content-Type": ctype}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def fake_get(url, *a, **kw):
    from urllib.parse import urlparse
    host = urlparse(url).netloc
    if url.endswith("/robots.txt"):
        return Resp(ROBOTS.get(host, ""), 200 if host in ROBOTS else 404)
    table = {sources.SOURCE_BY_ID["sebi-rss"]["url"]: SEBI_RSS, sources.SOURCE_BY_ID["rbi"]["url"]: RBI_RSS,
             sources.SOURCE_BY_ID["nse"]["url"]: NSE_RSS, sources.SOURCE_BY_ID["nsdl"]["url"]: NSDL_PAGE,
             sources.SOURCE_BY_ID["sebi-circulars"]["url"]: SEBI_LIST}
    if url in table:
        return Resp(table[url])
    if "nseclearing" in host or "cdsl" in host or "ncdex" in host or "ifsca" in host or "npci" in host:
        return Resp("<html><body>redesigned page with no links</body></html>")
    if "sebi.gov.in" in host:
        return Resp("<html></html>")
    raise requests.ConnectionError(f"no fixture for {url}")


def install_fakes():
    sources._robots.clear()
    requests.Session.get = lambda self, url, *a, **kw: fake_get(url)
    requests.get = fake_get


class FakeTriageClient:
    """Mimics a model that sets aside obviously routine titles, including one it gets WRONG
    (the NSDL KYC circular) so the keyword override can be tested."""
    def __init__(self):
        self.messages = types.SimpleNamespace(create=self.create)

    def create(self, **kw):
        lines = kw["messages"][0]["content"].splitlines()
        out = []
        for ln in lines:
            i = int(ln.split(".")[0])
            routine = any(w in ln for w in ("Listing of", "Face Value", "Line of Credit", "Holiday", "KYC of Beneficial"))
            out.append({"i": i, "include": not routine, "reason": "Company- or bank-specific" if routine else "Affects members"})
        return types.SimpleNamespace(content=[types.SimpleNamespace(text=json.dumps(out))])


def test_parsers_and_health():
    install_fakes()
    items, health = sources.collect_all()
    by = {h["id"]: h for h in health}
    assert by["sebi-rss"]["status"] == "ok" and by["sebi-rss"]["items"] == 1, by["sebi-rss"]   # order filtered out
    assert by["rbi"]["items"] == 2 and by["nse"]["items"] == 3
    assert by["nsdl"]["items"] == 2
    assert by["bse"]["status"] == "blocked", by["bse"]                                        # robots.txt respected
    assert by["mcx"]["status"] == "not_connected"
    assert by["cdsl"]["status"] == "empty", by["cdsl"]                                        # layout-change detector
    urls = [i["url"] for i in items]
    assert len(urls) == len(set(urls)), "SEBI RSS + listing overlap must be de-duplicated"
    nsdl = [i for i in items if i["regulator"] == "NSDL"]
    assert len(nsdl) == 2, [i["title"] for i in nsdl]                       # undated menu PDF excluded
    assert nsdl[0]["title"] == "2026-0101-Policy-Revised procedure for KYC of Beneficial Owners", nsdl[0]["title"]
    assert nsdl[0]["date"] == "2026-09-24" and nsdl[1]["date"] == "2026-09-22", "dd/mm/yyyy must be read day-first"
    rbi = [i for i in items if i["regulator"] == "RBI"][0]
    assert rbi["date"] == "2026-09-24" and "&Mode=0" in rbi["url"]
    exim = [i for i in items if i["title"].startswith("Exim")][0]
    assert "₹ 4,850" in exim["title"] and "&#" not in exim["title"], exim["title"]   # double-escaped entities decoded
    print("ok  parsers, robots.txt, de-duplication, layout-change detection, Indian dates")


def test_triage_override():
    install_fakes()
    items, _ = sources.collect_all(["nsdl", "nse", "rbi"])
    got = {it["title"]: (inc, why) for it, inc, why in triage_mod.triage(items, client=FakeTriageClient())}
    kyc = [v for k, v in got.items() if "KYC" in k][0]
    assert kyc[0] is True and "keyword rule" in kyc[1], kyc                 # model was wrong; rule saved it
    assert got["Listing of further issues of securities"][0] is False
    uapa = [v for k, v in got.items() if k.startswith("Designation of terrorist")][0]
    assert uapa[0] is True
    print("ok  triage: routine set aside, wrong model call on a KYC circular overridden by keyword rule")


def test_pipeline_end_to_end():
    install_fakes()
    import main as M
    tmp = tempfile.mkdtemp()
    M.DATA_PATH, M.FILTERED_PATH = os.path.join(tmp, "c.json"), os.path.join(tmp, "f.json")
    json.dump({"generated_at": None, "circulars": [{"sample_data": True, "title": "seed"}]}, open(M.DATA_PATH, "w"))
    M.triage = lambda items: triage_mod.triage(items, client=FakeTriageClient())
    M.fetch_circular_text = lambda url: ("Full circular text " * 20, url)
    M.allowed = lambda url: True
    calls = []
    def fake_classify(text, source_url, known_circular_numbers=None, regulator="SEBI"):
        calls.append(regulator)
        return {"circular_no": "NOT STATED IN SOURCE", "date": None, "doc_type": "Fresh Circular",
                "overall_confidence": "Needs Review", "confidence_flags": {}, "source_url": source_url, "validator_version": 2}
    M.classify_circular = fake_classify
    os.environ["ANTHROPIC_API_KEY"] = "test"
    code = None
    try:
        M.main()
    except SystemExit as e:
        code = e.code
    assert code in (None, 0), code
    data, filt = json.load(open(M.DATA_PATH)), json.load(open(M.FILTERED_PATH))
    regs = sorted(r["regulator"] for r in data["circulars"])
    assert not any(r.get("sample_data") for r in data["circulars"]), "seed rows must be replaced on first real run"
    assert regs == ["NSDL", "NSE", "RBI", "SEBI"], regs
    titles = " | ".join(f["title"] for f in filt["items"])
    for want in ("Listing of further issues", "Face Value Split", "Exim Bank", "Holiday on account"):
        assert want in titles, (want, titles)
    assert all(f["reason"] for f in filt["items"])
    assert len(data["sources"]) == len(sources.SOURCES)
    # Second run: nothing new, heartbeat not due -> no write
    mtime = os.path.getmtime(M.DATA_PATH)
    try:
        M.main()
    except SystemExit:
        pass
    assert os.path.getmtime(M.DATA_PATH) == mtime, "an idle run must not rewrite the data"
    shutil.rmtree(tmp)
    print(f"ok  pipeline: {len(regs)} classified ({', '.join(regs)}), {len(filt['items'])} set aside with reasons, idle run makes no write")


def test_sebi_viewer_and_title_only_guard():
    import extract_text as X
    page = """<html><body><h1>Review of Inclusion</h1><iframe src='../../../web/?file=https://www.sebi.gov.in/sebi_data/attachdocs/aug-2026/1786537329546.pdf'></iframe></body></html>"""
    assert X.find_pdf_link(page, "https://www.sebi.gov.in/legal/circulars/aug-2026/x_103521.html") == \
        "https://www.sebi.gov.in/sebi_data/attachdocs/aug-2026/1786537329546.pdf"
    class R:
        def __init__(s, body, ct): s.content = body.encode(); s.text = body; s.headers = {"Content-Type": ct}
        def raise_for_status(s): pass
    class S:
        def get(s, url, **kw): return R("<html><body><h1>Title only</h1><p>Sep 09, 2026</p></body></html>", "text/html")
    try:
        X.fetch_circular_text("https://www.sebi.gov.in/legal/circulars/x.html", session=S())
        raise AssertionError("title-only page must not be classified")
    except X.NoDocumentText as e:
        print("ok  SEBI viewer PDF found; title-only page refused:", str(e)[:70])


def test_rate_limit_and_cap():
    install_fakes()
    import main as M
    tmp = tempfile.mkdtemp()
    M.DATA_PATH, M.FILTERED_PATH = os.path.join(tmp, "c.json"), os.path.join(tmp, "f.json")
    M.triage = lambda items: [(i, True, "keep") for i in items]
    M.fetch_circular_text = lambda url: ("Full circular text " * 20, url)
    M.allowed = lambda url: True
    M.PAUSE_SECONDS = 0
    M.MAX_CLASSIFY = 3
    class RateLimitError(Exception): pass
    calls = []
    def fake_classify(text, source_url, known_circular_numbers=None, regulator="SEBI"):
        calls.append(source_url)
        if len(calls) == 2:
            raise RateLimitError("429")
        return {"circular_no": "NOT STATED IN SOURCE", "doc_type": "Fresh Circular", "overall_confidence": "Needs Review",
                "confidence_flags": {}, "source_url": source_url, "validator_version": 2}
    M.classify_circular = fake_classify
    os.environ["ANTHROPIC_API_KEY"] = "test"
    try:
        M.main()
    except SystemExit as e:
        assert e.code in (None, 0), e.code          # deferrals are not failures
    d = json.load(open(M.DATA_PATH))
    lr = d["last_run"]
    assert len(calls) == 2 and lr["added"] == 1 and lr["failed"] == 0 and lr["deferred"] >= 2, lr
    shutil.rmtree(tmp)
    print(f"ok  cap + rate limit: 1 added, stopped at the limit, {lr['deferred']} deferred to later runs, none counted as failed")


def test_requeue_and_unreadable():
    install_fakes()
    import main as M, extract_text as X
    tmp = tempfile.mkdtemp()
    M.DATA_PATH, M.FILTERED_PATH = os.path.join(tmp, "c.json"), os.path.join(tmp, "f.json")
    old = {"title": "Old SEBI circular", "regulator": "SEBI", "source_url": "https://www.sebi.gov.in/legal/circulars/old_1.html",
           "date": "2026-09-01", "overall_confidence": "Needs Review", "circular_no": "SEBI/HO/OLD/2026/1"}
    json.dump({"generated_at": "2026-09-27T00:00:00Z", "circulars": [old]}, open(M.DATA_PATH, "w"))
    M.triage = lambda items: [(i, True, "keep") for i in items]
    M.allowed = lambda url: True
    M.PAUSE_SECONDS = 0; M.MAX_CLASSIFY = 60
    def fetch(url):
        if "CMPL76570" in url: raise X.NoDocumentText("scanned")
        return ("text " * 400, url)
    M.fetch_circular_text = fetch
    M.classify_circular = lambda text, source_url, known_circular_numbers=None, regulator="SEBI": {
        "circular_no": "X/2026/1", "doc_type": "Fresh Circular", "overall_confidence": "Certain",
        "confidence_flags": {}, "source_url": source_url, "validator_version": 2}
    os.environ["ANTHROPIC_API_KEY"] = "test"
    for _ in range(3):
        try: M.main()
        except SystemExit: pass
    d = json.load(open(M.DATA_PATH))
    olds = [r for r in d["circulars"] if r["source_url"] == old["source_url"]]
    assert len(olds) == 1 and olds[0]["validator_version"] == 2 and olds[0]["title"] == "Old SEBI circular", olds
    scanned = [r for r in d["circulars"] if "CMPL76570" in r["source_url"]]
    assert len(scanned) == 1 and "scanned image" in scanned[0]["confidence_flags"]["all_fields"], scanned
    assert d["last_run"]["failed"] == 0, d["last_run"]
    shutil.rmtree(tmp)
    print("ok  old record re-checked once (not duplicated); unreadable PDF listed after 3 tries and run goes green")


if __name__ == "__main__":
    test_parsers_and_health(); test_triage_override(); test_pipeline_end_to_end()
    test_sebi_viewer_and_title_only_guard(); test_rate_limit_and_cap(); test_requeue_and_unreadable()
    print("ALL PIPELINE TESTS PASS")
