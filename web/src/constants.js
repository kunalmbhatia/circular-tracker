export const TYPES = [
  { key: "Fresh Circular", color: "var(--color-s1)" },
  { key: "Amendment", color: "var(--color-s2)" },
  { key: "Addendum", color: "var(--color-s3)" },
  { key: "Corrigendum", color: "var(--color-s4)" },
  { key: "Master Circular", color: "var(--color-s5)" },
  { key: "FAQ/Clarification", color: "var(--color-s6)" },
];

export const CONF_COLOR = {
  Certain: "var(--color-good)",
  Inferred: "var(--color-warning)",
  "Needs Review": "var(--color-critical)",
  "NEEDS HUMAN REVIEW": "var(--color-critical)",
};

export function confLabel(c) {
  if (!c) return "Needs Review";
  if (c === "NEEDS HUMAN REVIEW") return "Needs Review";
  return c;
}

export function fmtDate(d) {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleDateString("en-IN", { year: "numeric", month: "short", day: "2-digit" });
  } catch {
    return d;
  }
}

export function rowKey(c) {
  return c.circular_no && c.circular_no !== "NOT STATED IN SOURCE" ? c.circular_no : `${c.title}|${c.date || ""}`;
}
