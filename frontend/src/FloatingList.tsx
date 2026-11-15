import { type CSSProperties, type ReactNode, type RefObject, useLayoutEffect, useState } from "react";
import { createPortal } from "react-dom";

/** The open list of a type-to-search picker (Combobox, PIN, HSN). It is drawn on the page itself, just
 * under its field (or above it when there is no room below), so no box, table or folding section the
 * field sits in can cut it off or scroll the field out of sight (Sidharth, 2026-11-15: the item picker
 * in the purchase order's Items box showed only one item). It follows the field when the page scrolls
 * and keeps the field's own text size. */
export function FloatingList(props: {
  anchor: RefObject<HTMLElement>;
  listRef?: RefObject<HTMLUListElement>;
  children: ReactNode;
}) {
  const [place, setPlace] = useState<CSSProperties | null>(null);

  useLayoutEffect(() => {
    const field = props.anchor.current;
    if (!field) return;
    const input = field.querySelector("input") ?? field;
    const update = () => {
      const r = input.getBoundingClientRect();
      // Hide the list when its field has scrolled out of sight.
      if (r.bottom < 0 || r.top > window.innerHeight) {
        setPlace({ display: "none" });
        return;
      }
      const below = window.innerHeight - r.bottom - 8;
      const above = r.top - 8;
      const up = below < 200 && above > below;
      setPlace({
        left: r.left,
        width: r.width,
        fontSize: getComputedStyle(input).fontSize,
        maxHeight: Math.max(120, Math.min(280, up ? above : below)),
        ...(up ? { bottom: window.innerHeight - r.top + 2 } : { top: r.bottom + 2 }),
      });
    };
    update();
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [props.anchor]);

  return createPortal(
    <ul
      className="combo-list floating"
      role="listbox"
      ref={props.listRef}
      style={place ?? { visibility: "hidden" }}
      // Clicking the list (or its scroll bar) must not take the focus from the field, or the list closes.
      onMouseDown={(e) => e.preventDefault()}
    >
      {props.children}
    </ul>,
    document.body,
  );
}
