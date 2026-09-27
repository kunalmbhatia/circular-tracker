import { useEffect, useMemo, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { toast } from "sonner";
import { useCircularsData } from "./useCircularsData";
import { TYPES, rowKey } from "./constants";
import StatsRow from "./components/StatsRow";
import FiltersPanel from "./components/FiltersPanel";
import TrendChart from "./components/TrendChart";
import TrackerTable from "./components/TrackerTable";
import ExportMenu from "./components/ExportMenu";
import CommandPalette from "./components/CommandPalette";

function parseFiltersFromURL() {
  const p = new URLSearchParams(location.search);
  return {
    search: p.get("q") || "",
    from: p.get("from") || "",
    to: p.get("to") || "",
    hideReview: p.get("hr") === "1",
    types: new Set((p.get("type") || "").split(",").filter(Boolean)),
    segments: new Set((p.get("seg") || "").split(",").filter(Boolean)),
    appl: new Set((p.get("appl") || "").split(",").filter(Boolean)),
  };
}

function writeFiltersToURL(f) {
  const p = new URLSearchParams();
  if (f.search) p.set("q", f.search);
  if (f.from) p.set("from", f.from);
  if (f.to) p.set("to", f.to);
  if (f.hideReview) p.set("hr", "1");
  if (f.types.size) p.set("type", [...f.types].join(","));
  if (f.segments.size) p.set("seg", [...f.segments].join(","));
  if (f.appl.size) p.set("appl", [...f.appl].join(","));
  const qs = p.toString();
  history.replaceState(null, "", location.pathname + (qs ? "?" + qs : ""));
}

export default function App() {
  const { data, status } = useCircularsData();
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [filters, setFilters] = useState(parseFiltersFromURL);
  const [highlightKey, setHighlightKey] = useState(null);
  const [pendingJump, setPendingJump] = useState(null);
  const tableRef = useRef(null);
  const reduceMotion =
    typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)").matches : false;

  useEffect(() => writeFiltersToURL(filters), [filters]);

  useEffect(() => {
    const onSlash = (e) => {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT") {
        e.preventDefault();
        document.querySelector("[data-search-input]")?.focus();
      }
    };
    document.addEventListener("keydown", onSlash);
    return () => document.removeEventListener("keydown", onSlash);
  }, []);

  const segments = useMemo(() => [...new Set(data.circulars.flatMap((c) => c.impact_areas || []))].sort(), [data]);
  const applicabilities = useMemo(() => [...new Set(data.circulars.map((c) => c.applicability).filter(Boolean))].sort(), [data]);

  const filteredRows = useMemo(() => {
    return data.circulars
      .filter((c) => {
        if (filters.search) {
          const hay = [c.circular_no, c.title, c.intent].filter(Boolean).join(" ").toLowerCase();
          if (!hay.includes(filters.search.toLowerCase())) return false;
        }
        if (filters.from && c.date && c.date < filters.from) return false;
        if (filters.to && c.date && c.date > filters.to) return false;
        if (filters.types.size && !filters.types.has(c.doc_type)) return false;
        if (filters.segments.size && !(c.impact_areas || []).some((a) => filters.segments.has(a))) return false;
        if (filters.appl.size && !filters.appl.has(c.applicability)) return false;
        if (filters.hideReview) {
          const label = c.overall_confidence === "NEEDS HUMAN REVIEW" ? "Needs Review" : c.overall_confidence || "Needs Review";
          if (label === "Needs Review") return false;
        }
        return true;
      })
      .sort((a, b) => (b.date || "").localeCompare(a.date || ""));
  }, [data, filters]);

  const anySample = data.circulars.some((c) => c.sample_data);

  const healthInfo = useMemo(() => {
    if (!data.generated_at) return { label: "No pipeline run yet", cls: "bg-[var(--color-critical)]" };
    const hoursAgo = (Date.now() - new Date(data.generated_at).getTime()) / 36e5;
    const label = "Last updated " + new Date(data.generated_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
    const cls = hoursAgo < 30 ? "bg-[var(--color-good)]" : hoursAgo < 72 ? "bg-[var(--color-warning)]" : "bg-[var(--color-critical)]";
    return { label, cls };
  }, [data]);

  function jumpTo(circularNo) {
    const index = filteredRows.findIndex((c) => rowKey(c) === circularNo);
    if (index === -1) return false;
    tableRef.current?.scrollToIndex({ index, align: "center", behavior: reduceMotion ? "auto" : "smooth" });
    setHighlightKey(circularNo);
    setTimeout(() => setHighlightKey(null), 1600);
    return true;
  }

  // A command-palette selection may target a row that's filtered out. Rather than
  // reaching into a stale closure after clearing filters, wait for filteredRows to
  // actually reflect the cleared state, then jump — React state updates are async.
  useEffect(() => {
    if (!pendingJump) return;
    if (jumpTo(pendingJump)) setPendingJump(null);
  }, [pendingJump, filteredRows]);

  async function handleShare() {
    const url = location.href;
    if (navigator.share) {
      try {
        await navigator.share({ title: "SEBI Circular Tracker", url });
        return;
      } catch {
        /* user cancelled */
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Filtered link copied to clipboard.");
    } catch {
      toast(url);
    }
  }

  function clearFilters() {
    setFilters({ search: "", from: "", to: "", hideReview: false, types: new Set(), segments: new Set(), appl: new Set() });
  }

  return (
    <div className="max-w-[1180px] mx-auto px-4 py-5 pb-16">
      <header className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
        <h1 className="text-[23px] font-semibold tracking-[-0.015em]">SEBI Circular Tracker</h1>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-[12.5px] text-[var(--color-ink-muted)]">
            <span className={`h-2 w-2 rounded-full ${healthInfo.cls} ${healthInfo.cls.includes("critical") ? "animate-pulse" : ""}`} />
            {healthInfo.label}
          </div>
          <button
            onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
            className="rounded-lg border border-black/10 dark:border-white/10 bg-[var(--color-chip)] px-2.5 py-1 text-[12px] active:scale-95 transition-transform"
            aria-label="Toggle theme"
          >
            {resolvedTheme === "dark" ? "Light" : "Dark"}
          </button>
        </div>
      </header>
      <p className="text-[13.5px] leading-relaxed text-[var(--color-ink-secondary)] max-w-[68ch] mb-4">
        Open-source tracker from release to implementation — classification, parent-circular mapping, impact area, and
        plain-language intent/action for every SEBI circular. Press <kbd className="px-1 py-0.5 rounded bg-[var(--color-chip)] text-[11px]">/</kbd> to
        search or <kbd className="px-1 py-0.5 rounded bg-[var(--color-chip)] text-[11px]">⌘K</kbd> to jump to a circular.
      </p>

      {anySample && (
        <div className="rounded-xl border border-black/10 dark:border-white/10 bg-[var(--color-chip)] px-3.5 py-2.5 text-[13px] text-[var(--color-ink-secondary)] mb-4">
          <strong className="text-[var(--color-ink)]">Sample data.</strong> This deployment is showing seed/demo records. Run
          the ingestion pipeline (see README) to replace this with live, classified SEBI circulars. Every seed record is
          flagged <strong className="text-[var(--color-ink)]">Needs Review</strong>.
        </div>
      )}

      <div className="flex flex-col gap-4">
        <StatsRow rows={filteredRows} />
        <TrendChart rows={filteredRows} />
        <FiltersPanel filters={filters} setFilters={setFilters} segments={segments} applicabilities={applicabilities} />

        <div className="flex flex-wrap gap-2">
          <button
            onClick={handleShare}
            className="rounded-lg px-3 py-1.5 text-[12.5px] text-white active:scale-95 transition-transform"
            style={{ background: "var(--color-s1)" }}
          >
            Share filtered view
          </button>
          <ExportMenu rows={filteredRows} />
          <button
            onClick={clearFilters}
            className="rounded-lg border border-black/10 dark:border-white/10 bg-[var(--color-chip)] px-3 py-1.5 text-[12.5px] active:scale-95 transition-transform"
          >
            Clear filters
          </button>
        </div>

        {status === "error" ? (
          <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-[var(--color-surface)] p-10 text-center text-sm text-[var(--color-ink-muted)]">
            Could not load <code>data/circulars.json</code>. If you're running this locally, use{" "}
            <code>npm run dev</code> rather than opening the built file directly.
          </div>
        ) : (
          <TrackerTable ref={tableRef} rows={filteredRows} onJumpTo={jumpTo} highlightKey={highlightKey} />
        )}
      </div>

      <footer className="mt-6 text-[12px] text-[var(--color-ink-muted)] leading-relaxed">
        Data is auto-classified by an LLM against the circular text and carries per-field confidence flags — treat anything
        marked <strong>Inferred</strong> or <strong>Needs Review</strong> as unverified and check the original circular
        before acting on it. Not legal or compliance advice.
        <br />
        Open source — see the repository README for the ingestion pipeline and how to run your own copy.
      </footer>

      <CommandPalette
        rows={data.circulars}
        onSelect={(c) => {
          const key = rowKey(c);
          const inView = filteredRows.some((r) => rowKey(r) === key);
          if (!inView) clearFilters();
          setPendingJump(key);
        }}
      />
    </div>
  );
}
