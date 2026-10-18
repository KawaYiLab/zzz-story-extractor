"""Parse the game's gzip resource catalog and map Perform assets to .blk blocks."""

from __future__ import annotations

import gzip
import re
import struct
from pathlib import Path

import xxhash

STORY_FAMILIES = {
    "GalGame",
    "Chat",
    "Bubble",
    "BubbleStory",
    "ChatAudio",
    "ChatPlus",
    "BubbleNpc",
}

_ASSET_RE = re.compile(r"Data/ScriptConfig/Perform/Data/([^/]+)/.*\.asset$", re.IGNORECASE)


def story_asset_paths(perform_payload: object) -> set[str]:
    """Collect story Perform asset paths from PerformTemplateTb.json."""
    found: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, str):
            match = _ASSET_RE.search(value)
            if match and match.group(1) in STORY_FAMILIES:
                found.add(match.group(0))
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)

    walk(perform_payload)
    return found


def find_catalog_block(game_dir: Path) -> Path:
    blocks = game_dir / "ZenlessZoneZero_Data" / "StreamingAssets" / "Blocks"
    candidates: list[Path] = []
    for path in blocks.glob("*.blk"):
        try:
            with path.open("rb") as handle:
                if handle.read(2) == b"\x1f\x8b":
                    candidates.append(path)
        except OSError:
            continue
    if not candidates:
        raise FileNotFoundError(f"no gzip catalog block found under {blocks}")
    # The real catalog is by far the largest gzip block.
    candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
    return candidates[0]


class Catalog:
    def __init__(self, raw: bytes):
        if len(raw) < 52:
            raise ValueError("catalog is truncated")
        self.raw = raw
        self.asset_count = struct.unpack_from("<I", raw, 8)[0]
        self.block_count = struct.unpack_from("<I", raw, 12)[0]
        self.bundle_count = struct.unpack_from("<I", raw, 16)[0]
        self.assets_start = struct.unpack_from("<I", raw, 20)[0]
        self.blocks_start = struct.unpack_from("<Q", raw, 28)[0]
        self.bundles_start = struct.unpack_from("<Q", raw, 36)[0]
        self.bundles_end = struct.unpack_from("<Q", raw, 44)[0]
        if self.assets_start != 52:
            raise ValueError("unsupported catalog asset table offset")
        if self.blocks_start != self.assets_start + self.asset_count * 12:
            raise ValueError("unsupported catalog block table offset")
        if self.bundles_start != self.blocks_start + self.block_count * 9:
            raise ValueError("unsupported catalog bundle table offset")
        if self.bundles_end != self.bundles_start + self.bundle_count * 28:
            raise ValueError("unsupported catalog bundle table end")
        if self.bundles_end > len(raw):
            raise ValueError("catalog bundle table exceeds file size")

    @classmethod
    def from_path(cls, path: Path) -> "Catalog":
        with path.open("rb") as handle:
            return cls(gzip.decompress(handle.read()))

    def block_for_asset_hash(self, hashes: set[int]) -> tuple[set[int], int]:
        matched_bundles: set[int] = set()
        matched_assets = 0
        for index in range(self.asset_count):
            offset = self.assets_start + index * 12
            bundle_index = struct.unpack_from("<I", self.raw, offset)[0]
            asset_hash = struct.unpack_from("<Q", self.raw, offset + 4)[0]
            if asset_hash in hashes:
                matched_bundles.add(bundle_index)
                matched_assets += 1

        block_ids: set[int] = set()
        for bundle_index in matched_bundles:
            if bundle_index >= self.bundle_count:
                continue
            offset = self.bundles_start + bundle_index * 28
            block_index = struct.unpack_from("<I", self.raw, offset)[0]
            if block_index >= self.block_count:
                continue
            block_offset = self.blocks_start + block_index * 9
            block_ids.add(struct.unpack_from("<I", self.raw, block_offset + 1)[0])
        return block_ids, matched_assets


def map_story_assets(catalog: Catalog, asset_paths: set[str]) -> tuple[dict[int, set[str]], int]:
    wanted: dict[int, str] = {}
    for path in asset_paths:
        full = ("assets/napresources/" + path).lower()
        wanted[xxhash.xxh64(full.encode("utf-8")).intdigest()] = path

    block_by_hash, matched = catalog.block_for_asset_hash(set(wanted))
    by_block: dict[int, set[str]] = {block_id: set() for block_id in block_by_hash}

    # Re-scan for the per-block path assignment.
    for index in range(catalog.asset_count):
        offset = catalog.assets_start + index * 12
        bundle_index = struct.unpack_from("<I", catalog.raw, offset)[0]
        asset_hash = struct.unpack_from("<Q", catalog.raw, offset + 4)[0]
        path = wanted.get(asset_hash)
        if path is None:
            continue
        if bundle_index >= catalog.bundle_count:
            continue
        bundle_offset = catalog.bundles_start + bundle_index * 28
        block_index = struct.unpack_from("<I", catalog.raw, bundle_offset)[0]
        if block_index >= catalog.block_count:
            continue
        block_offset = catalog.blocks_start + block_index * 9
        block_id = struct.unpack_from("<I", catalog.raw, block_offset + 1)[0]
        by_block.setdefault(block_id, set()).add(path)

    return by_block, matched
