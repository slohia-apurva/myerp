/**
 * Phones (Sidharth, 2026-11-26: "quite a few screens still do not fit on the iPhone"): below
 * 768px every list (`table.pick`) and every table of lines (`table.grid`) shows each row as a
 * small card instead of a row wider than the phone (app.css, "Tables as cards on phones"). A card
 * cannot show the column headings above it, so this copies each column's heading onto its cells
 * as `data-label`, which the CSS prints in small letters beside (lists) or above (lines) the
 * value. It runs again whenever a table redraws. Nothing changes on a wider screen.
 */
const PHONE = "(max-width: 768px)";
const TABLES = "table.pick, table.grid";

function headings(table: HTMLTableElement): string[] {
  const row = table.tHead?.rows[0];
  if (!row) return [];
  const out: string[] = [];
  for (const th of Array.from(row.cells)) {
    const text = (th.textContent ?? "").replace(/\s+/g, " ").trim();
    for (let i = 0; i < th.colSpan; i++) out.push(text);
  }
  return out;
}

function label(table: HTMLTableElement) {
  const heads = headings(table);
  if (heads.length === 0) return;
  const rows = [...Array.from(table.tBodies).flatMap((b) => Array.from(b.rows)), ...Array.from(table.tHead?.rows ?? []).slice(1)];
  for (const row of rows) {
    let col = 0;
    for (const cell of Array.from(row.cells)) {
      const text = cell.colSpan === 1 ? (heads[col] ?? "") : "";
      if (cell.dataset.label !== text) {
        if (text) cell.dataset.label = text;
        else delete cell.dataset.label;
      }
      col += cell.colSpan;
    }
  }
}

export function labelTablesOnPhones() {
  const phone = window.matchMedia(PHONE);
  let queued = false;
  const run = () => {
    queued = false;
    if (phone.matches) document.querySelectorAll<HTMLTableElement>(TABLES).forEach(label);
  };
  const soon = () => {
    if (!queued) {
      queued = true;
      requestAnimationFrame(run);
    }
  };
  new MutationObserver(soon).observe(document.body, { childList: true, subtree: true });
  phone.addEventListener("change", soon);
  soon();
}
