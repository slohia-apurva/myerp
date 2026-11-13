"""Formatted text kept in a few fields (the item's sales and purchase
descriptions): bold, italic, underline, lists, font and size.

The browser's editor sends HTML, and anything typed or pasted into it could
carry scripts or odd markup, so every save runs `clean` first: only the tags,
fonts and sizes listed below survive, and every other tag is dropped (its text
is kept; scripts and styles are dropped whole). `to_text` and `from_text` turn
the same value to and from plain text, for Excel and for places with no
formatting."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

TAGS = {"b", "strong", "i", "em", "u", "s", "br", "p", "div", "ul", "ol", "li", "span"}
VOID = {"br"}
DROP_WHOLE = {"script", "style", "template", "iframe", "object", "embed", "head", "title"}
FONTS = {
    "arial",
    "georgia",
    "times new roman",
    "courier new",
    "verdana",
    "tahoma",
    "trebuchet ms",
}
SIZES = {"x-small", "small", "medium", "large", "x-large", "xx-large"}
MAX_LENGTH = 5000
_BLOCK_END = re.compile(r"</(p|div|li)>|<br\s*/?>", re.I)


def _style(value: str) -> str:
    """Keep only a font-family from FONTS and a font-size from SIZES."""
    kept = []
    for part in (value or "").split(";"):
        name, _, val = part.partition(":")
        name, val = name.strip().lower(), val.strip().strip("'\"").lower()
        if name == "font-family":
            first = val.split(",")[0].strip().strip("'\"")
            if first in FONTS:
                kept.append(f"font-family: {first}")
        elif name == "font-size" and val in SIZES:
            kept.append(f"font-size: {val}")
    return "; ".join(kept)


class _Cleaner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in DROP_WHOLE:
            self.skip += 1
            return
        if self.skip or tag not in TAGS:
            return
        if tag in VOID:
            self.out.append("<br>")
            return
        style = _style(dict(attrs).get("style", "")) if tag == "span" else ""
        self.out.append(f'<span style="{style}">' if style else f"<{tag}>")
        self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag == "br" and not self.skip:
            self.out.append("<br>")

    def handle_endtag(self, tag):
        if tag in DROP_WHOLE:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or tag not in TAGS or tag in VOID or tag not in self.stack:
            return
        while self.stack:  # close anything left open inside it
            top = self.stack.pop()
            self.out.append(f"</{top}>")
            if top == tag:
                break

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html.escape(data, quote=False))

    def result(self) -> str:
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")
        return "".join(self.out)


def to_text(value: str) -> str:
    """The same text with the formatting taken off, one line per paragraph."""
    text = _BLOCK_END.sub("\n", value or "")
    text = re.sub(r"<[^>]*>", "", text)
    lines = [line.rstrip() for line in html.unescape(text).splitlines()]
    return "\n".join(lines).strip()


def from_text(text: str) -> str:
    """Plain text as the formatted form: characters escaped, line breaks kept."""
    escaped = html.escape((text or "").strip(), quote=False)
    return re.sub(r"\r\n|\r|\n", "<br>", escaped)


def clean(value: str) -> str:
    """The value with everything outside the allowed list removed; an empty
    editor ("<br>", "<div></div>") comes back as ''."""
    parser = _Cleaner()
    parser.feed(value or "")
    parser.close()
    cleaned = parser.result().strip()
    return cleaned if to_text(cleaned) else ""
