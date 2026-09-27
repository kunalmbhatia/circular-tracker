import { confLabel } from "../constants";

// xlsx and jsPDF (which pulls in html2canvas internally) are only needed once
// someone actually exports, and together they're a meaningful chunk of the
// bundle — dynamically importing them keeps the initial page load light.

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

async function toExcel(rows) {
  const XLSX = await import("xlsx");
  const data = rows.map((c) => ({
    Date: c.date || "",
    Type: c.doc_type || "",
    "Circular No": c.circular_no || "",
    Title: c.title || "",
    Intent: c.intent || "",
    Segments: (c.impact_areas || []).join("; "),
    "Applies To": c.applicability || "",
    "Parent Circular": c.parent_circular_no || "",
    "Action Required": c.action_required || "",
    "Effective Date": c.effective_date || "",
    Confidence: confLabel(c.overall_confidence),
    "Source URL": c.source_url || "",
  }));
  const ws = XLSX.utils.json_to_sheet(data);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Circulars");
  XLSX.writeFile(wb, `sebi-circulars-${todayStr()}.xlsx`);
}

async function toPdf(rows) {
  const [{ default: jsPDF }, { default: autoTable }] = await Promise.all([
    import("jspdf"),
    import("jspdf-autotable"),
  ]);
  const doc = new jsPDF({ orientation: "landscape" });
  doc.setFontSize(14);
  doc.text("SEBI Circular Tracker", 14, 14);
  doc.setFontSize(9);
  doc.text(`Exported ${new Date().toLocaleString("en-IN")}`, 14, 20);
  autoTable(doc, {
    startY: 26,
    head: [["Date", "Type", "Circular No", "Title", "Segments", "Action Required", "Confidence"]],
    body: rows.map((c) => [
      c.date || "",
      c.doc_type || "",
      c.circular_no || "",
      c.title || "",
      (c.impact_areas || []).join(", "),
      c.action_required || "",
      confLabel(c.overall_confidence),
    ]),
    styles: { fontSize: 7, cellWidth: "wrap" },
    columnStyles: { 3: { cellWidth: 70 }, 4: { cellWidth: 35 }, 5: { cellWidth: 45 } },
    headStyles: { fillColor: [42, 120, 214] },
  });
  doc.save(`sebi-circulars-${todayStr()}.pdf`);
}

export default function ExportMenu({ rows }) {
  return (
    <div className="flex gap-2">
      <button
        onClick={() => toExcel(rows)}
        className="rounded-lg border border-black/10 dark:border-white/10 bg-[var(--color-chip)] px-3 py-1.5 text-[12.5px] active:scale-95 transition-transform"
      >
        Export Excel
      </button>
      <button
        onClick={() => toPdf(rows)}
        className="rounded-lg border border-black/10 dark:border-white/10 bg-[var(--color-chip)] px-3 py-1.5 text-[12.5px] active:scale-95 transition-transform"
      >
        Export PDF
      </button>
    </div>
  );
}
