# Circular Tracker

An open-source register of every circular that changes how India's broking
and fintech ecosystem operates. It covers SEBI, RBI, NSE, BSE, NSE Clearing,
NSDL, CDSL, NCDEX, IFSCA and NPCI, with MCX listed but not yet connected.
Each circular is classified by type and linked to the circular it changes.
Exchange and depository circulars are also linked to the SEBI or RBI circular
they implement. Each is tagged by who it affects and traced from issue to
deadline, on a dashboard any broker, compliance team, fintech, regulator or
investor can use for free.

**Dashboard:** `index.html`, a single file with no build step. It has
filters with live counts (including by issuing body), an issuance chart you
can click to filter, upcoming compliance dates, and a detail panel showing
each circular's lifecycle, lineage and verification evidence. It also has ⌘K
search, keyboard navigation, shareable links, and Excel, CSV and PDF export,
plus two audit views: **Sources** (the health of every feed and page, from the
freshness pill) and **Set aside** (every routine notice the filter screened
out, with the reason).

`web/` is an earlier React prototype with the old design and SEBI-only data.
It's superseded. Delete it (and simplify `.github/workflows/deploy.yml`)
unless you plan to develop it further.

**Pipeline:** `scraper/`
- `sources.py`: the registry of every source, how it's read, and how far
  its parser has been verified. Respects robots.txt.
- `triage.py`: screens titles from mixed feeds and sets routine notices aside.
- `classify.py`: extracts structure from each circular's full text, with
  deterministic validation.
- `main.py`: runs it all every 2 hours via GitHub Actions.

---

## Before you rely on this: read this section

This project is built to be honest about what it can and can't guarantee,
not to promise numbers nobody can actually deliver:

- **No LLM-based classification can hit 100% accuracy unsupervised.** This
  pipeline is designed to *fail visibly instead of silently* — every field
  the model isn't sure about gets a `Needs Review` flag rather than being
  published as settled fact. Treat the dashboard as a triage and tracking
  tool, not a substitute for reading the source circular before you act on it.
- **Source coverage is uneven, and the dashboard says so.** SEBI, RBI and
  NSE publish RSS feeds whose format was checked against the live feeds on
  27 Sep 2026. BSE's feed address is confirmed, but BSE refused a direct test
  fetch, so it may block automated access. NSE Clearing, NSDL, CDSL, NCDEX,
  IFSCA and NPCI publish circulars only as web pages. Their parsers were
  written without a live fetch, because the build environment couldn't reach
  those sites. MCX is listed but not connected: its robots.txt disallows
  automated access to its feed page. After the first real run, open
  **Sources** on the dashboard to see which work. A page that loads but
  yields no circulars is flagged "Page changed" so you know its parser needs
  updating.
- **Feeds are short.** NSE's feed holds about one day of circulars and SEBI's
  about five days, which is why the pipeline runs every 2 hours. GitHub can
  delay or skip scheduled runs under load. SEBI has listing pages as a
  backstop; the other feeds don't.
- **Routine notices are filtered, visibly.** The exchanges publish dozens of
  notices a day, mostly company- or scheme-specific. A small, cheap model
  screens titles first. It's told to keep anything it's unsure about, a
  keyword rule overrides it for titles naming core obligations (brokers,
  KYC, margins, cyber and so on), and every item it sets aside is listed on
  the dashboard with the reason, so the filter can be audited.
