import { useEffect, useState } from "react";
import { Logo, PageHeader } from "../Brand";
import { MANUAL, type Chapter } from "./manual";

/** The manual chapter for the screen at this hash, for the Help link. */
export function helpTopicFor(hash: string): string {
  const [page, id, sub] = hash.replace(/^#\/?/, "").split("/");
  if (page === "users" || page === "roles" || page === "credit-terms" || page === "units" || page === "items" || page === "hsn" || page === "reset")
    return page;
  if (page !== "companies") return "start";
  if (!id) return "companies";
  if (sub === "ledgers") return "ledgers";
  if (sub === "groups") return "ledger-groups";
  if (sub === "branches" || sub === "certificates" || sub === "modules") return sub;
  return "companies";
}

function ChapterView({ chapter, n }: { chapter: Chapter; n: number }) {
  return (
    <article className="help-chapter" id={`help-${chapter.id}`}>
      <h2>
        {n}. {chapter.title}
      </h2>
      <p className="help-summary">{chapter.summary}</p>
      {chapter.body}
    </article>
  );
}

export function HelpPage({ topic }: { topic?: string }) {
  const index = Math.max(
    0,
    MANUAL.findIndex((c) => c.id === topic),
  );
  const chapter = MANUAL[index];
  // "Print manual" shows every chapter, prints, then goes back.
  const [whole, setWhole] = useState(false);
  useEffect(() => {
    if (!whole) return;
    const done = () => setWhole(false);
    window.addEventListener("afterprint", done);
    window.print();
    return () => window.removeEventListener("afterprint", done);
  }, [whole]);

  return (
    <section className="page help">
      <PageHeader
        title="Help"
        sub="How to use MyERP, screen by screen"
        actions={
          <>
            <button className="secondary" onClick={() => window.print()}>
              Print this page
            </button>
            <button onClick={() => setWhole(true)}>Print manual</button>
          </>
        }
      />
      <div className="help-layout">
        <nav className="help-toc" aria-label="Contents">
          <h3>Contents</h3>
          <ol>
            {MANUAL.map((c) => (
              <li key={c.id}>
                <a href={`#/help/${c.id}`} className={c.id === chapter.id ? "active" : ""}>
                  {c.title}
                </a>
              </li>
            ))}
          </ol>
        </nav>
        <div className="help-body">
          {whole ? (
            <>
              <div className="help-cover">
                <Logo size={48} />
                <h1>User manual</h1>
                <p>Printed {new Date().toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}</p>
                <ol>
                  {MANUAL.map((c) => (
                    <li key={c.id}>
                      {c.title}: <span className="small">{c.summary}</span>
                    </li>
                  ))}
                </ol>
              </div>
              {MANUAL.map((c, i) => (
                <ChapterView key={c.id} chapter={c} n={i + 1} />
              ))}
            </>
          ) : (
            <>
              <ChapterView chapter={chapter} n={index + 1} />
              <nav className="help-pager" aria-label="Chapters">
                {index > 0 && <a href={`#/help/${MANUAL[index - 1].id}`}>‹ {MANUAL[index - 1].title}</a>}
                <span />
                {index < MANUAL.length - 1 && <a href={`#/help/${MANUAL[index + 1].id}`}>{MANUAL[index + 1].title} ›</a>}
              </nav>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
