import { TYPES, confLabel } from "../constants";

export default function StatsRow({ rows }) {
  const byType = Object.fromEntries(TYPES.map((t) => [t.key, 0]));
  let needsReview = 0;
  for (const c of rows) {
    if (byType[c.doc_type] !== undefined) byType[c.doc_type]++;
    if (confLabel(c.overall_confidence) === "Needs Review") needsReview++;
  }
  const tiles = [
    { n: rows.length, l: "Total (filtered)" },
    { n: byType["Fresh Circular"], l: "Fresh" },
    { n: (byType.Amendment || 0) + (byType.Addendum || 0) + (byType.Corrigendum || 0), l: "Amend./Addm./Corr." },
    { n: byType["Master Circular"], l: "Master Circulars" },
    { n: needsReview, l: "Needs review", accent: needsReview > 0 },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2.5">
      {tiles.map((t) => (
        <div
          key={t.l}
          className="rounded-xl border border-black/10 dark:border-white/10 bg-[var(--color-surface)] px-3.5 py-3 shadow-[0_1px_2px_rgba(11,11,11,0.05)]"
        >
          <div
            className="text-2xl font-semibold leading-none tabular-nums"
            style={t.accent ? { color: "var(--color-critical)" } : undefined}
          >
            {t.n || 0}
          </div>
          <div className="text-xs text-[var(--color-ink-secondary)] mt-1">{t.l}</div>
        </div>
      ))}
    </div>
  );
}
