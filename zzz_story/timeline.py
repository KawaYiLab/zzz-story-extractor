"""Read ChatPlus timeline clips and link their numbered main-text copies."""

from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path

from .catalog import find_resource_block, map_story_assets
from .clean import clean_text
from .mhy1 import extract_mhy_files
from .perform import utf16_ascii_strings

VOICE_RE = re.compile(r"^ChatPlusTimeline_(Chapter\d+)_([A-Za-z0-9]+)_(\d+)_(\d+)$")
TEXT_RE = re.compile(r"^(TL_.+)_(\d+)$")
MAIN_RE = re.compile(r"^Main_GalGame_(Chapter\d+)_(\d+)_(\d+)$")


@dataclass(frozen=True)
class TimelineClip:
    avatar: str
    text_key: str
    voice_key: str
    timeline: str = ""


def _unity_string(raw: bytes, offset: int) -> tuple[str, int]:
    if offset + 4 > len(raw):
        raise ValueError("truncated Unity string")
    size = struct.unpack_from("<I", raw, offset)[0]
    end = offset + 4 + size
    if end > len(raw):
        raise ValueError("Unity string exceeds object")
    return raw[offset + 4:end].decode("utf-8"), (end + 3) & ~3


def clip_from_raw(raw: bytes) -> TimelineClip | None:
    """MonoBehaviour header followed by three aligned Unity strings.

    Script identity is checked by the caller. Cloned clip names have the same
    layout; filtering on the object name alone loses several real lines.
    """
    try:
        _, offset = _unity_string(raw, 28)
        avatar, offset = _unity_string(raw, offset)
        text_key, offset = _unity_string(raw, offset)
        voice_key, _ = _unity_string(raw, offset)
    except (ValueError, UnicodeDecodeError):
        return None
    if not TEXT_RE.fullmatch(text_key) or not VOICE_RE.fullmatch(voice_key):
        return None
    return TimelineClip(avatar, text_key, voice_key)


def clips_from_cab(cab: bytes) -> list[TimelineClip]:
    import UnityPy

    env = UnityPy.load(cab)
    scripts = {obj.path_id: obj.read().m_ClassName for obj in env.objects if obj.class_id == 115}
    timelines = set()
    for obj in env.objects:
        if obj.class_id != 114:
            continue
        raw = obj.get_raw_data()
        if len(raw) >= 32 and scripts.get(struct.unpack_from("<q", raw, 20)[0]) == "TimelineAsset":
            name, _ = _unity_string(raw, 28)
            if name.endswith("_Timeline"):
                timelines.add(name[:-len("_Timeline")])
    timeline = next(iter(timelines)) if len(timelines) == 1 else ""
    result = []
    for obj in env.objects:
        if obj.class_id != 114:
            continue
        raw = obj.get_raw_data()
        if len(raw) < 32 or struct.unpack_from("<i", raw, 16)[0] != 0:
            continue
        if scripts.get(struct.unpack_from("<q", raw, 20)[0]) != "ChatPlusDialogClip":
            continue
        clip = clip_from_raw(raw)
        if clip:
            result.append(TimelineClip(clip.avatar, clip.text_key, clip.voice_key, timeline))
    return result


def timeline_asset_paths(perform: object, files) -> set[str]:
    names: set[str] = set()
    for row in perform.get("IAEFFFFLKNB", []) if isinstance(perform, dict) else []:
        for field in ("BCKKFAEFDPP", "LGJCAHIEBBK"):
            value = row.get(field)
            if isinstance(value, str) and value.startswith("TL_") and "ChatPlus" in value:
                names.add(value)
    paths: set[str] = set()
    for cab in files:
        if "MoleMole.ChatPlusTimelineData".encode("utf-16le") not in cab:
            continue
        for value in utf16_ascii_strings(cab):
            if not value.startswith("Assets/NapResources/CutScene_Runtime/ChatPlusTimeline/"):
                continue
            if Path(value).stem in names and value.endswith(".prefab"):
                paths.add(value[len("Assets/NapResources/"):])
    return paths


