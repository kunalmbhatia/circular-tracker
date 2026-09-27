"""
main.py — the ingestion pipeline, run every 2 hours by GitHub Actions.

  1. Fetch every source in sources.py (RSS feeds first, listing pages as
     backstops), respecting robots.txt, recording each source's health.
  2. Drop anything already in the register or already set aside.
  3. Screen titles from mixed feeds (RBI, exchanges, depositories...) with
     triage.py. Set-aside items go to data/filtered.json with the reason.
  4. Classify each remaining circular from its full text (classify.py),
     with deterministic validation on top.
  5. Save, then fail loudly if anything went wrong.

Honesty rules this file enforces:
  - If no source could be reached at all, nothing is written and the run
    fails. The dashboard's freshness indicator then ages on its own.
  - Items that couldn't be triaged or classified are not recorded, so the
    next run retries them.
  - The data files are rewritten only when something changed, or at least
    every 6 hours as a heartbeat, so git history isn't flooded.

Run locally:  ANTHROPIC_API_KEY=... python scraper/main.py
"""

import os
import sys
import json
import datetime

sys.path.insert(0, os.path.dirname(__file__))
from sources import collect_all, SOURCE_BY_ID, allowed
from extract_text import fetch_circular_text
from classify import classify_circular
from triage import triage

ROOT = os.path.join(os.path.dirname(__file__), "..", "data")
DATA_PATH = os.path.join(ROOT, "circulars.json")
FILTERED_PATH = os.path.join(ROOT, "filtered.json")
HEARTBEAT_HOURS = 6
KEEP_FILTERED_DAYS = 180


def _now():
    return datetime.datetime.utcnow().replace(microsecond=0)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def known_numbers(records):
    return {r["circular_no"] for r in records if r.get("circular_no") and r["circular_no"] != "NOT STATED IN SOURCE"}


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY is not set. Set it as an environment variable "
              "(locally) or a GitHub Actions secret (in CI) before running this.", file=sys.stderr)
        sys.exit(1)

    data = load(DATA_PATH, {"generated_at": None, "schema_version": "2.0", "circulars": []})
    filtered = load(FILTERED_PATH, {"items": []})
    # Sample rows were placeholders; the first real run replaces them.
    records = [r for r in data.get("circulars", []) if not r.get("sample_data")]
    set_aside = [f for f in filtered.get("items", []) if not f.get("sample_data")]
    had_samples = len(records) != len(data.get("circulars", [])) or len(set_aside) != len(filtered.get("items", []))

    items, health = collect_all()
    reached = [h for h in health if h["status"] in ("ok", "empty")]
    if not reached:
        print("[main] ERROR: no source could be reached. Data left unchanged; failing the run.", file=sys.stderr)
        sys.exit(2)

    seen = {r.get("source_url") for r in records} | {f.get("url") for f in set_aside}
    new = [i for i in items if i["url"] not in seen]
    direct = [i for i in new if not SOURCE_BY_ID[i["source"]]["triage"]]
    screen = [i for i in new if SOURCE_BY_ID[i["source"]]["triage"]]
    print(f"[main] {len(items)} item(s) from {len(reached)} source(s); {len(new)} new "
          f"({len(direct)} direct, {len(screen)} to screen)", file=sys.stderr)

    relevant, triage_failed, newly_set_aside = list(direct), 0, 0
    try:
        for item, include, reason in triage(screen):
            if include:
                relevant.append(dict(item, triage_reason=reason))
            else:
                set_aside.append({"title": item["title"], "url": item["url"], "date": item.get("date"),
                                  "regulator": item["regulator"], "source": item["source"],
                                  "reason": reason, "decided_at": _iso(_now())})
                newly_set_aside += 1
    except Exception as e:
        triage_failed = len(screen)
        print(f"[main] ERROR: triage failed ({e}); {triage_failed} item(s) will be retried next run.", file=sys.stderr)

    known = known_numbers(records)
    added, failed = 0, 0
    for item in relevant:
        try:
            if not allowed(item["url"]):
                print(f"[main] skipping {item['url']}: disallowed by robots.txt", file=sys.stderr)
                continue
            text, _ = fetch_circular_text(item["url"])
            if not text or len(text) < 100:
                print(f"[main] WARNING: little or no text from {item['url']}; will retry", file=sys.stderr)
                failed += 1
                continue
            rec = classify_circular(text, source_url=item["url"], known_circular_numbers=known,
                                    regulator=item["regulator"])
            rec["title"] = item["title"]
            rec["regulator"] = item["regulator"]
            rec["source"] = item["source"]
            if item.get("triage_reason"):
                rec["triage_reason"] = item["triage_reason"]
            if not rec.get("date") or rec["date"] == "NOT STATED IN SOURCE":
                rec["date"] = item.get("date")
            records.append(rec)
            if rec.get("circular_no") and rec["circular_no"] != "NOT STATED IN SOURCE":
                known.add(rec["circular_no"])
            added += 1
            print(f"[main] + [{rec['regulator']}] {item['title'][:70]} -> {rec['doc_type']} ({rec['overall_confidence']})", file=sys.stderr)
        except Exception as e:
            print(f"[main] ERROR processing {item.get('url')}: {e}", file=sys.stderr)
            failed += 1

    cutoff = (_now() - datetime.timedelta(days=KEEP_FILTERED_DAYS)).date().isoformat()
    before = len(set_aside)
    set_aside = [f for f in set_aside if (f.get("date") or f.get("decided_at", "")[:10] or "9999") >= cutoff]
    pruned = before - len(set_aside)

    prev_status = {h["id"]: h["status"] for h in data.get("sources", [])}
    status_changed = prev_status != {h["id"]: h["status"] for h in health}
    last = data.get("generated_at")
    stale = True
    if last:
        try:
            stale = _now() - datetime.datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ") >= datetime.timedelta(hours=HEARTBEAT_HOURS)
        except ValueError:
            stale = True

    if added or newly_set_aside or pruned or status_changed or stale or had_samples:
        data.update({"generated_at": _iso(_now()), "schema_version": "2.0", "circulars": records, "sources": health})
        data.pop("note", None)
        write(DATA_PATH, data)
        write(FILTERED_PATH, {"generated_at": _iso(_now()), "items": set_aside})
        print("[main] data written", file=sys.stderr)
    else:
        print("[main] nothing changed; no write (heartbeat not due)", file=sys.stderr)

    down = [f"{h['id']} ({h['status']})" for h in health if h["status"] in ("failed", "empty", "blocked")]
    summary = (f"Added {added}, set aside {newly_set_aside}, failed {failed}, triage retries {triage_failed}. "
               f"Register: {len(records)} circulars. Sources reached: {len(reached)}/{len(health)}"
               + (f". Needs attention: {', '.join(down)}" if down else ""))
    print(f"[main] {summary}", file=sys.stderr)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(f"### Circular Tracker run\n\n{summary}\n")

    if failed or triage_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
