import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

/** The bell in the top menu: messages for this person, such as an over-receipt on a goods
 * receipt for the Purchase team and the Owner. Checked every minute while the page is open. */
type Note = { id: number; title: string; body: string; link: string; created_at: string; read: boolean };

export function NotificationBell() {
  const [rows, setRows] = useState<Note[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const load = useCallback(() => {
    api<{ unread: number; rows: Note[] }>("v1/notifications/").then(
      (d) => {
        setRows(d.rows);
        setUnread(d.unread);
      },
      () => undefined,
    );
  }, []);
  useEffect(() => {
    load();
    const timer = window.setInterval(load, 60000);
    return () => window.clearInterval(timer);
  }, [load]);
  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  const read = (ids?: number[]) => api("v1/notifications/read/", ids ? { ids } : {}).then(load, () => undefined);
  const when = (iso: string) =>
    new Date(iso).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "numeric", minute: "2-digit" });
  return (
    <div className="menu bell" ref={box}>
      <button type="button" className="bell-button" aria-haspopup="true" aria-expanded={open} title="Notifications" onClick={() => setOpen(!open)}>
        <span aria-hidden="true">🔔</span>
        {unread > 0 && <span className="bell-count">{unread > 99 ? "99+" : unread}</span>}
        <span className="sr-only">{unread} unread notifications</span>
      </button>
      {open && (
        <div className="menu-panel bell-panel" role="menu">
          <div className="bell-head">
            <b>Notifications</b>
            {unread > 0 && (
              <button type="button" className="link" onClick={() => read()}>
                Mark all read
              </button>
            )}
          </div>
          {rows.length === 0 && <p className="small bell-empty">Nothing yet.</p>}
          {rows.map((n) => (
            <a
              key={n.id}
              role="menuitem"
              href={n.link || undefined}
              className={n.read ? "bell-row" : "bell-row unread"}
              onClick={() => {
                if (!n.read) read([n.id]);
                setOpen(false);
              }}
            >
              <b>{n.title}</b>
              <span className="small">{n.body}</span>
              <span className="small">{when(n.created_at)}</span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
