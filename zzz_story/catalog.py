"""Parse legacy gzip and Unity resource catalogs and locate Perform blocks."""

from __future__ import annotations

import gzip
import json
import re
import struct
from pathlib import Path

import xxhash

from .mhy1 import extract_mhy_files


def resource_block_dirs(game_dir: Path) -> tuple[Path, Path]:
    root = game_dir / "ZenlessZoneZero_Data"
    return root / "Persistent" / "Blocks", root / "StreamingAssets" / "Blocks"


def find_resource_block(game_dir: Path, block_id: int) -> Path | None:
    for blocks in resource_block_dirs(game_dir):
        path = blocks / f"{block_id}.blk"
        if path.is_file():
            return path
    return None


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
    root = game_dir / "ZenlessZoneZero_Data"
    # The index is the untagged Blocks entry in the game's resource manifest.
    # Prefer the patched index to the base install, including legacy gzip.
    for rel in ("Persistent/res_version_persist", "StreamingAssets/res_version"):
        manifest = root / rel
        if not manifest.is_file():
            continue
        with manifest.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        for entry in reversed(payload.get("files", [])):
            match = re.fullmatch(r"Blocks/(\d+)\.blk", entry.get("remoteName", ""))
            if match and not entry.get("tags"):
                path = find_resource_block(game_dir, int(match.group(1)))
                if path:
                    return path

    candidates: list[Path] = []
    for blocks in resource_block_dirs(game_dir):
        for path in blocks.glob("*.blk"):
            try:
                with path.open("rb") as handle:
                    if handle.read(2) == b"\x1f\x8b":
                        candidates.append(path)
            except OSError:
                continue
        if candidates:
            break
    if not candidates:
        raise FileNotFoundError(f"no resource catalog found under {root}")
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
        self.bundle_stride = 28
        self.block_id_offset = 1
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
        data = path.read_bytes()
        if data.startswith(b"\x1f\x8b"):
            return cls(gzip.decompress(data))
        if not data.startswith(b"mhy1"):
            raise ValueError(f"unsupported resource catalog container: {path}")

        import UnityPy

        for cab in extract_mhy_files(data):
            env = UnityPy.load(cab)
            for obj in env.objects:
                # 3.3 serializes the index as a custom Unity object, without
                # a type tree. UnityPy locates its bytes using the object table.
                if obj.class_id == 6776977:
                    return cls.from_unity_index(obj.get_raw_data())
        raise ValueError(f"resource index object missing from {path}")

    @classmethod
    def from_unity_index(cls, raw: bytes) -> "Catalog":
        if len(raw) < 12 or raw[:8] != b"\x03\x00\x00\x00Res\x00":
            raise ValueError("unsupported Unity resource index header")
        catalog = cls.__new__(cls)
        catalog.raw = raw
        catalog.asset_count = struct.unpack_from("<I", raw, 8)[0]
        catalog.assets_start = 12
        bundle_count_offset = catalog.assets_start + catalog.asset_count * 12
        if bundle_count_offset + 4 > len(raw):
            raise ValueError("Unity catalog asset table exceeds file size")
        catalog.bundle_count = struct.unpack_from("<I", raw, bundle_count_offset)[0]
        catalog.bundles_start = bundle_count_offset + 4
        catalog.bundle_stride = 44
        catalog.bundles_end = catalog.bundles_start + catalog.bundle_count * catalog.bundle_stride
        if catalog.bundles_end + 4 > len(raw):
            raise ValueError("Unity catalog bundle table exceeds file size")
        catalog.block_count = struct.unpack_from("<I", raw, catalog.bundles_end)[0]
        catalog.blocks_start = catalog.bundles_end + 4
        catalog.block_id_offset = 0
        if catalog.blocks_start + catalog.block_count * 9 > len(raw):
            raise ValueError("Unity catalog block table exceeds file size")
        return catalog

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
            offset = self.bundles_start + bundle_index * self.bundle_stride
            block_index = struct.unpack_from("<I", self.raw, offset)[0]
            if block_index >= self.block_count:
                continue
            block_offset = self.blocks_start + block_index * 9
            block_ids.add(struct.unpack_from("<I", self.raw, block_offset + self.block_id_offset)[0])
        return block_ids, matched_assets


def map_story_assets(catalog: Catalog, asset_paths: set[str]) -> tuple[dict[int, set[str]], int]:
    wanted: dict[int, str] = {}
    for path in asset_paths:
        full = ("assets/napresources/" + path).lower()
        wanted[xxhash.xxh64(full.encode("utf-8")).intdigest()] = path

    # Resolve the matched asset, bundle and block in one table pass.  The old
    # implementation first scanned every asset to discover matching blocks,
    # then scanned the same asset table again to assign paths to those blocks.
    # The catalog is large (500k+ assets), so retaining the path while doing
    # the first lookup avoids a full second pass.
    by_block: dict[int, set[str]] = {}
    matched = 0
    for index in range(catalog.asset_count):
        offset = catalog.assets_start + index * 12
        bundle_index = struct.unpack_from("<I", catalog.raw, offset)[0]
        asset_hash = struct.unpack_from("<Q", catalog.raw, offset + 4)[0]
        path = wanted.get(asset_hash)
        if path is None:
            continue
        matched += 1
        if bundle_index >= catalog.bundle_count:
            continue
        bundle_offset = catalog.bundles_start + bundle_index * catalog.bundle_stride
        block_index = struct.unpack_from("<I", catalog.raw, bundle_offset)[0]
        if block_index >= catalog.block_count:
            continue
        block_offset = catalog.blocks_start + block_index * 9
        block_id = struct.unpack_from("<I", catalog.raw, block_offset + catalog.block_id_offset)[0]
        by_block.setdefault(block_id, set()).add(path)

    return by_block, matched