def scan_timeline_clips(game_dir: Path, catalog, perform: object) -> list[TimelineClip]:
    """Locate timeline configuration from the manifest, then resolve prefabs.

    Tag 2 contains serialized configuration. No filename or version-specific
    block ID is pinned; patched paths take priority over the base install.
    """
    root = game_dir / "ZenlessZoneZero_Data"
    config_paths: dict[str, Path] = {}
    for rel in ("StreamingAssets/res_version", "Persistent/res_version_persist"):
        manifest = root / rel
        if not manifest.is_file():
            continue
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        for entry in payload.get("files", []):
            remote = entry.get("remoteName", "")
            if 2 not in (entry.get("tags") or []) or not re.fullmatch(r"Blocks/\d+\.blk", remote):
                continue
            path = manifest.parent / remote
            if path.is_file():
                config_paths[remote] = path
    paths: set[str] = set()
    for number, path in enumerate(config_paths.values(), 1):
        if number % 100 == 0:
            print(f"  timeline config block {number}/{len(config_paths)}")
        paths.update(timeline_asset_paths(perform, extract_mhy_files(path.read_bytes())))
    by_block, matched = map_story_assets(catalog, paths)
    print(f"  timeline prefabs: {len(paths)} paths, {matched} matched, {len(by_block)} blocks")
    result: set[TimelineClip] = set()
    for block_id in sorted(by_block):
        path = find_resource_block(game_dir, block_id)
        if not path:
            continue
        for cab in extract_mhy_files(path.read_bytes()):
            if b"ChatPlusDialogClip" in cab:
                result.update(clips_from_cab(cab))
    return sorted(result, key=lambda clip: (clip.text_key, clip.voice_key, clip.avatar, clip.timeline))


def link_main_copies(clips: list[TimelineClip], text_map, perform: object) -> dict[str, dict]:
    """Accept a numbered namespace only when its text alignment is verified.

    Shared timeline keys can have two main copies. An adjacent identical copy
    absent from the timeline is linked to the used key, not treated as a new
    utterance. Distinct clips (including repeated NPC pauses) remain distinct.
    """
    routes: dict[tuple[str, str], set[str]] = {}
    for row in perform.get("IAEFFFFLKNB", []) if isinstance(perform, dict) else []:
        for field, side in (("BCKKFAEFDPP", "M"), ("LGJCAHIEBBK", "F")):
            name = row.get(field)
            if isinstance(name, str):
                routes.setdefault((str(row.get("PFOAJKNPCHL")), name), set()).add(side)
    groups: dict[tuple[str, str, str], list[TimelineClip]] = {}
    for clip in clips:
        voice = VOICE_RE.fullmatch(clip.voice_key)
        text = TEXT_RE.fullmatch(clip.text_key)
        if voice and text and (voice[3], clip.timeline) in routes:
            groups.setdefault((voice[1], voice[3], text[1]), []).append(clip)
    mains: dict[tuple[str, str], dict[int, str]] = {}
    for key in text_map.keys():
        match = MAIN_RE.fullmatch(key)
        if match:
            mains.setdefault((match[1], match[2]), {})[int(match[3])] = key
    result: dict[str, dict] = {}
    for (chapter, scene, prefix), group in groups.items():
        declared = {name for (route_scene, name) in routes if route_scene == scene and name.startswith("TL_")}
        if not declared <= {clip.timeline for clip in group}:
            # A missing route resource is not evidence that its text is unused.
            continue
        numbered = mains.get((chapter, scene), {})
        by_number: dict[int, list[TimelineClip]] = {}
        for clip in group:
            by_number.setdefault(int(TEXT_RE.fullmatch(clip.text_key)[2]), []).append(clip)
        comparable = [(n, values[0]) for n, values in by_number.items() if n in numbered]
        exact = sum(clean_text(text_map.get(numbered[n]), "M").text ==
                    clean_text(text_map.get(clip.text_key), "M").text for n, clip in comparable)
        # Allow a small number of independently updated/merged text values,
        # but never infer namespace identity from short or weak matches.
        if len(comparable) < 10 or exact / len(comparable) < 0.9:
            continue
        for n, values in sorted(by_number.items()):
            key = numbered.get(n)
            if not key:
                continue
            avatars = {clip.avatar for clip in values}
            voices = {clip.voice_key for clip in values}
            sides = set()
            for clip in values:
                sides.update(routes[(scene, clip.timeline)])
            result[key] = {"text_key": values[0].text_key,
                           "avatar": next(iter(avatars)) if len(avatars) == 1 else None,
                           "voice_keys": sorted(voices), "sides": sorted(sides),
                           "timelines": sorted({clip.timeline for clip in values}),
                           "text_difference": clean_text(text_map.get(key), "M").text !=
                           clean_text(text_map.get(values[0].text_key), "M").text}
        for n, key in sorted(numbered.items()):
            if n in by_number:
                continue
            previous = numbered.get(n - 1)
            if previous not in result or result[previous].get("copy_of"):
                continue
            if result[previous]["sides"] == ["F", "M"] and text_map.get(previous) == text_map.get(key):
                result[key] = {**result[previous], "copy_of": previous}
    return result
