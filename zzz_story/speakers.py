"""Resolve per-line speakers from Perform voice links."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .catalog import Catalog, find_catalog_block, map_story_assets, story_asset_paths
from .fetch import read_json
from .perform import scan_perform_blocks
from .textmap import load_language_map

CACHE_VERSION = 3

_ALIAS_IN_BANKS = re.compile(r"(?:^|\|)BK_([A-Za-z0-9]+)")
_ALIAS_IN_PATH = re.compile(r"(?:^|/)VO_([A-Za-z0-9]+)(?:/|$)")
_GALGAME_SOURCE = re.compile(
    r"^(?:VO_[A-Za-z0-9_./-]+/)?(?:Galgame|GalGame)_([^_/]+)_([^_/]+)_(\d+)(?:_\d+)?$",
    re.IGNORECASE,
)
_CHAPTER_NORMALIZE = re.compile(r"chapter0*(\d+)", re.IGNORECASE)
_NAME_CLEAN = re.compile(r"[\s\-_·.&/（）()\[\]【】「」:：,，]+")
_CJK = re.compile(r"[\u4e00-\u9fff]")
_NAME_KEYS = (
    "Partner_Name",
    "NPCName",
    "FullName",
    "Avatar_",
    "_Name",
    "Message_NPC",
    "Message_MultiMessage_Name",
)
_GENERIC_NAMES = {
    "黑色", "白色", "红色", "蓝色", "绿色", "黄色", "紫色", "灰色", "选项", "旁白",
    "男性", "女性", "未知", "无", "其他", "全部", "搜索", "确认", "取消",
}
_MANUAL_ALIASES = {
    "fairy": "Fairy",
    "bruxas": "奥菲丝&「鬼火」",
    "brujas": "奥菲丝&「鬼火」",
    "nekomiya": "猫又",
    # Internal aliases that differ from both AvatarBase and the English name
    # used in the TextMap.  Kept explicit rather than fuzzy-guessed.
    "orpheus": "奥菲厄丝",
    "orphie": "奥菲丝",
    "lindveinskin01": "林德薇恩",
    "lindvein": "林德薇恩",
    "generallorenz": "「少将」洛伦兹",
}

_ALIAS_PREFIXES = (
    "student",
    "taoist",
    "swimsuit",
    "starlight",
    "remielle",
    "sp",
    "ex",
    "new",
    "old",
    "teen",
    "little",
    "young",
)
_ALIAS_SUFFIXES = ("black", "white", "teen", "young", "little", "sunbringer")


def normalize_name(value: str) -> str:
    return _NAME_CLEAN.sub("", value or "").lower()


def load_alias_map(text_map, en_map: dict[str, str], avatar_payload) -> dict[str, str]:
    aliases: dict[str, str] = {}
    rows = avatar_payload.get("IAEFFFFLKNB", []) if isinstance(avatar_payload, dict) else []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            display = (
                text_map.get(str(row.get("HAKHHHCAENA", "")))
                or text_map.get(str(row.get("JGHFBBCBBBA", "")))
                or row.get("ABBKMFEEJNJ")
                or ""
            )
            if not display or not _CJK.search(display):
                continue
            banks = row.get("NBEKFBKGEPP", "")
            if isinstance(banks, str):
                for match in _ALIAS_IN_BANKS.finditer(banks):
                    alias = match.group(1)
                    if alias.lower() == "chr":
                        continue
                    key = normalize_name(alias)
                    if key not in aliases or not _CJK.search(aliases[key]):
                        aliases[key] = display
            for key in ("FEKFJBFGANO", "ABBKMFEEJNJ"):
                value = row.get(key)
                if isinstance(value, str) and value:
                    normalized = normalize_name(value)
                    if normalized not in aliases or not _CJK.search(aliases[normalized]):
                        aliases.setdefault(normalized, display)

    # English TextMap values -> Chinese TextMap values for name-like keys.
    # This resolves cast names such as Nekomata -> 猫又 without hand tables.
    for key, english in en_map.items():
        if not any(pattern in key for pattern in _NAME_KEYS):
            continue
        if not isinstance(english, str) or not english:
            continue
        chinese = text_map.get(key)
        if not chinese or chinese == english:
            continue
        if len(english) > 48 or any(char in english for char in "\n<>{}"):
            continue
        if not _CJK.search(chinese) or len(chinese) > 24 or chinese in _GENERIC_NAMES:
            continue
        normalized = normalize_name(english)
        if len(normalized) < 2 or normalized.isdigit():
            continue
        aliases.setdefault(normalized, chinese)

    for alias, display in _MANUAL_ALIASES.items():
        aliases.setdefault(alias, display)
    return aliases


def resolve_alias(alias: str, aliases: dict[str, str]) -> str | None:
    normalized = normalize_name(alias)
    if not normalized:
        return None
    if normalized in aliases:
        return aliases[normalized]

    for prefix in _ALIAS_PREFIXES:
        if normalized.startswith(prefix) and len(normalized) > len(prefix):
            candidate = normalized[len(prefix):]
            if candidate in aliases:
                return aliases[candidate]
    for suffix in _ALIAS_SUFFIXES:
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            candidate = normalized[:-len(suffix)]
            if candidate in aliases:
                return aliases[candidate]

    if len(normalized) >= 4:
        candidates: list[tuple[int, str]] = []
        for key, display in aliases.items():
            if len(key) >= 4 and (
                key.startswith(normalized)
                or normalized.startswith(key)
                or key.endswith(normalized)
                or normalized.endswith(key)
            ):
                candidates.append((len(key), display))
        values = {display for _, display in candidates}
        if len(values) == 1:
            return next(iter(values))

        contained = [(len(key), display) for key, display in aliases.items() if len(key) >= 4 and key in normalized]
        if contained:
            contained.sort(reverse=True)
            values = {display for _, display in contained}
            if len(values) == 1:
                return next(iter(values))
    return None


@dataclass
class SpeakerInfo:
    speaker: str | None
    alias: str | None
    confidence: float
    source: str  # voice | scene_name | none
    has_voice: bool = False


@dataclass
class SpeakerStats:
    links: int = 0
    sources: int = 0
    text_ids: int = 0
    mapped_keys: int = 0
    ambiguous: int = 0
    unresolved_aliases: int = 0
    blocks: int = 0
    avatar_links: int = 0
    avatar_values: int = 0
    avatar_speakers: int = 0


def alias_from_source(source: str) -> str | None:
    found = _ALIAS_IN_PATH.findall(source)
    if found:
        # Prefer the last VO_ segment; in practice there is exactly one.
        return found[-1]

    filename = source.rsplit("/", 1)[-1]
    match = _GALGAME_SOURCE.match(filename)
    if match:
        alias = match.group(2)
        # In GalGame_<chapter>_<speaker>_<line> the middle segment is the
        # character alias.  Numeric middle segments are scene ids, not names.
        if alias and not alias.isdigit():
            return alias
    return None


def canonical_text_id(value: str) -> str:
    value = value.strip()
    if value.startswith("Main_"):
        value = value[5:]
    value = _CHAPTER_NORMALIZE.sub(lambda m: f"chapter{int(m.group(1))}", value)
    return value.lower()


def _normalized_key_index(text_keys: set[str]) -> dict[str, str]:
    index: dict[str, str] = {}
    for key in text_keys:
        index.setdefault(canonical_text_id(key), key)
    return index


def build_speaker_index(
    *,
    text_map,
    text_keys: set[str],
    data_paths: dict[str, Path],
    game_dir: Path | None,
    cache_path: Path,
    refresh: bool = False,
    no_speakers: bool = False,
) -> tuple["SpeakerIndex", SpeakerStats]:
    stats = SpeakerStats()
    if no_speakers or game_dir is None:
        return SpeakerIndex({}, stats), stats

    if cache_path.exists() and not refresh:
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if payload.get("version") != CACHE_VERSION:
                raise ValueError("speaker cache version changed")
            speakers = {
                text_id: SpeakerInfo(**info)
                for text_id, info in payload.get("speakers", {}).items()
            }
            for key, value in payload.get("stats", {}).items():
                if hasattr(stats, key):
                    setattr(stats, key, value)
            print(f"Loaded speaker cache: {len(speakers)} text ids")
            return _index_from_speakers(speakers, text_keys, stats), stats
        except Exception as exc:  # noqa: BLE001 - rebuild on corrupt cache
            print(f"Speaker cache unreadable, rebuilding: {exc}")

    perform_path = data_paths.get("FileCfg/PerformTemplateTb.json")
    avatar_path = data_paths.get("FileCfg/AvatarBaseTemplateTb.json")
    voice_path = data_paths.get("Data/_unsorted/VoiceData.json")
    if not perform_path or not avatar_path or not voice_path:
        print("warning: speaker inputs missing; continuing without per-line speakers")
        return SpeakerIndex({}, stats), stats

    en_map = load_language_map(data_paths, "EN")
    alias_map = load_alias_map(text_map, en_map, read_json(avatar_path))
    print(f"  alias table: {len(alias_map)} entries (EN names + AvatarBase)")
    voice_payload = read_json(voice_path)
    _ = voice_payload  # currently only used for diagnostics; source paths carry VO_<alias>

    print("Finding resource catalog...")
    catalog_path = find_catalog_block(game_dir)
    print(f"  catalog: {catalog_path.name} ({catalog_path.stat().st_size / 1e6:.1f} MB)")
    catalog = Catalog.from_path(catalog_path)
    print(
        f"  catalog: {catalog.asset_count} assets / {catalog.block_count} blocks / "
        f"{catalog.bundle_count} bundles"
    )

    perform_payload = read_json(perform_path)
    asset_paths = story_asset_paths(perform_payload)
    by_block, matched = map_story_assets(catalog, asset_paths)
    block_paths = []
    blocks_dir = game_dir / "ZenlessZoneZero_Data" / "StreamingAssets" / "Blocks"
    for block_id in sorted(by_block):
        path = blocks_dir / f"{block_id}.blk"
        if path.exists():
            block_paths.append(path)
        else:
            print(f"  warning: missing block {path.name}")
    print(
        f"  perform assets: {len(asset_paths)} paths, {matched} matched, "
        f"{len(block_paths)} blocks"
    )
    if not block_paths:
        print("warning: no Perform blocks found; continuing without per-line speakers")
        return SpeakerIndex({}, stats), stats

    source_to_text, avatar_to_text, scan_stats = scan_perform_blocks(block_paths)
    stats.links = scan_stats.links
    stats.sources = scan_stats.sources
    stats.blocks = scan_stats.blocks
    stats.avatar_links = scan_stats.avatar_links
    stats.avatar_values = scan_stats.avatar_values
    print(
        f"Scan complete: {scan_stats.links} voice links, {scan_stats.sources} sources, "
        f"{scan_stats.avatar_links} avatar links, {scan_stats.avatar_values} text ids with avatar"
    )

    text_to_infos: dict[str, list[tuple[str | None, str | None, str]]] = {}
    for source, text_ids in source_to_text.items():
        alias = alias_from_source(source)
        speaker = resolve_alias(alias, alias_map) if alias else None
        for text_id in text_ids:
            text_to_infos.setdefault(text_id, []).append((speaker, alias, source))

    speakers: dict[str, SpeakerInfo] = {}
    for text_id, infos in text_to_infos.items():
        named = {(speaker, alias) for speaker, alias, _ in infos if speaker}
        if len(named) == 1:
            speaker, alias = next(iter(named))
            speakers[text_id] = SpeakerInfo(speaker, alias, 1.0, "voice", True)
        elif len(named) > 1:
            stats.ambiguous += 1
            speakers[text_id] = SpeakerInfo(None, None, 0.0, "voice", True)
        else:
            aliases = {alias for _, alias, _ in infos if alias}
            if len(aliases) == 1:
                alias = next(iter(aliases))
                stats.unresolved_aliases += 1
                speakers[text_id] = SpeakerInfo(None, alias, 0.0, "voice", True)
            else:
                stats.ambiguous += 1
                speakers[text_id] = SpeakerInfo(None, None, 0.0, "voice", True)

    # Perform assets also carry an avatarName per dialogue node.  It is a
    # TextMap key in most cases, which gives a direct speaker even for
    # unvoiced Chat/MainChat lines.
    for text_id, avatar_name in avatar_to_text.items():
        if text_id in speakers and speakers[text_id].speaker:
            continue
        display = text_map.get(avatar_name) or resolve_alias(avatar_name, alias_map)
        if not display:
            continue
        speakers[text_id] = SpeakerInfo(display, avatar_name, 0.95, "avatar", False)
        stats.avatar_speakers += 1

    stats.text_ids = len(speakers)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "speakers": {key: asdict(value) for key, value in speakers.items()},
        "stats": asdict(stats),
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"Cached speaker map: {cache_path}")
    return _index_from_speakers(speakers, text_keys, stats), stats


def _index_from_speakers(
    speakers: dict[str, SpeakerInfo],
    text_keys: set[str],
    stats: SpeakerStats,
) -> "SpeakerIndex":
    normalized = _normalized_key_index(text_keys)
    key_info: dict[str, SpeakerInfo] = {}
    for text_id, info in speakers.items():
        candidates = [text_id]
        if not text_id.startswith("Main_"):
            candidates.append("Main_" + text_id)
        if text_id.startswith("Main_"):
            candidates.append(text_id[5:])
        key = next((candidate for candidate in candidates if candidate in text_keys), None)
        if key is None:
            key = normalized.get(canonical_text_id(text_id))
        if key is None:
            continue
        previous = key_info.get(key)
        if previous is None or (info.confidence, info.speaker or "") > (
            previous.confidence,
            previous.speaker or "",
        ):
            key_info[key] = info
    stats.mapped_keys = len(key_info)
    return SpeakerIndex(key_info, stats)


class SpeakerIndex:
    def __init__(self, key_info: dict[str, SpeakerInfo], stats: SpeakerStats):
        self._key_info = key_info
        self.stats = stats

    def lookup(self, key: str) -> SpeakerInfo | None:
        return self._key_info.get(key)

    def __len__(self) -> int:
        return len(self._key_info)
