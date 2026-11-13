import { useEffect, useRef } from "react";
import { Combobox } from "./Combobox";

/**
 * A small formatted-text editor: bold, italic, underline, lists, font and size.
 * It gives back HTML; the server cleans that (core/richtext.py) before saving,
 * so only these formats are ever kept.
 */
const FONTS = ["Arial", "Georgia", "Times New Roman", "Courier New", "Verdana", "Tahoma", "Trebuchet MS"];
const SIZES: [string, string][] = [
  ["2", "Small"],
  ["3", "Normal"],
  ["4", "Large"],
  ["5", "Larger"],
  ["6", "Largest"],
];

export function RichText(props: {
  label: string;
  value: string;
  onChange: (html: string) => void;
  hint?: string;
  required?: boolean;
}) {
  const box = useRef<HTMLDivElement>(null);
  const saved = useRef<Range | null>(null);

  // Put the saved text in the box, but never while the person is typing (the cursor would jump).
  useEffect(() => {
    const el = box.current;
    if (el && el.innerHTML !== props.value) el.innerHTML = props.value;
  }, [props.value]);

  // Remember where the cursor or selection is, so a toolbar pick can act on it.
  useEffect(() => {
    const remember = () => {
      const sel = window.getSelection();
      const el = box.current;
      if (sel && sel.rangeCount > 0 && el && el.contains(sel.anchorNode)) saved.current = sel.getRangeAt(0).cloneRange();
    };
    document.addEventListener("selectionchange", remember);
    return () => document.removeEventListener("selectionchange", remember);
  }, []);

  const changed = () => {
    const el = box.current;
    if (!el) return;
    const empty = (el.textContent ?? "").trim() === "" && !el.querySelector("li");
    props.onChange(empty ? "" : el.innerHTML);
  };

  const run = (command: string, arg?: string, css = false) => {
    const el = box.current;
    if (!el) return;
    el.focus();
    const sel = window.getSelection();
    if (sel && saved.current) {
      sel.removeAllRanges();
      sel.addRange(saved.current);
    }
    document.execCommand("styleWithCSS", false, css ? "true" : "false");
    document.execCommand(command, false, arg);
    changed();
  };

  // Keep the selection in the box while a toolbar button is clicked.
  const keepSelection = (e: React.MouseEvent) => e.preventDefault();

  return (
    <div className="rte wide">
      <span className="rte-label">{props.label}{props.required && <span className="req-star"> *</span>}</span>
      <div className="rte-bar" role="toolbar" aria-label={`${props.label} formatting`}>
        <button type="button" className="link" aria-label="Bold" onMouseDown={keepSelection} onClick={() => run("bold")}>
          <b>B</b>
        </button>
        <button type="button" className="link" aria-label="Italic" onMouseDown={keepSelection} onClick={() => run("italic")}>
          <i>I</i>
        </button>
        <button type="button" className="link" aria-label="Underline" onMouseDown={keepSelection} onClick={() => run("underline")}>
          <u>U</u>
        </button>
        <button type="button" className="link" onMouseDown={keepSelection} onClick={() => run("insertUnorderedList")}>
          Bullets
        </button>
        <button type="button" className="link" onMouseDown={keepSelection} onClick={() => run("insertOrderedList")}>
          Numbers
        </button>
        <span className="rte-pick">
          <Combobox
            ariaLabel="Font"
            value=""
            empty="Font"
            options={FONTS.map((f) => ({ value: f, label: f }))}
            onChange={(v) => v && run("fontName", v, true)}
          />
        </span>
        <span className="rte-pick">
          <Combobox
            ariaLabel="Size"
            value=""
            empty="Size"
            options={SIZES.map(([value, label]) => ({ value, label }))}
            onChange={(v) => v && run("fontSize", v, true)}
          />
        </span>
        <button type="button" className="link" onMouseDown={keepSelection} onClick={() => run("removeFormat")}>
          Clear formatting
        </button>
      </div>
      <div
        ref={box}
        className="rte-box"
        contentEditable
        suppressContentEditableWarning
        role="textbox"
        aria-multiline="true"
        aria-label={props.label}
        onInput={changed}
        onPaste={(e) => {
          e.preventDefault();
          document.execCommand("insertText", false, e.clipboardData.getData("text/plain"));
        }}
      />
      {props.hint && <span className="small">{props.hint}</span>}
    </div>
  );
}
