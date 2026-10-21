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
    # Layout variants occur in adjacent groups; select each group at its
    # original location instead of appending all selected text at the end.
    group_re = re.compile(r"(?:\{LAYOUT_[A-Z_]+#[^{}]*\})+")
    def choose(match: re.Match[str]) -> str:
        variants = _LAYOUT_RE.findall(match.group(0))
        mobile = [value for kind, value in variants if kind == "MOBILE"]
        if mobile:
            return "".join(mobile)
        return variants[0][1] if variants else match.group(0)
    return group_re.sub(choose, raw)


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
