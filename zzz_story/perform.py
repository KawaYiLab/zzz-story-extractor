"""Scan Perform CAB assets for dialogueKey -> voice source links."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .mhy1 import MhyError, extract_mhy_files

SOURCE_RE = re.compile(
    r"^(?:VO_[A-Za-z0-9_./-]+/)?"
    r"(?:GalGame|Chat|Bubble|BubbleStory|ChatAudio|ChatPlus|BubbleNpc)_[A-Za-z0-9_-]+$",
    re.IGNORECASE,
)
DIALOGUE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def utf16_ascii_strings(data: bytes) -> list[str]:
    """Extract UTF-16LE strings of ASCII characters, as done by the reference parser."""
    values: list[str] = []
    offset = 0
    length = len(data)
    while offset + 7 < length:
        start = offset
        while offset + 1 < length and 0x20 <= data[offset] <= 0x7E and data[offset + 1] == 0:
            offset += 2
        if offset - start >= 8:
            values.append(data[start:offset].decode("utf-16le", errors="replace"))
        offset = offset if offset != start else offset + 1
    return values


def dialogue_links_from_cab(cab: bytes):
    values = utf16_ascii_strings(cab)
    index = 0
    while index + 1 < len(values):
        if values[index] != "dialogueKey" or not DIALOGUE_KEY_RE.match(values[index + 1]):
            index += 1
            continue
        text_id = values[index + 1]
        for cursor in range(index + 2, min(index + 12, len(values) - 1)):
            if values[cursor] == "dialogueKey":
                break
            if values[cursor] not in ("externalVoiceKey", "voiceKey"):
                continue
            source = values[cursor + 1]
            if SOURCE_RE.match(source):
                yield source, text_id
            break
        index += 1


def avatar_links_from_cab(cab: bytes):
    """Yield ``(dialogueKey, avatarName)`` for nodes that carry a speaker.

    Perform assets serialize a node's ``avatarName`` immediately before its
    ``dialogueKey``.  The avatar value is usually a TextMap key
    (``Avatar_...``, ``GalNPC...``, ``MainChat_..._Name01``), so it resolves to
    a display name even when the line has no voice key.
    """
    values = utf16_ascii_strings(cab)
    last_avatar: str | None = None
    index = 0
    while index + 1 < len(values):
        value = values[index]
        following = values[index + 1]
        if value == "avatarName" and following and following not in ("nodeMark", "backgroundKey"):
            last_avatar = following
        elif value == "dialogueKey" and DIALOGUE_KEY_RE.match(following):
            if last_avatar:
                yield following, last_avatar
                last_avatar = None
        index += 1


def option_keys_from_cab(cab: bytes):
    """Yield dialogue option text keys serialized in transition lists."""
    values = utf16_ascii_strings(cab)
    limit = len(values) - 1
    for index in range(limit):
        if values[index] == "textKey" and DIALOGUE_KEY_RE.match(values[index + 1]):
            yield values[index + 1]


def scan_cab(cab: bytes):
    """Scan one CAB after decoding its UTF-16 strings exactly once.

    Perform blocks contain three independently useful relationships.  The
    old scanner called :func:`utf16_ascii_strings` once for each relationship,
    tripling the allocation and UTF-16 decoding cost for every CAB.  Keep the
    same local parsing rules as the public helpers, but share the decoded
    string table for the block scanner.

    Returns ``(voice_links, avatar_links, option_keys)`` as lists.  The
    public generator helpers above remain available for callers that only
    need one relationship.
    """
    values = utf16_ascii_strings(cab)
    links: list[tuple[str, str]] = []
    avatars: list[tuple[str, str]] = []
    options: list[str] = []
    last_avatar: str | None = None
    limit = len(values) - 1

    for index, value in enumerate(values):
        following = values[index + 1] if index < limit else ""

        if value == "avatarName" and following and following not in ("nodeMark", "backgroundKey"):
            last_avatar = following
        elif value == "dialogueKey" and DIALOGUE_KEY_RE.match(following):
            text_id = following
            if last_avatar:
                avatars.append((text_id, last_avatar))
                last_avatar = None

            for cursor in range(index + 2, min(index + 12, limit)):
                if values[cursor] == "dialogueKey":
                    break
                if values[cursor] not in ("externalVoiceKey", "voiceKey"):
                    continue
                source = values[cursor + 1]
                if SOURCE_RE.match(source):
                    links.append((source, text_id))
                break
        elif value == "textKey" and DIALOGUE_KEY_RE.match(following):
            options.append(following)

    return links, avatars, options


@dataclass
class ScanStats:
    blocks: int = 0
    mhy_files: int = 0
    cab_files: int = 0
    links: int = 0
    sources: int = 0
    text_ids: int = 0
    avatar_links: int = 0
    avatar_values: int = 0
    option_keys: int = 0
    graphs: dict = field(default_factory=dict)
    graph_errors: dict = field(default_factory=dict)


def scan_perform_blocks(
    block_paths: list[Path],
    graph_paths: set[str] | None = None,
) -> tuple[dict[str, set[str]], dict[str, str], set[str], ScanStats]:
    from .perform_graph import asset_hash, graphs_from_cab
    wanted = {asset_hash(path): path for path in graph_paths or set()}
    graph_marker = "storySections".encode("utf-16le")
    source_to_text: dict[str, set[str]] = {}
    avatar_to_text: dict[str, str] = {}
    option_keys: set[str] = set()
    ambiguous_avatar: set[str] = set()
    stats = ScanStats()
    for number, path in enumerate(block_paths, 1):
        stats.blocks += 1
        print(f"  perform block {number}/{len(block_paths)}: {path.name} ({path.stat().st_size / 1e6:.1f} MB)")
        block = path.read_bytes()
        try:
            files = extract_mhy_files(block)
        except MhyError as exc:
            print(f"    skipped: {exc}")
            continue
        stats.mhy_files += 1
        for cab in files:
            stats.cab_files += 1
            if wanted and graph_marker in cab:
                try:
                    stats.graphs.update(graphs_from_cab(cab, wanted))
                except (ValueError, KeyError, UnicodeDecodeError) as exc:
                    # Unknown layouts remain available to the legacy scanner;
                    # never turn a parse failure into evidence of unused text.
                    stats.graph_errors[f"{path.name}:cab{stats.cab_files}"] = str(exc)
            links, avatars, options = scan_cab(cab)
            for source, text_id in links:
                stats.links += 1
                source_to_text.setdefault(source, set()).add(text_id)
            for text_id, avatar_name in avatars:
                stats.avatar_links += 1
                previous = avatar_to_text.get(text_id)
                if previous is None:
                    avatar_to_text[text_id] = avatar_name
                    stats.avatar_values += 1
                elif previous != avatar_name:
                    ambiguous_avatar.add(text_id)
            for opt_key in options:
                if opt_key not in option_keys:
                    option_keys.add(opt_key)
                    stats.option_keys += 1
    for text_id in ambiguous_avatar:
        avatar_to_text.pop(text_id, None)
    stats.sources = len(source_to_text)
    stats.text_ids = len({text_id for values in source_to_text.values() for text_id in values})
    return source_to_text, avatar_to_text, option_keys, stats
