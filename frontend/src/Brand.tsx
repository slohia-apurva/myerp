import type { ReactNode } from "react";

/** The MyERP mark: a leaf-green rounded square with a white M. */
export function Mark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#2E9E62" />
      <path
        d="M8 22V10l8 7 8-7v12"
        fill="none"
        stroke="#FFFFFF"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Logo({ size = 28 }: { size?: number }) {
  return (
    <span className="logo">
      <Mark size={size} />
      <span className="wordmark">
        My<span>ERP</span>
      </span>
    </span>
  );
}

/**
 * The light green band at the top of every page: breadcrumbs, title,
 * a line of key facts and the page's main buttons.
 */
export function PageHeader(props: {
  title: ReactNode;
  crumbs?: { label: string; href: string }[];
  sub?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="band">
      <div className="band-inner">
        <div className="band-row">
          <div className="band-title">
            {props.crumbs && props.crumbs.length > 0 && (
              <nav className="crumbs" aria-label="Breadcrumb">
                {props.crumbs.map((c, i) => (
                  <span key={c.href}>
                    {i > 0 && " › "}
                    <a href={c.href}>{c.label}</a>
                  </span>
                ))}
              </nav>
            )}
            <h1>{props.title}</h1>
            {props.sub && <p className="band-sub">{props.sub}</p>}
          </div>
          {props.actions && <div className="buttons">{props.actions}</div>}
        </div>
        {props.children}
      </div>
    </header>
  );
}

/** A fold arrow: points right when closed, down when open. */
export function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 16 16"
      aria-hidden="true"
      style={{ transform: open ? "rotate(90deg)" : "none" }}
    >
      <path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/**
 * Open a tree to a chosen depth: "1" shows only the main groups, "All" shows everything.
 * `levels` is how many numbered levels to offer; `value` is the one last picked, if any.
 */
export function LevelPicker(props: { levels: number; value: number | null; onPick: (level: number) => void }) {
  const options = [...Array.from({ length: props.levels }, (_, i) => i + 1), Infinity];
  return (
    <span className="levels" role="group" aria-label="Show levels">
      <span className="small">Show levels</span>
      {options.map((n) => (
        <button
          key={n}
          type="button"
          className={props.value === n ? "active" : ""}
          aria-pressed={props.value === n}
          onClick={() => props.onPick(n)}
        >
          {n === Infinity ? "All" : n}
        </button>
      ))}
    </span>
  );
}

/** A titled box inside a form: the one way every screen groups its fields. */
export function Section(props: { title: string; children: React.ReactNode }) {
  return (
    <div className="panel-card">
      <h4>{props.title}</h4>
      {props.children}
    </div>
  );
}
