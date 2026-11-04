"""Cleaning of TextMap markup and protagonist-gender variants."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TAG_RE = re.compile(r"</?([A-Za-z][A-Za-z0-9-]*)([^<>]*)>")
_NOPARSE_RE = re.compile(r"<noparse>(.*?)</noparse>", re.I | re.S)
_RUBY_RE = re.compile(r"<ruby\b[^>]*>(.*?)</ruby>", re.I | re.S)
_RT_RE = re.compile(r"<rt\b[^>]*>(.*?)</rt>", re.I | re.S)
_VARIANT_START = re.compile(r"\{(M|F|LAYOUT_[A-Z_]+)#")
# Remove presentation syntax only; literal placeholders such as <PLAYER>
# and comparisons must survive. Icon/action names remain available in raw_text.
_FORMAT_TAGS = frozenset({
    "color", "size", "b", "i", "u", "s", "sup", "sub", "alpha", "align",
    "allcaps", "lowercase", "uppercase", "cspace", "font", "font-weight",
    "indent", "line-height", "line-indent", "link", "margin", "mark",
    "material", "mspace", "nobr", "page", "pos", "rotate", "space", "sprite",
    "style", "voffset", "width", "quad", "term", "iconmap", "action", "ruby", "rt", "rp",
})


@dataclass
class CleanedText:
    text: str
    variants: dict[str, str] | None = None


def _segments(raw: str) -> list[tuple[str | None, str]]:
    """Split balanced variant tokens, including nested format placeholders."""
    ends, stack = {}, []
    for index, char in enumerate(raw):
        if char == "{":
            stack.append(index)
        elif char == "}" and stack:
            ends[stack.pop()] = index
    segments = []
    start = index = 0
    while index < len(raw):
        match = _VARIANT_START.match(raw, index)
        if not match:
            index += 1
            continue
        end = ends.get(index)
        if end is None:
            break  # Keep a malformed token verbatim for review.
        if start < index:
            segments.append((None, raw[start:index]))
        segments.append((match[1], raw[match.end():end]))
        start = index = end + 1
    if start < len(raw):
        segments.append((None, raw[start:]))
    return segments


def _render(raw: str, gender: str) -> str:
    if not _VARIANT_START.search(raw):
        return raw
    segments = _segments(raw)
    result = []
    index = 0
    while index < len(segments):
        kind, value = segments[index]
        if kind is None:
            result.append(value)
        elif kind in {"M", "F"}:
            if kind == gender:
                result.append(_render(value, gender))
        else:
            # Adjacent layouts represent alternatives at this exact position.
            layouts = [(kind, value)]
            while index + 1 < len(segments) and (segments[index + 1][0] or "").startswith("LAYOUT_"):
                index += 1
                layouts.append(segments[index])
            selected = next((text for layout, text in layouts if layout == "LAYOUT_MOBILE"), layouts[0][1])
            result.append(_render(selected, gender))
        index += 1
    return "".join(result)


def _strip_markup(raw: str) -> str:
    def ruby(match: re.Match[str]) -> str:
        base = _strip_markup(_RT_RE.sub("", match[1]))
        reading = "、".join(_strip_markup(value) for value in _RT_RE.findall(match[1]))
        return f"{base}（{reading}）" if base and reading and reading != base else base or reading

    def fragment(text: str) -> str:
        return _TAG_RE.sub(replace, _RUBY_RE.sub(ruby, text))

    def replace(match: re.Match[str]) -> str:
        name = match[1].lower()
        if name == "br":
            return "\n"
        return "" if name in _FORMAT_TAGS else match[0]

    parts = []
    start = 0
    for match in _NOPARSE_RE.finditer(raw):
        parts.extend((fragment(raw[start:match.start()]), match[1]))
        start = match.end()
    parts.append(fragment(raw[start:]))
    text = "".join(parts).replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_text(raw: str, protagonist: str = "F") -> CleanedText:
    """Render balanced layout/gender alternatives while retaining both genders."""
    if not isinstance(raw, str) or not raw:
        return CleanedText("")
    if not _VARIANT_START.search(raw):
        return CleanedText(_strip_markup(raw))
    texts = {gender: _strip_markup(_render(raw, gender)) for gender in ("M", "F")}
    variants = {gender: value for gender, value in texts.items() if value}
    chosen = texts.get(protagonist) or texts["M"] or texts["F"]
    return CleanedText(chosen, variants if len(set(variants.values())) > 1 else None)
