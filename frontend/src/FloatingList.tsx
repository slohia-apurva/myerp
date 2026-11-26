import { type CSSProperties, type ReactNode, type RefObject, useLayoutEffect, useState } from "react";
import { createPortal } from "react-dom";

/** The open list of a type-to-search picker (Combobox, PIN, HSN). It is drawn on the page itself, just
 * under its field (or above it when there is no room below), so no box, table or folding section the
 * field sits in can cut it off or scroll the field out of sight (Sidharth, 2026-11-15: the item picker
 * in the purchase order's Items box showed only one item). It is placed on the page, not the screen, so it
 * stays under its field when the page scrolls or a phone keyboard slides the view, and keeps the
 * field's own text size. */
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
      // The part of the page on screen. On an iPhone the keyboard covers the lower part and the
      // page can slide under it, so this is the visual viewport, not the window (Sidharth,
      // 2026-11-26: "the dropdown keeps floating around the screen").
      const vv = window.visualViewport;
      const viewTop = vv ? vv.offsetTop : 0;
      const viewBottom = vv ? vv.offsetTop + vv.height : window.innerHeight;
      // Hide the list when its field has scrolled out of sight.
      if (r.bottom < viewTop || r.top > viewBottom) {
        setPlace({ display: "none" });
        return;
      }
      const below = viewBottom - r.bottom - 8;
      const above = r.top - viewTop - 8;
      const up = below < 200 && above > below;
      // Placed on the page (not on the screen), so it moves with its field however the page
      // or the phone's view slides.
      setPlace({
        left: r.left + window.scrollX,
        width: r.width,
        fontSize: getComputedStyle(input).fontSize,
        maxHeight: Math.max(120, Math.min(280, up ? above : below)),
        top: (up ? r.top - 2 : r.bottom + 2) + window.scrollY,
        ...(up ? { transform: "translateY(-100%)" } : {}),
      });
    };
    update();
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    window.visualViewport?.addEventListener("resize", update);
    window.visualViewport?.addEventListener("scroll", update);
    return () => {
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("scroll", update);
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
