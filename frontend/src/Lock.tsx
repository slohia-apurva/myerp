import type { ReactNode } from "react";

/** What a record says of its use: why it is in use, and which key fields that locks. */
export type LockInfo = { in_use: string[]; locked: string[] };

/** Whether `field` is locked on a record (a record being added has no lock). */
export const isLocked = (lock: LockInfo | undefined, field: string) => !!lock && lock.locked.includes(field);

/** A key field of a record in use: greyed, tagged "Locked", and not clickable or focusable. */
export function Locked({ on, children }: { on: boolean; children: ReactNode }) {
  if (!on) return <>{children}</>;
  // `inert` keeps the control from being focused or changed; React 18 passes it through as an attribute.
  return (
    <span className="locked-field" {...({ inert: "" } as object)}>
      {children}
    </span>
  );
}

/** The one line at the top of a record that is in use, saying what uses it. */
export function InUseNote({ lock, children }: { lock: LockInfo | undefined; children?: ReactNode }) {
  if (!lock || lock.in_use.length === 0) return null;
  return (
    <div className="use-note">
      <b>In use: {lock.in_use.join(", ")}.</b> {children ?? "The locked fields cannot be changed. Everything else stays open."}
    </div>
  );
}
