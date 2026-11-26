"""Parse TextMap keys into chapter / scene / line components."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .clean import clean_text
from .dedupe import paired_route_order, referenced_sides


@dataclass(frozen=True)
class ParsedKey:
    key: str
    family: str
    chapter_token: str
    scene: str
    kind: str  # line | name | source_variant | other
    line_no: int | None = None
    sub_no: int | None = None
    variant: str | None = None

    @property
    def route_variant(self) -> str | None:
        # The source scene spelling is part of published line IDs (e.g. 0059F).
        return self.variant or split_scene_variant(self.scene)[1]


_LINE_RE = re.compile(r"^(\d+)(?:_(\d+))?([MF])?$")
_NAME_RE = re.compile(r"(?:^|_)(?:Name|name)(?:_?(\d+))?([MF])?$")
_OPTION_RE = re.compile(r"^Option(\d+)_(\d+)([MF])?$", re.IGNORECASE)
# Season-1 cutscenes: ``03_Option1_02F_Main`` (line 3, option group 1, entry 2).
_LEGACY_OPTION_RE = re.compile(r"^(\d+)_Option(\d+)(?:_(\d+))?([MF])?(?:_Main)?$", re.IGNORECASE)
# Season-1 cutscenes predate the ``Main_`` prefix: ``GalGame_Chapter050_010_001``.
# Only numeric chapter tokens are mainline; ``GalGame_ChapterMana`` is an
# agent story and is handled by ``extras.py``.
LEGACY_GALGAME_RE = re.compile(r"^GalGame_(Chapter\d+)_([^_]+)_(.+)$")


def split_scene_variant(scene: str) -> tuple[str, str | None]:
    if re.fullmatch(r"(?:Inlevel_)?\d+[MF]", scene):
        return scene[:-1], scene[-1]
    return scene, None


def source_gender_pairs(variants: dict[str, str | None], text_map, speaker_index=None) -> dict[str, tuple[str, str]]:
    """Pair nonempty exported sources with the same spelling except for a route marker.

    The older tables use an unmarked key for Wise and an F on the line,
    choice, cast name or scene for Belle. Prefer an explicit M/F pair when
    present. An ambiguous or missing counterpart leaves all candidates intact.
    """
    alternatives: dict[str, list[str]] = {}
    for key, variant in variants.items():
        if variant != "F":
            continue
        markers = list(re.finditer(r"(?:(?<=\d)|(?<=[Nn]ame))F(?=_|$)", key))
        if len(markers) != 1:
            continue
        pos = markers[0].start()
        male = key[:pos] + "M" + key[pos + 1:]
        if variants.get(male) != "M":
            male = key[:pos] + key[pos + 1:]
            if male not in variants or variants[male] is not None:
                continue
        if clean_text(text_map.get(key), "F").text and clean_text(text_map.get(male), "M").text:
            alternatives.setdefault(male, []).append(key)

    def sides(key: str) -> set[str]:
        info = speaker_index.lookup(key) if speaker_index else None
        return referenced_sides(info.perform, info.timeline) if info else set()

    pairs = {}
    for male, females in alternatives.items():
        if len(females) == 1:
            female = females[0]
            order = paired_route_order(sides(male), sides(female))
            if order:
                pairs[male] = (female, order[0])
                pairs[female] = (male, order[1])
    return pairs


def _parse_suffix(suffix: str) -> tuple[str, int | None, int | None, str | None]:
    if not suffix:
        return ("other", None, None, None)

    # Names are not dialogue lines; they are collected as scene cast.
    if suffix.startswith(("Name", "name")) or "_Name" in suffix or "_name" in suffix:
        match = _NAME_RE.search(suffix)
        variant = match.group(2) if match else None
        return ("name", None, None, variant)

    match = _LINE_RE.match(suffix)
    if match:
        return ("line", int(match.group(1)), int(match.group(2)) if match.group(2) else None, match.group(3))
    match = _OPTION_RE.match(suffix)
    if match:
        return ("line", int(match.group(2)), int(match.group(1)), match.group(3))
    match = _LEGACY_OPTION_RE.match(suffix)
    if match:
        sub_no = int(match.group(2)) * 100 + int(match.group(3) or 0)
        return ("line", int(match.group(1)), sub_no, match.group(4))
    # This is an auxiliary source value, not a second playback event. Keep
    # its identity separate so it can be audited without renumbering _01.
    if suffix.endswith("_Gender"):
        match = _LINE_RE.fullmatch(suffix[:-len("_Gender")])
        if match:
            return ("source_variant", int(match.group(1)),
                    int(match.group(2)) if match.group(2) else None, "Gender")
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


def _scene_key(key: str, family: str, chapter: str, scene: str, suffix: str) -> ParsedKey:
    kind, line_no, sub_no, variant = _parse_suffix(suffix)
    return ParsedKey(key, family, chapter, scene, kind, line_no, sub_no, variant)


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
        return _scene_key(key, family, *split)

    match = LEGACY_GALGAME_RE.match(key)
    if match:
        return _scene_key(key, "GalGame", *match.groups())

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
        return _scene_key(key, "MainChat", chapter, scene, suffix)

    if key.startswith("Comic_"):
        return ParsedKey(key, "Comic", "", key[len("Comic_"):], "line", 0, None, None)

    if key.startswith("CS_"):
        parts = key[3:].split("_")
        if len(parts) >= 3:
            ch_raw, sc, ln_raw = parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            ch_raw, sc, ln_raw = parts[0], parts[1], "0"
        else:
            ch_raw, sc, ln_raw = "Other", key, "0"
        line_no = int(re.sub(r"\D", "", ln_raw) or "0")
        return ParsedKey(key, "CS", ch_raw, sc, "line", line_no, None, None)

    return None


def natural_scene_key(scene: str) -> tuple[int, str]:
    """Sort numeric scenes numerically, keep non-numeric scenes after them."""
    if scene.isdigit():
        return (0, f"{int(scene):012d}")
    return (1, scene)
