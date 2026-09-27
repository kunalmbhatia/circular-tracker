import { forwardRef } from "react";
import { TableVirtuoso } from "react-virtuoso";
import { toast } from "sonner";
import { TYPES, CONF_COLOR, confLabel, fmtDate, rowKey } from "../constants";

function Badge({ docType }) {
  const t = TYPES.find((x) => x.key === docType);
  return (
    <span
      className="inline-flex items-center rounded-full px-2.5 py-0.5 text-[11.5px] font-semibold text-white whitespace-nowrap"
      style={{ background: t?.color || "var(--color-s6)", color: docType === "Corrigendum" ? "#111" : "#fff" }}
    >
      {docType || "Unclassified"}
    </span>
  );
}

function ConfBadge({ value }) {
  const label = confLabel(value);
  return (
    <span className="inline-flex items-center gap-1.5 text-[11.5px] font-semibold">
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: CONF_COLOR[label] }} />
      {label}
    </span>
  );
}

function Tag({ children }) {
  return (
    <span className="inline-block rounded-full border border-black/10 dark:border-white/10 bg-[var(--color-chip)] text-[var(--color-ink-secondary)] px-2 py-0.5 text-[11px] mr-1 mb-1">
      {children}
    </span>
  );
}

const TrackerTable = forwardRef(function TrackerTable({ rows, onJumpTo, highlightKey }, ref) {
  return (
    <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-[var(--color-surface)] shadow-[0_1px_2px_rgba(11,11,11,0.05)] overflow-hidden">
      <TableVirtuoso
        ref={ref}
        style={{ height: "min(70vh, 640px)" }}
        data={rows}
        fixedHeaderContent={() => (
          <tr className="bg-[var(--color-surface)]/85 backdrop-blur-md text-[11.5px] uppercase tracking-wide text-[var(--color-ink-muted)]">
            {["Date", "Type", "Circular No.", "Title / Intent", "Segment", "Applies to", "Parent", "Action / Effective", "Confidence"].map((h) => (
              <th key={h} className="text-left font-semibold px-3 py-2.5 border-b border-[var(--color-grid)] whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        )}
        itemContent={(_, c) => {
          const isHighlighted = highlightKey && rowKey(c) === highlightKey;
          const cellClass = `px-3 py-2.5 border-b border-[var(--color-grid)] align-top transition-colors duration-[1400ms] ${
            isHighlighted ? "bg-[var(--color-warning)]/40" : ""
          }`;
          return (
            <>
              <td className={`${cellClass} whitespace-nowrap text-[13px]`}>{fmtDate(c.date)}</td>
              <td className={cellClass}>
                <Badge docType={c.doc_type} />
              </td>
              <td className={`${cellClass} text-[13px]`}>{c.circular_no || "—"}</td>
              <td className={`${cellClass} max-w-[320px] text-[13px]`}>
                <div className="font-medium">{c.title}</div>
                {c.intent && <div className="text-[12px] text-[var(--color-ink-secondary)] mt-0.5">{c.intent}</div>}
                {c.source_url && (
                  <a href={c.source_url} target="_blank" rel="noopener noreferrer" className="text-[11.5px] text-[var(--color-ink-muted)] underline">
                    Source ↗
                  </a>
                )}
              </td>
              <td className={cellClass}>
                {(c.impact_areas || []).map((a) => (
                  <Tag key={a}>{a}</Tag>
                ))}
              </td>
              <td className={`${cellClass} text-[13px]`}>{c.applicability ? <Tag>{c.applicability}</Tag> : "—"}</td>
              <td className={`${cellClass} text-[13px]`}>
                {c.parent_circular_no && c.parent_circular_no !== "NOT STATED IN SOURCE" ? (
                  <button
                    className="text-[var(--color-s1)] underline active:opacity-60 transition-opacity"
                    onClick={() => {
                      const ok = onJumpTo(c.parent_circular_no);
                      if (!ok) toast("Parent circular not in current filtered view — clear filters and retry.");
                    }}
                  >
                    {c.parent_circular_no}
                  </button>
                ) : c.parent_circular_no === "NOT STATED IN SOURCE" ? (
                  <span className="text-[var(--color-ink-muted)]">Referenced, number unconfirmed</span>
                ) : (
                  <span className="text-[var(--color-ink-muted)]">Standalone</span>
                )}
              </td>
              <td className={`${cellClass} text-[13px]`}>
                {c.action_required && <div>{c.action_required}</div>}
                {c.effective_date && <div className="text-[11.5px] text-[var(--color-ink-muted)]">Effective: {c.effective_date}</div>}
                {!c.action_required && !c.effective_date && "—"}
              </td>
              <td className={cellClass}>
                <ConfBadge value={c.overall_confidence} />
              </td>
            </>
          );
        }}
        components={{
          Table: (props) => <table {...props} className="w-full border-collapse text-[13px] min-w-[900px]" />,
          EmptyPlaceholder: () => (
            <div className="p-10 text-center text-sm text-[var(--color-ink-muted)]">No circulars match these filters.</div>
          ),
        }}
      />
    </div>
  );
});

export default TrackerTable;
