import { useCallback, useEffect, useRef, useState } from "react";
import { api, type SignedIn } from "./api";
import { PageHeader } from "./Brand";
import { closeThisTab } from "./Create";
import { ErrorNote } from "./ErrorNote";
import { ActionsMenu } from "./Exchange";
import { hashParam, openTab } from "./Master";
import { pickPdf } from "./PickLists";

/** Entry > Sales > Scan Picking (Sidharth, 2026-11-25, preview mockups/scan-picking): scan the
 * pick list's barcode, then each package label, unit barcode or bin label as it is picked; the
 * server says at once whether it is right. Made for a phone: a scanner gun types into the scan
 * box and presses Enter; the "Camera" button reads codes where the browser can (Android Chrome).
 * Every scan is saved at once, so a refresh or a second picker carries on. */

export type ScanRow = {
  id: number;
  position: number;
  item_name: string;
  item_number: string;
  location: number;
  location_name: string;
  batch_number: string;
  package_number: string;
  package_left: string;
  qty: string;
  unit: string;
  done: boolean;
  got: string;
  how: string;
  at: string | null;
};
export type Check = { done: number; total: number; scanned: number; by_barcode: number; by_hand: number; wrong: number; started: boolean };
type Screen = Check & {
  id: number;
  number: string;
  status: string;
  status_label: string;
  customer_name: string;
  order_number: string;
  despatch_from: string;
  rows: ScanRow[];
};
type Offer = { row: number; package: number; package_number: string; instead_of: string };
type Reply = { result: "ok" | "warn" | "wrong" | "offer" | "bin"; message: string; offer?: Offer; bin?: number; row?: number; list: Screen };
type OpenList = { id: number; number: string; customer_name: string; order_number: string; despatch_from: string; check?: Check };

const base = (companyId: number) => `#/companies/${companyId}/scan-picking`;
const CRUMB = "Entry › Sales";
const can = (session: SignedIn, action: string) => session.permissions.includes(`sales.${action}`) || session.permissions.includes(`stock.${action}`);
const time = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }) : "");

/** A short beep (and a buzz where the phone can) for a wrong scan, a soft tick for a right one. */
function sound(ok: boolean) {
  try {
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new Ctx();
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.frequency.value = ok ? 880 : 220;
    g.gain.value = 0.15;
    o.connect(g).connect(ctx.destination);
    o.start();
    o.stop(ctx.currentTime + (ok ? 0.08 : 0.35));
    o.onended = () => ctx.close();
  } catch {
    /* no sound on this device */
  }
  if (!ok) navigator.vibrate?.([120, 60, 120]);
}

export function ScanPickingPage({ companyId, session }: { companyId: number; session: SignedIn }) {
  const list = Number(hashParam("list"));
  if (list > 0) return <ScanList key={list} companyId={companyId} id={list} session={session} />;
  return <ScanStart companyId={companyId} />;
}

/** The scan box: a scanner gun types and presses Enter; the camera button fills it in. */
function ScanBox(props: { placeholder: string; label: string; busy: boolean; onCode: (code: string) => void; focusKey?: unknown }) {
  const [code, setCode] = useState("");
  const [camera, setCamera] = useState(false);
  const box = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!props.busy) box.current?.focus();
  }, [props.busy, props.focusKey]);
  const send = (value: string) => {
    const v = value.trim();
    if (!v) return;
    setCode("");
    props.onCode(v);
  };
  return (
    <>
      <form
        className="scan-box"
        onSubmit={(e) => {
          e.preventDefault();
          send(code);
        }}
      >
        <input
          ref={box}
          aria-label={props.label}
          placeholder={props.placeholder}
          value={code}
          autoComplete="off"
          autoCapitalize="characters"
          enterKeyHint="go"
          onChange={(e) => setCode(e.target.value)}
        />
        <button type="button" onClick={() => setCamera(true)} aria-label="Scan with the camera">
          📷 Camera
        </button>
      </form>
      {camera && (
        <CameraScan
          onCode={(c) => {
            setCamera(false);
            send(c);
          }}
          onClose={() => setCamera(false)}
        />
      )}
    </>
  );
}

