import { useEffect, useState } from "react";
import { Command } from "cmdk";
import { fmtDate } from "../constants";

export default function CommandPalette({ rows, onSelect }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const handler = (e) => {
      const tag = document.activeElement?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA";
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !typing)) {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh] bg-black/30 backdrop-blur-[2px]"
      onClick={() => setOpen(false)}
    >
      <Command
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg rounded-2xl border border-black/10 dark:border-white/10 bg-[var(--color-surface)] shadow-2xl overflow-hidden"
        label="Jump to a circular"
      >
        <Command.Input
          autoFocus
          placeholder="Jump to a circular by title or number…"
          className="w-full px-4 py-3 text-[14px] outline-none bg-transparent border-b border-[var(--color-grid)]"
        />
        <Command.List className="max-h-80 overflow-y-auto p-1.5">
          <Command.Empty className="px-3 py-6 text-center text-sm text-[var(--color-ink-muted)]">No matches.</Command.Empty>
          {rows.slice(0, 500).map((c) => (
            <Command.Item
              key={`${c.circular_no}-${c.title}-${c.date}`}
              value={`${c.title} ${c.circular_no || ""}`}
              onSelect={() => {
                onSelect(c);
                setOpen(false);
              }}
              className="flex flex-col gap-0.5 rounded-lg px-3 py-2 text-sm cursor-pointer data-[selected=true]:bg-[var(--color-chip)]"
            >
              <span className="font-medium">{c.title}</span>
              <span className="text-[11.5px] text-[var(--color-ink-muted)]">
                {fmtDate(c.date)} · {c.doc_type} {c.circular_no && c.circular_no !== "NOT STATED IN SOURCE" ? `· ${c.circular_no}` : ""}
              </span>
            </Command.Item>
          ))}
        </Command.List>
      </Command>
    </div>
  );
}
