"""Cleaning of TextMap markup and protagonist-gender variants."""

from __future__ import annotations

import re
from dataclasses import dataclass


_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")
_LAYOUT_RE = re.compile(r"\{LAYOUT_([A-Z_]+)#([^{}]*)\}")


@dataclass
class CleanedText:
    text: str
    variants: dict[str, str] | None = None


def _split_variants(raw: str) -> tuple[list[tuple[str | None, str]], bool]:
    """Split into literal / M / F segments, preserving order.

    Example: ``前缀{M#甲}{F#乙}后缀`` becomes
    ``[(None, "前缀"), ("M", "甲"), ("F", "乙"), (None, "后缀")]``.
    """
    segments: list[tuple[str | None, str]] = []
    literal: list[str] = []
    found = False
    i = 0
    n = len(raw)
    while i < n:
        if i + 2 < n and raw[i] == "{" and raw[i + 1] in "MF" and raw[i + 2] == "#":
            depth = 0
            j = i
            while j < n:
                if raw[j] == "{":
                    depth += 1
                elif raw[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j < n:
                if literal:
                    segments.append((None, "".join(literal)))
                    literal = []
                segments.append((raw[i + 1], raw[i + 3:j]))
                found = True
                i = j + 1
                continue
        literal.append(raw[i])
        i += 1
    if literal:
        segments.append((None, "".join(literal)))
    return segments, found


def _choose_layout(raw: str) -> str:
    chosen: list[str] | None = None
    fallback: list[str] | None = None

    def repl(match: re.Match[str]) -> str:
        nonlocal chosen, fallback
        kind, value = match.group(1), match.group(2)
        if fallback is None:
            fallback = []
        fallback.append(value)
        if kind == "MOBILE":
            if chosen is None:
                chosen = []
            chosen.append(value)
        return ""

    stripped = _LAYOUT_RE.sub(repl, raw)
    if chosen is not None:
        return stripped + "".join(chosen)
    if fallback is not None:
        return stripped + "".join(fallback)
    return stripped


def _strip_markup(raw: str) -> str:
    text = _TAG_RE.sub("", raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _render(segments: list[tuple[str | None, str]], gender: str) -> str:
    return "".join(value for kind, value in segments if kind is None or kind == gender)


def clean_text(raw: str, protagonist: str = "F") -> CleanedText:
    """Clean one TextMap value.

    ``protagonist`` is ``F`` (铃) or ``M`` (哲).  If both variants differ they
    are returned in ``variants`` so no text is lost.
    """
    if not isinstance(raw, str) or not raw:
        return CleanedText("")

    segments, found = _split_variants(raw)
    if not found:
        return CleanedText(_strip_markup(_choose_layout(raw)))

    texts: dict[str, str] = {}
    for gender in ("M", "F"):
        texts[gender] = _strip_markup(_choose_layout(_render(segments, gender)))

    if texts["M"] == texts["F"]:
        return CleanedText(texts.get(protagonist, texts["F"]))

    variants = {gender: value for gender, value in texts.items() if value}
    chosen = texts.get(protagonist) or texts.get("M") or texts.get("F") or ""
    return CleanedText(chosen, variants if len(set(variants.values())) > 1 else None)
