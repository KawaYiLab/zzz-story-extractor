"""Parse TextMap keys into chapter / scene / line components."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedKey:
    key: str
    family: str
    chapter_token: str
    scene: str
    kind: str  # line | name | other
    line_no: int | None = None
    sub_no: int | None = None
    variant: str | None = None


_LINE_RE = re.compile(r"^(\d+)(?:_(\d+))?([MF])?$")
_NAME_RE = re.compile(r"^(?:Name|name)(?:_?(\d+))?([MF])?$")


def _parse_suffix(suffix: str) -> tuple[str, int | None, int | None, str | None]:
    if not suffix:
        return ("other", None, None, None)

    # Names are not dialogue lines; they are collected as scene cast.
    if suffix.startswith(("Name", "name")):
        match = _NAME_RE.match(suffix)
        variant = match.group(2) if match else None
        return ("name", None, None, variant)
    if "_Name" in suffix or "_name" in suffix:
        match = _NAME_RE.search(suffix)
        variant = match.group(2) if match else None
        return ("name", None, None, variant)

    match = _LINE_RE.match(suffix)
    if match:
        return ("line", int(match.group(1)), int(match.group(2)) if match.group(2) else None, match.group(3))
    return ("other", None, None, None)


def _split_scene_chapter(rest: str, family: str) -> tuple[str, str, str] | None:
    """Split ``ChapterXXX_scene_suffix`` into chapter, scene, suffix."""
    parts = rest.split("_", 2)
    if len(parts) < 3:
        return None
    chapter, scene, suffix = parts
    if family == "MainChat" and scene == "Inlevel":
        # MainChat_Chapter00_Inlevel_0002_Name01
        more = suffix.split("_", 1)
        if len(more) == 2:
            scene = f"Inlevel_{more[0]}"
            suffix = more[1]
    return chapter, scene, suffix


def parse_key(key: str) -> ParsedKey | None:
    if not key:
        return None

    if key.startswith("Main_"):
        rest = key[5:]
        if "_" not in rest:
            return None
        family, rest = rest.split("_", 1)
        split = _split_scene_chapter(rest, family)
        if not split:
            return None
        chapter, scene, suffix = split
        kind, line_no, sub_no, variant = _parse_suffix(suffix)
        return ParsedKey(key, family, chapter, scene, kind, line_no, sub_no, variant)

    if key.startswith("MainChat_"):
        rest = key[len("MainChat_"):]
        if "_" not in rest:
            return None
        chapter, rest = rest.split("_", 1)
        if chapter == "StoreNPC":
            return None
        if rest.startswith("Inlevel_"):
            pieces = rest.split("_", 2)
            if len(pieces) < 3:
                return None
            scene = f"Inlevel_{pieces[1]}"
            suffix = pieces[2]
        else:
            if "_" not in rest:
                return None
            scene, suffix = rest.split("_", 1)
        kind, line_no, sub_no, variant = _parse_suffix(suffix)
        return ParsedKey(key, "MainChat", chapter, scene, kind, line_no, sub_no, variant)

    if key.startswith("Comic_"):
        return ParsedKey(key, "Comic", "", key[len("Comic_"):], "line", 0, None, None)

    if key.startswith("CS_"):
        return ParsedKey(key, "CS", "CS", key, "line", 0, None, None)

    return None


def natural_scene_key(scene: str) -> tuple[int, str]:
    """Sort numeric scenes numerically, keep non-numeric scenes after them."""
    if scene.isdigit():
        return (0, f"{int(scene):012d}")
    return (1, scene)
