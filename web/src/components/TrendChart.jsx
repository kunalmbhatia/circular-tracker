import { useMemo } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from "recharts";
import { TYPES } from "../constants";

function monthKey(dateStr) {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return null;
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function TrendChart({ rows }) {
  const chartData = useMemo(() => {
    const buckets = new Map();
    for (const c of rows) {
      const key = monthKey(c.date);
      if (!key) continue;
      if (!buckets.has(key)) {
        buckets.set(key, { month: key, ...Object.fromEntries(TYPES.map((t) => [t.key, 0])) });
      }
      const bucket = buckets.get(key);
      if (bucket[c.doc_type] !== undefined) bucket[c.doc_type]++;
    }
    return [...buckets.values()].sort((a, b) => a.month.localeCompare(b.month));
  }, [rows]);

  if (chartData.length === 0) {
    return (
      <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-[var(--color-surface)] p-6 text-sm text-[var(--color-ink-muted)] text-center">
        No dated circulars in the current filter to chart.
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-[var(--color-surface)] p-4 shadow-[0_1px_2px_rgba(11,11,11,0.05)]">
      <div className="text-[13px] font-medium mb-2">Circulars per month, by type</div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={chartData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-grid)" vertical={false} />
          <XAxis dataKey="month" tick={{ fontSize: 11, fill: "var(--color-ink-muted)" }} axisLine={{ stroke: "var(--color-grid)" }} tickLine={false} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "var(--color-ink-muted)" }} axisLine={false} tickLine={false} width={28} />
          <Tooltip
            contentStyle={{ background: "var(--color-surface)", border: "1px solid var(--color-grid)", borderRadius: 8, fontSize: 12 }}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {TYPES.map((t) => (
            <Bar key={t.key} dataKey={t.key} stackId="a" fill={t.color} radius={[2, 2, 0, 0]} maxBarSize={28} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
