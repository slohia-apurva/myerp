/** Locked rates on orders (Sidharth, 2026-11-26): a rate that comes from the
 * party's own Item Prices or its price list shows grey with a lock and cannot be
 * typed over; a line with no such price takes a typed rate, marked "Typed (no
 * price set)". The server refuses a changed locked rate too (core/price_lists.py). */

export function RateBox({
  label,
  value,
  locked,
  onChange,
  why,
  placeholder,
}: {
  label: string;
  value: string;
  locked: boolean;
  onChange: (value: string) => void;
  why: string;
  placeholder?: string;
}) {
  if (locked) {
    return (
      <span className="rate-locked" title={why}>
        <span aria-hidden="true">🔒</span>
        <input className="num" aria-label={label} value={value} placeholder={placeholder} readOnly tabIndex={-1} />
      </span>
    );
  }
  return <input className="num" inputMode="decimal" aria-label={label} placeholder={placeholder} value={value} onChange={(e) => onChange(e.target.value)} />;
}

/** The words under a rate: where a locked rate came from, or that it was typed. */
export function RateSource({ line }: { line: { item: string; rate: string; source: string; locked: boolean } }) {
  if (line.locked) return <span className="small rate-from">{line.source}</span>;
  if (line.item && line.rate) return <span className="small rate-typed">Typed (no price set)</span>;
  return null;
}
