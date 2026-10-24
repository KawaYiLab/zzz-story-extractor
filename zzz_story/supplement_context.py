"""Exact ComicConfig timeline references for existing supplement text keys.

Read saved Unity objects only. No file-name or nearby-text matching is used
to associate a Comic UUID with a scene or a displayed speaker.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from pathlib import Path

from .catalog import find_catalog_block, find_resource_block, map_story_assets
from .clean import clean_text
from .fetch import read_game_version
from .mhy1 import extract_mhy_named_files
from .perform_graph import asset_hash
from .timeline import _unity_string

_GUID = re.compile(r"[0-9a-f]{32}")
_CACHE_VERSION = 1


def comic_config_from_raw(raw: bytes) -> tuple[str, list[tuple[int, int]]]:
    """Decode the validated ComicConfig layout, preserving external PPtrs."""
    name, offset = _unity_string(raw, 28)
    # Three optional Unity PPtrs, one scalar, then 11 timeline-variant PPtrs.
    if offset + 3 * 12 + 4 + 11 * 12 > len(raw):
        raise ValueError("truncated ComicConfig timeline references")
    pointers = [struct.unpack_from("<iq", raw, offset + 3 * 12 + 4 + i * 12) for i in range(11)]
    offset += 3 * 12 + 4 + 11 * 12
    _, offset = _unity_string(raw, offset)
    if offset + 4 > len(raw):
        raise ValueError("truncated ComicConfig trailing list")
    count = struct.unpack_from("<I", raw, offset)[0]
    offset += 4
    if count > 1024:
        raise ValueError("oversized ComicConfig trailing list")
    for _ in range(count):
        if offset + 4 > len(raw):
            raise ValueError("truncated ComicConfig string list")
        size = struct.unpack_from("<I", raw, offset)[0]
        offset += 4
        if size > 1024:
            raise ValueError("oversized ComicConfig string list")
        for _ in range(size):
            _, offset = _unity_string(raw, offset)
    if offset != len(raw):
        raise ValueError("unsupported ComicConfig trailing fields")
    if any(file_id < 0 for file_id, _ in pointers):
        raise ValueError("negative ComicConfig file reference")
    return name, [(file_id, path_id) for file_id, path_id in pointers if path_id]


def _strings(raw: bytes, start: int = 32):
    for offset in range(start, len(raw) - 3, 4):
        try:
            value, end = _unity_string(raw, offset)
        except (ValueError, UnicodeDecodeError):
            continue
        if not value or value.isprintable():
            yield offset, end, value


def comic_bubbles_from_raw(raw: bytes) -> list[dict]:
    """Read same-event UUIDs and display names from EventTriggerMarker.

    Only typed BubbleEvent objects with the known namespace/reference header
    and Terminus footer are accepted. Other event GUIDs are not dialogue IDs.
    """
    _, offset = _unity_string(raw, 28)
    if offset + 16 > len(raw):
        raise ValueError("truncated EventTriggerMarker header")
    time = struct.unpack_from("<d", raw, offset)[0]
    if not math.isfinite(time) or time < 0:
        raise ValueError("invalid marker time")
    offset += 16
    info, offset = _unity_string(raw, offset)
    namespace, offset = _unity_string(raw, offset)
    assembly, offset = _unity_string(raw, offset)
    if (info, namespace, assembly) != ("EventTriggerMarkerInfo", "UnityEngine.Timeline", "Unity.Timeline"):
        return []
    if offset + 12 > len(raw):
        raise ValueError("truncated marker reference")
    ref_kind, reference = struct.unpack_from("<iq", raw, offset)
    if ref_kind != 0:
        return []
    label, offset = _unity_string(raw, offset + 12)
    strings = list(_strings(raw, offset))
    results = []
    for start, end, kind in strings:
        if kind != "BubbleEvent":
            continue
        try:
            namespace, cursor = _unity_string(raw, end)
            assembly, cursor = _unity_string(raw, cursor)
            if (namespace, assembly) != ("UnityEngine.Timeline", "Unity.Timeline"):
                continue
            if cursor + 24 > len(raw) or struct.unpack_from("<iqiii", raw, cursor) != (0, reference, 0, 0, 0):
                continue
            guid, body = _unity_string(raw, cursor + 24)
            if not _GUID.fullmatch(guid) or body + 12 > len(raw):
                continue
            footers = []
            for footer, footer_end, value in strings:
                if footer <= body or value != "Terminus":
                    continue
                ns, footer_end = _unity_string(raw, footer_end)
                asm, footer_end = _unity_string(raw, footer_end)
                if (ns, asm, footer_end) == ("UnityEngine.DMAT", "FAKE_ASM", len(raw)):
                    footers.append(footer)
            if len(footers) != 1:
                continue
            footer = footers[0]
            # BubbleEvent's display name precedes optional animation objects.
            # The last string before Terminus can instead be an easing name.
            # Decode the known body header and variable point array rather
            # than searching for a nearby or terminal string.
            speakers = []
            for header in (body + 68, body + 72):
                if header + 20 > footer:
                    continue
                style, enabled, toggle, point_kind, point_count = struct.unpack_from("<5i", raw, header)
                if not -256 <= style <= 4096 or enabled not in (0, 1) or toggle not in (0, 1):
                    continue
                if point_kind not in (0, 1, 2) or not 0 <= point_count <= 4:
                    continue
                name_offset = header + 20 + point_count * 8 + 8
                if name_offset + 4 > footer or struct.unpack_from("<ii", raw, name_offset - 8) != (0, 1):
                    continue
                display, name_end = _unity_string(raw, name_offset)
                if len(display) > 128 or (display and not display.isprintable()) or name_end > footer:
                    continue
                # A display string is followed by either the terminator or a
                # declared typed object; arbitrary float bytes are rejected.
                following, following_end = _unity_string(raw, name_end)
                valid_following = following == "Terminus"
                if not valid_following:
                    ns, following_end = _unity_string(raw, following_end)
                    asm, following_end = _unity_string(raw, following_end)
                    valid_following = ns in ("MoleMole.Comic", "UnityEngine.Timeline") and asm == "Unity.Timeline"
                if valid_following:
                    speakers.append((display or None, name_offset))
            speaker = speakers[0][0] if len(speakers) == 1 else None
            speaker_offset = speakers[0][1] if len(speakers) == 1 else None
            results.append({"text_key": "Comic_" + guid, "marker_name": label,
                            "marker_time": time, "event_offset": start,
                            "display_name": speaker, "display_name_offset": speaker_offset})
        except (ValueError, UnicodeDecodeError, struct.error):
            continue
    return results


def _script_name(obj) -> str | None:
    raw = obj.get_raw_data()
    if len(raw) < 32 or struct.unpack_from("<i", raw, 16)[0] != 0:
        return None
    script = obj.assets_file.objects.get(struct.unpack_from("<q", raw, 20)[0])
    return script.read().m_ClassName if script is not None and script.class_id == 115 else None


def _owned_markers(timeline) -> list:
    """Follow timeline roots, track children and marker PPtrs with owners."""
    raw = timeline.get_raw_data()
    _, offset = _unity_string(raw, 28)
    if offset + 8 > len(raw):
        raise ValueError("truncated Comic TimelineAsset")
    count = struct.unpack_from("<I", raw, offset + 4)[0]
    if count > 10000 or offset + 8 + count * 12 > len(raw):
        raise ValueError("invalid Comic TimelineAsset track list")
    roots = [struct.unpack_from("<iq", raw, offset + 8 + i * 12) for i in range(count)]
    objects = timeline.assets_file.objects
    seen = set()
    markers = {}

    def visit(file_id: int, path_id: int, parent: int) -> None:
        if file_id != 0 or path_id not in objects:
            raise ValueError("external or missing Comic track")
        if path_id in seen:
            return
        seen.add(path_id)
        track = objects[path_id]
        kind = _script_name(track) if track.class_id == 114 else None
        if not kind or not kind.endswith("Track"):
            raise ValueError("Comic root/child is not a track")
        data = track.get_raw_data()
        _, pos = _unity_string(data, 28)
        if pos + 56 > len(data) or struct.unpack_from("<iq", data, pos + 40) != (0, parent):
            raise ValueError("Comic track parent does not match timeline")
        children = struct.unpack_from("<I", data, pos + 52)[0]
        if children > 10000 or pos + 56 + children * 12 > len(data):
            raise ValueError("invalid Comic track children")
        for index in range(children):
            fid, pid = struct.unpack_from("<iq", data, pos + 56 + index * 12)
            visit(fid, pid, path_id)
        if kind != "EventTriggerTrack":
            return
        # The marker list is the terminal PPtr array followed by the track
        # owner PPtr. Validate both bounds and every referenced object type.
        arrays = []
        for pos in range(32, len(data) - 15, 4):
            size = struct.unpack_from("<I", data, pos)[0]
            if size == 0:
                continue
            if size > 10000 or pos + 4 + size * 12 + 12 != len(data):
                continue
            if struct.unpack_from("<iq", data, len(data) - 12) != (0, parent):
                continue
            pointers = [struct.unpack_from("<iq", data, pos + 4 + i * 12) for i in range(size)]
            if all(fid == 0 and pid in objects and objects[pid].class_id == 114
                   and _script_name(objects[pid]) == "EventTriggerMarker" for fid, pid in pointers):
                arrays.append(pointers)
        # Empty arrays contain no speaker/text evidence and can be omitted.
        if not arrays and struct.unpack_from("<iq", data, len(data) - 12) == (0, parent):
            if struct.unpack_from("<I", data, len(data) - 16)[0] == 0:
                return
        if len(arrays) != 1:
            raise ValueError("ambiguous Comic EventTriggerTrack markers")
        for _, pid in arrays[0]:
            markers[pid] = objects[pid]

    for file_id, path_id in roots:
        visit(file_id, path_id, timeline.path_id)
    return list(markers.values())


def comic_links_from_files(files: list[tuple[str, bytes]], wanted: set[str]) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """Resolve configured assets, external PPtrs and typed timeline markers."""
    import UnityPy

    wanted_hashes = {asset_hash(path): path for path in wanted}
    # Only files containing one of the three scripts can own relevant objects.
    environments = []
    serialized = {}
    for name, cab in files:
        if not any(marker in cab for marker in (b"ComicConfig", b"TimelineAsset", b"EventTriggerMarker")):
            continue
        env = UnityPy.load(cab)
        environments.append(env)
        # An mhy node is one serialized CAB. Its original name is the exact
        # identity used in the referring file's external-file table.
        if len(env.files) == 1:
            serialized.setdefault(name.rsplit("/", 1)[-1], []).append(next(iter(env.files.values())))
    result: dict[str, list[dict]] = {}
    errors = {}
    for env in environments:
        for bundle in env.objects:
            if bundle.class_id != 142:
                continue
            for key, info in bundle.read().m_Container:
                path = wanted_hashes.get(key)
                if path is None:
                    continue
                try:
                    if info.asset.m_FileID != 0:
                        raise ValueError("configured ComicConfig is external")
                    config = bundle.assets_file.objects.get(info.asset.m_PathID)
                    if config is None or config.class_id != 114 or _script_name(config) != "ComicConfig":
                        raise ValueError("configured object is not ComicConfig")
                    name, pointers = comic_config_from_raw(config.get_raw_data())
                    timelines = []
                    dependencies = set(bundle.read().m_Dependencies)
                    for file_id, path_id in pointers:
                        if file_id == 0:
                            target = config.assets_file.objects.get(path_id)
                        else:
                            if file_id > len(config.assets_file.externals):
                                continue
                            external_name = config.assets_file.externals[file_id - 1].path.rsplit("/", 1)[-1]
                            owners = serialized.get(external_name, [])
                            if len(owners) != 1:
                                continue
                            target = owners[0].objects.get(path_id)
                        if target is None:
                            continue
                        if file_id > 0:
                            owner_bundle = target.assets_file.assetbundle
                            if owner_bundle is None or owner_bundle.m_Name not in dependencies:
                                continue
                        if target.class_id == 114 and _script_name(target) == "TimelineAsset":
                            timelines.append((file_id, target))
                    if not timelines:
                        raise ValueError("ComicConfig timeline unavailable or ambiguous")
                    for file_id, timeline in timelines:
                        timeline_name, _ = _unity_string(timeline.get_raw_data(), 28)
                        for marker in _owned_markers(timeline):
                            for occurrence in comic_bubbles_from_raw(marker.get_raw_data()):
                                item = {**occurrence, "asset": path, "comic": name,
                                        "timeline": timeline_name, "timeline_path_id": timeline.path_id,
                                        "timeline_file_id": file_id, "marker_path_id": marker.path_id,
                                        "timeline_bundle": timeline.assets_file.assetbundle.m_Name,
                                        "external_file": config.assets_file.externals[file_id - 1].path if file_id else None,
                                        "pointer_resolution": "external_cab_name_and_path_id" if file_id else "same_file",
                                        "evidence": "comic_config_owned_timeline_bubble_uuid"}
                                result.setdefault(item["text_key"], []).append(item)
                except (ValueError, KeyError, UnicodeDecodeError, struct.error) as exc:
                    errors[path] = str(exc)
    for items in result.values():
        items.sort(key=lambda item: (item["asset"], item["timeline"], item["marker_time"], item["marker_path_id"], item["event_offset"]))
    return result, errors


def scan_comic_context(game_dir: Path | None, perform: object, cache_path: Path | None = None, *, refresh: bool = False) -> dict:
    """Scan known Comic assets with a cache bound to source and resource state."""
    if game_dir is None:
        return {"links": {}, "errors": {}, "stats": {"configured": 0, "matched": 0, "linked_texts": 0}}
    from .catalog import Catalog
    from .writers import _atomic_write_text

    paths = {row[field] for row in perform.get("IAEFFFFLKNB", []) if isinstance(row, dict)
             for field in ("BCKKFAEFDPP", "LGJCAHIEBBK")
             if isinstance(row.get(field), str) and row[field].startswith("Data/ScriptConfig/Comic/") and row[field].endswith(".asset")}
    catalog_path = find_catalog_block(game_dir)
    catalog = Catalog.from_path(catalog_path)
    by_block, matched = map_story_assets(catalog, paths)
    block_paths = {bid: find_resource_block(game_dir, bid) for bid in by_block}
    resources = [(str(path), path.stat().st_size, path.stat().st_mtime_ns) if path else (bid, None, None)
                 for bid, path in sorted(block_paths.items())]
    catalog_stat = catalog_path.stat()
    fingerprint = hashlib.sha256(json.dumps({
        "version": _CACHE_VERSION,
        "code": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                 for name in ("supplement_context.py", "timeline.py", "mhy1.py", "catalog.py", "clean.py")},
        "game": str(game_dir.resolve()), "game_version": read_game_version(game_dir),
        "perform": perform, "resources": resources,
        "catalog": (str(catalog_path), catalog_stat.st_size, catalog_stat.st_mtime_ns),
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    if cache_path and cache_path.is_file() and not refresh:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("fingerprint") == fingerprint:
                unchanged = all(
                    (path := find_resource_block(game_dir, int(block_id))) is not None
                    and [str(path), path.stat().st_size, path.stat().st_mtime_ns] == state
                    for block_id, state in cached.get("dependency_resources", {}).items()
                )
                if unchanged:
                    print(f"  comic context cache: {len(cached['links'])} text UUIDs")
                    return cached
        except (ValueError, KeyError, TypeError):
            pass
    result = {"fingerprint": fingerprint, "links": {}, "errors": {}, "dependency_resources": {},
              "stats": {"configured": len(paths), "matched": matched, "blocks": len(by_block)}}
    for number, (block_id, wanted) in enumerate(sorted(by_block.items()), 1):
        path = block_paths[block_id]
        if path is None:
            result["errors"][str(block_id)] = "missing_comic_block"
            continue
        if number % 10 == 0 or number == 1:
            print(f"  comic context block {number}/{len(by_block)}")
        files = extract_mhy_named_files(path.read_bytes())
        links, errors = comic_links_from_files(files, wanted)
        retry = {asset for asset, error in errors.items() if error == "ComicConfig timeline unavailable or ambiguous"}
        if retry:
            # Some timeline CABs are in another dependency block. Bundle
            # dependencies are numeric asset hashes from the same catalog;
            # retain the exact names and follow their original CAB PPtrs.
            import UnityPy

            dependencies = set()
            for _, cab in files:
                if b"ComicConfig" not in cab:
                    continue
                for bundle in UnityPy.load(cab).objects:
                    if bundle.class_id != 142:
                        continue
                    value = bundle.read()
                    if any(key in {asset_hash(asset) for asset in retry} for key, _ in value.m_Container):
                        dependencies.update(int(name[:-len(".bundle")]) for name in value.m_Dependencies
                                            if re.fullmatch(r"\d+\.bundle", name))
            ids, _ = catalog.block_for_asset_hash(dependencies)
            for dependency_id in sorted(ids - {block_id}):
                dependency = find_resource_block(game_dir, dependency_id)
                if dependency is None:
                    continue
                state = dependency.stat()
                result["dependency_resources"][str(dependency_id)] = [str(dependency), state.st_size, state.st_mtime_ns]
                files.extend(extract_mhy_named_files(dependency.read_bytes()))
            recovered, pending = comic_links_from_files(files, retry)
            for key, items in recovered.items():
                links.setdefault(key, []).extend(items)
            for recovered_asset in retry - pending.keys():
                errors.pop(recovered_asset, None)
            errors.update(pending)
        for key, items in links.items():
            result["links"].setdefault(key, []).extend(items)
        result["errors"].update(errors)
    result["stats"]["linked_texts"] = len(result["links"])
    result["stats"]["errors"] = len(result["errors"])
    if cache_path:
        _atomic_write_text(cache_path, json.dumps(result, ensure_ascii=False))
    return result


def annotate_supplement_context(records: list[dict], context: dict) -> dict[str, int]:
    """Attach exact occurrences while retaining the supplement's stable ID."""
    stats = {"comic_linked": 0, "comic_named": 0, "comic_conflicting_names": 0}
    for record in records:
        if record.get("family") != "Comic":
            continue
        # Re-annotation must retract this helper's old claims before applying
        # current evidence. A removed resource or a new conflict must never
        # leave a formerly resolved comic speaker in the record.
        owns_attribution = (record.get("speaker_source") == "comic_bubble"
                            or "comic_context" in record
                            or str(record.get("speaker_gap_reason", "")).startswith(("comic_", "conflicting_comic_")))
        if owns_attribution:
            for field in ("speaker", "speaker_source", "speaker_status", "speaker_gap_reason", "speaker_confidence"):
                record.pop(field, None)
        for field in ("comic_context", "comic_scenes", "context_chronology_status"):
            record.pop(field, None)
        record["context_status"] = "unlinked"
        items = context.get("links", {}).get(record["source_key"], [])
        if not items:
            if owns_attribution:
                record["speaker_status"] = "unresolved"
                record["speaker_gap_reason"] = "comic_reference_missing"
            continue
        record["context_status"] = "resource_linked"
        record["comic_context"] = items
        record["comic_scenes"] = sorted({item["comic"] for item in items})
        record["context_chronology_status"] = "within_timeline" if len({(item["asset"], item["timeline_path_id"]) for item in items}) == 1 else "unknown"
        names = {clean_text(item["display_name"], "M").text for item in items if item.get("display_name")}
        if len(names) == 1 and all(item.get("display_name") for item in items):
            record["speaker"] = next(iter(names))
            record["speaker_source"] = "comic_bubble"
            record["speaker_status"] = "resolved"
            record["speaker_gap_reason"] = None
            stats["comic_named"] += 1
        elif len(names) > 1:
            record["speaker_status"] = "unresolved"
            record["speaker_gap_reason"] = "conflicting_comic_display_names"
            stats["comic_conflicting_names"] += 1
        else:
            record["speaker_status"] = "unresolved"
            record["speaker_gap_reason"] = "comic_display_name_missing"
        stats["comic_linked"] += 1
    return stats