type Detector = { detect: (v: HTMLVideoElement) => Promise<{ rawValue: string }[]> };

/** The phone camera reading one barcode or QR code, where the browser can
 * (BarcodeDetector: Chrome on Android). Elsewhere it says to use a scanner or type. */
function CameraScan(props: { onCode: (code: string) => void; onClose: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [problem, setProblem] = useState("");
  const { onCode } = props;
  useEffect(() => {
    const Made = (window as unknown as { BarcodeDetector?: new (o: object) => Detector }).BarcodeDetector;
    if (!Made || !navigator.mediaDevices?.getUserMedia) {
      setProblem("This browser cannot read barcodes with the camera. Use a scanner, or type the code.");
      return;
    }
    let stream: MediaStream | null = null;
    let timer = 0;
    let stopped = false;
    const detector = new Made({ formats: ["code_128", "qr_code", "ean_13", "ean_8", "upc_a", "code_39"] });
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" } })
      .then((s) => {
        stream = s;
        if (stopped || !video.current) return;
        video.current.srcObject = s;
        void video.current.play();
        const look = async () => {
          if (stopped || !video.current) return;
          try {
            const found = await detector.detect(video.current);
            if (found[0]?.rawValue) {
              onCode(found[0].rawValue);
              return;
            }
          } catch {
            /* frame not ready yet */
          }
          timer = window.setTimeout(look, 250);
        };
        look();
      })
      .catch(() => setProblem("The camera could not be opened. Allow the camera for this site, or use a scanner."));
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [onCode]);
  return (
    <div className="popup-back" role="presentation">
      <div className="popup scan-camera" role="dialog" aria-modal="true" aria-label="Scan with the camera">
        <h3>Point the camera at the barcode</h3>
        {problem ? <p className="use-note">{problem}</p> : <video ref={video} muted playsInline />}
        <div className="popup-actions">
          <button type="button" className="link" onClick={props.onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

function ScanStart({ companyId }: { companyId: number }) {
  const [lists, setLists] = useState<OpenList[]>([]);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<OpenList[]>(`v1/companies/${companyId}/pick-lists/?view=open&check=1`).then(setLists, setError);
  }, [companyId]);
  const go = (id: number) => openTab(`${base(companyId)}?list=${id}`);
  const find = async (code: string) => {
    setError("");
    setBusy(true);
    try {
      go((await api<{ id: number }>(`v1/companies/${companyId}/scan-picking/find/?code=${encodeURIComponent(code)}`)).id);
    } catch (err) {
      sound(false);
      setError(err);
    }
    setBusy(false);
  };
  return (
    <section className="page scan-page">
      <PageHeader title="Scan Picking" crumbs={[{ label: CRUMB, href: base(companyId) }]} />
      <div className="scan-main">
        <span className="scan-label">Scan Pick List</span>
        <ScanBox label="Scan Pick List" placeholder="Scan or type PL number…" busy={busy} onCode={find} />
        <p className="small">The barcode at the top right of the printed pick list.</p>
        <ErrorNote error={error} />
        <div className="scan-group">
          <h2>
            Open Pick Lists <span>{lists.length}</span>
          </h2>
          {lists.length === 0 && <p className="small scan-line">No open pick lists.</p>}
          {lists.map((p) => (
            <button type="button" key={p.id} className="scan-line scan-pick" onClick={() => go(p.id)}>
              <span className="scan-what">
                <b>{p.number}</b>
                <span className="small">
                  {p.customer_name} · {p.order_number} · {p.despatch_from}
                </span>
              </span>
              {p.check && (
                <span className={p.check.started ? "pill on" : "pill warn"}>
                  {p.check.started ? `${p.check.done} of ${p.check.total}` : "Not started"}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function ScanList({ companyId, id, session }: { companyId: number; id: number; session: SignedIn }) {
  const [screen, setScreen] = useState<Screen | null>(null);
  const [error, setError] = useState<unknown>("");
  const [reply, setReply] = useState<Omit<Reply, "list"> | null>(null);
  const [busy, setBusy] = useState(false);
  const [showDone, setShowDone] = useState(true);
  const [hand, setHand] = useState<{ row: number; qty: string } | null>(null);
  const [restart, setRestart] = useState(false);
  const [tick, setTick] = useState(0);
  const load = useCallback(() => {
    api<Screen>(`v1/pick-lists/${id}/scans/`).then(setScreen, setError);
  }, [id]);
  useEffect(load, [load]);
  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
  const run = async (path: string, body?: unknown, method?: "DELETE") => {
    setError("");
    setBusy(true);
    try {
      const r = await api<Reply | Screen>(`v1/pick-lists/${id}/${path}`, body, method);
      if ("list" in r) {
        const { list, ...rest } = r;
        setScreen(list);
        setReply(rest);
        sound(rest.result === "ok" || rest.result === "bin");
        if (rest.bin) document.getElementById(`bin-${rest.bin}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
      } else {
        setScreen(r);
        setReply(null);
      }
      setHand(null);
    } catch (err) {
      sound(false);
      setError(err);
    }
    setBusy(false);
    setTick((n) => n + 1);
  };
  const submit = async () => {
    setError("");
    setBusy(true);
    try {
      await api(`v1/pick-lists/${id}/submit/`, {});
      load();
      setReply({ result: "ok", message: "Submitted: the list is Picked. The Delivery Note can be made from it." });
    } catch (err) {
      setError(err);
    }
    setBusy(false);
  };
  if (!screen)
    return (
      <section className="page scan-page">
        <PageHeader title="Scan Picking" crumbs={[{ label: CRUMB, href: base(companyId) }]} />
        <ErrorNote error={error} />
      </section>
    );
  const isOpen = screen.status === "open";
  const mayScan = isOpen && can(session, "create");
  const bins: { id: number; name: string; rows: ScanRow[] }[] = [];
  for (const r of screen.rows) {
    const b = bins.find((x) => x.id === r.location);
    if (b) b.rows.push(r);
    else bins.push({ id: r.location, name: r.location_name, rows: [r] });
  }
  const cls = { ok: "scan-flash ok", bin: "scan-flash ok", warn: "scan-flash warn", offer: "scan-flash warn", wrong: "scan-flash bad" };
  const all = screen.total > 0 && screen.done === screen.total;
  return (
    <section className="page scan-page">
      <PageHeader
        title={screen.number}
        sub={`Scan Picking · ${screen.customer_name} · ${screen.order_number}`}
        crumbs={[{ label: CRUMB, href: base(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            <button type="button" className="link" onClick={() => openTab(`#/companies/${companyId}/pick-lists?view=${id}`)}>
              Open Pick List
            </button>
            <ActionsMenu
              label="Print"
              items={[
                { label: "Pick list", onClick: () => pickPdf(id) },
                { label: "Download PDF", onClick: () => pickPdf(id, true) },
              ]}
            />
          </>
        }
      />
      <div className="scan-main">
        <div className="scan-count">
          <span className="scan-label">Verified</span>
          <b>
            {screen.done} of {screen.total} lines
          </b>
        </div>
        <div className="scan-bar" role="progressbar" aria-valuemin={0} aria-valuemax={screen.total} aria-valuenow={screen.done}>
          <i style={{ width: `${screen.total ? (100 * screen.done) / screen.total : 0}%` }} />
        </div>
        {!isOpen && <p className="use-note">{screen.number} is {screen.status_label}: only an open list is scanned.</p>}
        {mayScan && <ScanBox label="Scan package, item or bin" placeholder="Scan package, item or bin…" busy={busy} onCode={(code) => run("scans/", { code })} focusKey={tick} />}
        <ErrorNote error={error} />
        {reply && (
          <div className={cls[reply.result]} role="status">
            {reply.result === "wrong" ? "✕ " : reply.result === "ok" || reply.result === "bin" ? "✓ " : "⚠ "}
            {reply.message}
            {reply.offer && (
              <div className="buttons">
                <button type="button" disabled={busy} onClick={() => run("scans/swap/", { row: reply.offer?.row, package: reply.offer?.package })}>
                  Use {reply.offer.package_number} instead
                </button>
                <button type="button" className="link" onClick={() => setReply(null)}>
                  Put it back
                </button>
              </div>
            )}
          </div>
        )}
        {all && isOpen && (
          <>
            <p className="scan-flash ok">
              ✓ Everything on the list is checked: {screen.scanned} scanned, {screen.by_barcode} by item barcode, {screen.by_hand} by hand.
            </p>
            {can(session, "submit") && (
              <button type="button" className="scan-submit" disabled={busy} onClick={submit}>
                Submit as Picked
              </button>
            )}
            <p className="small">Same as &quot;Submit&quot; on the pick list: the list becomes Picked and the Delivery Note can be made from it.</p>
          </>
        )}
        <label className="scan-show">
          <input type="checkbox" checked={showDone} onChange={(e) => setShowDone(e.target.checked)} /> Show Done
        </label>
        {bins.map((b) => {
          const shown = b.rows.filter((r) => showDone || !r.done);
          return (
            <div className="scan-group" key={b.id} id={`bin-${b.id}`}>
              <h2>
                Bin {b.name}{" "}
                <span>
                  {b.rows.filter((r) => r.done).length} of {b.rows.length} done
                </span>
              </h2>
              {shown.map((r) => (
                <div key={r.id} className={r.done ? "scan-line done" : "scan-line"}>
                  <span className={r.done ? "ok-note" : "small"} aria-label={r.done ? "Done" : "Not done"}>
                    {r.done ? "✓" : "○"}
                  </span>
                  <span className="scan-what">
                    <b>{r.item_name}</b>
                    <span className="small">
                      {[r.item_number, r.batch_number && `Batch ${r.batch_number}`, r.package_number || "no package"].filter(Boolean).join(" · ")}
                      {r.package_number && Number(r.qty) < Number(r.package_left) && ` (take ${r.qty} of ${r.package_left})`}
                      {!r.package_number && !r.done && ` · ${r.got} of ${r.qty}`}
                    </span>
                    {r.how && (
                      <span className="small">
                        {r.how}
                        {r.at && ` · ${time(r.at)}`}
                      </span>
                    )}
                    {mayScan && !r.done && hand?.row !== r.id && (
                      <span>
                        <button type="button" className="link" onClick={() => setHand({ row: r.id, qty: String(Number(r.qty) - Number(r.got)) })}>
                          Tick by Hand…
                        </button>
                      </span>
                    )}
                    {hand?.row === r.id && (
                      <span className="scan-hand">
                        <b>Picked By Hand</b>
                        <span className="buttons">
                          {r.package_number ? (
                            <span>
                              {r.package_number}, {r.qty} {r.unit}
                            </span>
                          ) : (
                            <>
                              <input className="num" inputMode="decimal" aria-label={`Qty picked by hand for ${r.item_name}`} value={hand.qty} onChange={(e) => setHand({ ...hand, qty: e.target.value })} /> {r.unit}
                            </>
                          )}
                          <button type="button" disabled={busy} onClick={() => run("scans/hand/", { row: r.id, qty: hand.qty })}>
                            Save
                          </button>
                          <button type="button" className="link" onClick={() => setHand(null)}>
                            Cancel
                          </button>
                        </span>
                        <span className="small">For goods with no label to scan. The line then shows &quot;By hand&quot; and your name.</span>
                      </span>
                    )}
                  </span>
                  <b className="scan-qty">
                    {r.qty} {r.unit}
                  </b>
                </div>
              ))}
            </div>
          );
        })}
        <p className="small">
          A package label (PK-…) ticks its line. A free bag of the same item and batch can be taken in place of a listed one. An item&apos;s unit barcode (for
          example its carton) counts that many against the item&apos;s lines with no package. A bin label (LOC-…) jumps to that bin. A wrong scan beeps and
          ticks nothing.
        </p>
        {mayScan && screen.started && (
          <div className="buttons">
            {restart ? (
              <>
                <span>Clear every tick on this list?</span>
                <button type="button" className="link danger" onClick={() => run("scans/", undefined, "DELETE").then(() => setRestart(false))}>
                  Clear ticks
                </button>
                <button type="button" className="link" onClick={() => setRestart(false)}>
                  Keep them
                </button>
              </>
            ) : (
              <button type="button" className="link" onClick={() => setRestart(true)}>
                Start Again
              </button>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
