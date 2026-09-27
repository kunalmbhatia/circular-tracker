import clsx from "clsx";
import { TYPES } from "../constants";

function Chip({ active, onClick, children, colorVar }) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        "rounded-full border px-3 py-1 text-[12.5px] transition-all duration-150 ease-out active:scale-95 select-none",
        active
          ? "text-white border-transparent"
          : "text-[var(--color-ink-secondary)] bg-[var(--color-chip)] border-black/10 dark:border-white/10 hover:brightness-95"
      )}
      style={active ? { background: colorVar || "var(--color-ink)" } : undefined}
    >
      {children}
    </button>
  );
}

export default function FiltersPanel({ filters, setFilters, segments, applicabilities }) {
  const toggleSet = (key, value) => {
    setFilters((f) => {
      const next = new Set(f[key]);
      next.has(value) ? next.delete(value) : next.add(value);
      return { ...f, [key]: next };
    });
  };

  return (
    <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-[var(--color-surface)] p-3.5 shadow-[0_1px_2px_rgba(11,11,11,0.05)] flex flex-col gap-3">
      <div className="flex flex-wrap gap-2.5 items-center">
        <input
          type="text"
          placeholder="Search title, circular no., intent… ( / to focus)"
          value={filters.search}
          onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
          data-search-input
          className="flex-1 min-w-[180px] rounded-lg border border-black/10 dark:border-white/10 bg-[var(--color-page)] px-2.5 py-1.5 text-[13px] outline-none focus-visible:ring-2 ring-[var(--color-s1)]"
        />
        <input
          type="date"
          value={filters.from}
          onChange={(e) => setFilters((f) => ({ ...f, from: e.target.value }))}
          className="rounded-lg border border-black/10 dark:border-white/10 bg-[var(--color-page)] px-2.5 py-1.5 text-[13px] outline-none focus-visible:ring-2 ring-[var(--color-s1)]"
        />
        <span className="text-xs text-[var(--color-ink-muted)]">to</span>
        <input
          type="date"
          value={filters.to}
          onChange={(e) => setFilters((f) => ({ ...f, to: e.target.value }))}
          className="rounded-lg border border-black/10 dark:border-white/10 bg-[var(--color-page)] px-2.5 py-1.5 text-[13px] outline-none focus-visible:ring-2 ring-[var(--color-s1)]"
        />
        <label className="flex items-center gap-1.5 text-[12.5px] text-[var(--color-ink-secondary)] cursor-pointer">
          <input
            type="checkbox"
            checked={filters.hideReview}
            onChange={(e) => setFilters((f) => ({ ...f, hideReview: e.target.checked }))}
          />
          Hide items needing review
        </label>
      </div>

      <FilterRow label="Type">
        {TYPES.map((t) => (
          <Chip key={t.key} active={filters.types.has(t.key)} onClick={() => toggleSet("types", t.key)} colorVar={t.color}>
            {t.key}
          </Chip>
        ))}
      </FilterRow>

      <FilterRow label="Segment">
        {segments.map((s) => (
          <Chip key={s} active={filters.segments.has(s)} onClick={() => toggleSet("segments", s)}>
            {s}
          </Chip>
        ))}
      </FilterRow>

      <FilterRow label="Applies to">
        {applicabilities.map((a) => (
          <Chip key={a} active={filters.appl.has(a)} onClick={() => toggleSet("appl", a)}>
            {a}
          </Chip>
        ))}
      </FilterRow>
    </div>
  );
}

function FilterRow({ label, children }) {
  return (
    <div className="flex flex-wrap gap-1.5 items-center">
      <span className="text-[11px] uppercase tracking-wide text-[var(--color-ink-muted)] mr-1">{label}</span>
      {children}
    </div>
  );
}