- **"Continuous" means GitHub Actions runs it on a schedule — it does not
  mean a guaranteed-uptime service.** The dashboard itself (static files on
  GitHub Pages) is very reliable in practice. The daily pipeline run can
  occasionally fail (SEBI's site is briefly down, the API has a bad day) —
  when that happens the dashboard just shows slightly stale data with an
  amber/red "last updated" indicator, rather than breaking.

---

## What you need to finish setup

1. **A GitHub account and a new repository** (public, if you want this to
   actually be open source others can see and fork).
2. **An Anthropic API key** — from [console.anthropic.com](https://console.anthropic.com).
   At SEBI's actual circular volume (roughly 150–300 a year, i.e. usually 0–3
   new items a day), classification cost is a few dollars a month at most.
3. **10 minutes** to click through the steps below.

---

## Setup

### 1. Push this repo to GitHub

```bash
cd sebi-circular-tracker
git init
git add .
git commit -m "Initial commit: Circular Tracker"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

### 2. Add your Anthropic API key as a secret

In your repo on GitHub: **Settings → Secrets and variables → Actions → New
repository secret**
- Name: `ANTHROPIC_API_KEY`
- Value: your key from the Anthropic Console

### 3. Enable GitHub Pages

**Settings → Pages → Source → GitHub Actions** (not "Deploy from a branch" —
the combined deploy needs a build step for the `web/` app, run by
`.github/workflows/deploy.yml`). GitHub will give you a URL like
`https://<your-username>.github.io/<your-repo>/` for the zero-build dashboard,
and `.../app/` for the React one. The first push to `main` kicks off that
workflow; it's serving seed/demo data until step 4 runs.

### 4. Run the pipeline for the first time

**Actions tab → "Update circular data" → Run workflow** (this is the
`workflow_dispatch` trigger — no need to wait for the daily schedule).
Check the run's logs. If it finds and classifies new circulars, `data/circulars.json`
gets committed automatically and your Pages site updates within a minute or two.
Then open **Sources** on the dashboard (select the freshness pill) to see which sources answered.

After this, it runs automatically every 2 hours — edit
the `cron:` line in `.github/workflows/update.yml` to change that.

---

## Running it locally (to test before pushing)

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...
python scraper/main.py          # scrapes, classifies, updates data/circulars.json
python -m http.server 8000      # then open http://localhost:8000
```

Opening `index.html` directly by double-clicking it (a `file://` URL) will
show an error — browsers block `fetch()` on local files for security reasons.
Always view it through a local server (as above) or via GitHub Pages.

To run the React version locally:

```bash
cd web
npm install
npm run dev              # opens on localhost with hot reload
```

`web/public/data/circulars.json` is a copy for local dev convenience — it's
shadowed by the real `data/circulars.json` in the actual deployment (the
build workflow copies the repo-root data file over it), so don't worry about
keeping the two in sync; just re-copy it locally if you want fresh data while
developing: `cp data/circulars.json web/public/data/circulars.json`.

---

## Running costs

Hosting is free: GitHub Pages serves the files, and GitHub Actions runs the
pipeline (free for public repositories). The paid part is the Claude API:

- **Screening titles:** about 60–100 exchange, RBI and depository titles a
  day, in batches of 40, on a small model. Cents a month.
- **Full classification:** only for circulars that pass screening. Estimated
  at tens to a few hundred a month across all bodies. [Estimate: depends on
  how much the filter lets through]

Expect roughly **$10–40 a month** in API cost. Set a monthly spend limit in
the Anthropic Console so a surge (or a filter that lets too much through)
can't surprise you. Change models with the `ANTHROPIC_MODEL` and
`TRIAGE_MODEL` environment variables.

---

## How the validation actually works

Nothing here claims 99.99% accuracy. Instead, every record carries an
`overall_confidence` of `Certain`, `Inferred`, or `Needs Review`, produced by
two layers:

1. **The model's own self-report** — it's instructed to say "NOT STATED IN
   SOURCE" rather than recall a circular number from training data, and to
   cite short verbatim excerpts supporting anything non-obvious.
2. **Deterministic checks on top** (`scraper/classify.py::_validate`) that
   don't take the model's confidence claim at face value:
   - **Every quote must exist in the circular.** Each excerpt the model cites,
     and the sentence behind each key date it extracts, is matched against
     the circular's own text. A quote that isn't there means the model made
     it up, and the record is downgraded.
   - Does the extracted circular number look like a real SEBI numbering
     format?
   - If it says "Amendment/Addendum/Corrigendum," did it actually find a
     parent circular?
   - Is that parent circular number one this tracker has actually seen
     before? (If not: flagged, not silently accepted — it may predate the
     tracker, or be mistyped.)
   - Are extracted dates real calendar dates? Dates the circular only implies
     ("within 30 days") are never turned into calendar dates.

Anything that fails a check gets downgraded to `Needs Review`, full stop —
the dashboard shows it with a red "Needs Review" badge and it's included in
the "Needs review" count in the stat tiles, so a human always knows what to
double-check.

---

## Customizing

- **Market segments / applicability taxonomy**: edit the `impact_areas` list
  in `scraper/classify.py`'s `SYSTEM_PROMPT`, and the corresponding chip list
  will pick up new values automatically in `index.html` (it's derived from
  the data, not hardcoded).
- **Add or change a source**: add an entry to `SOURCES` in
  `scraper/sources.py`. For a listing page, set `link_filter` to a pattern
  that matches its circular links.
- **What counts as routine**: edit `PROMPT` and `ALWAYS_KEEP` in
  `scraper/triage.py`.
- **Refresh frequency**: edit the `cron:` line in `.github/workflows/update.yml`.
- **Classifier model**: set the `ANTHROPIC_MODEL` env var / GitHub Actions
  secret if you want to swap models — check
  [docs.claude.com](https://docs.claude.com) for the current list before
  assuming a given model string still exists.
- **Dashboard branding**: `index.html`'s colour tokens are CSS variables at
  the top of the `<style>` block. The React app's are in
  `web/src/index.css`'s `@theme` block — same values, same names, kept in
  sync by hand since there's no shared design-token file (a reasonable thing
  to add if this repo grows).

---

## License

MIT — do whatever you want with it, including forking it for your own
brokerage's internal compliance tracker. No warranty; see the accuracy
section above.

## Tests

`python tests/test_pipeline.py` runs the whole pipeline against fake copies
of every source, with no network or API calls. It covers parsing, robots.txt,
de-duplication, the filter's keyword safeguard, and the rule that an idle run
writes nothing.

## Disclaimer

This tool is not affiliated with or endorsed by SEBI, RBI, any exchange,
clearing corporation, depository, NPCI or IFSCA. It is not legal or
compliance advice. It is an aid for tracking and triaging circulars, not a replacement for reading the original circular
or consulting your compliance/legal team before acting on any regulatory
change.
