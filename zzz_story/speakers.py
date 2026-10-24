"""Resolve per-line speakers from Perform voice links."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .catalog import (
    Catalog,
    find_catalog_block,
    find_resource_block,
    map_story_assets,
    resource_block_dirs,
    story_asset_paths,
)
from .clean import clean_text
from .fetch import read_game_version, read_json, sha256_file
from .partner_dialogue import PARTNER_DIALOGUE_PREFIXES
from .perform import scan_perform_blocks
from .perform_graph import configured_routes, graph_links, link_unused_copies
from .street_dialogue import STREET_DIALOGUE_PREFIXES
from .textmap import load_language_map
from .timeline import VOICE_RE, link_main_copies, scan_timeline_clips

CACHE_VERSION = 9

_TIPS_VOICE_RE = re.compile(r"^[A-Za-z]+_Chapter\w+_([A-Za-z]+)_\d+_\d+$")
_TIPS_NAME_IGNORE = {"选项", "玩家选项", "旁白"}

_ALIAS_IN_BANKS = re.compile(r"(?:^|\|)BK_([A-Za-z0-9]+)")
_ALIAS_IN_PATH = re.compile(r"(?:^|/)VO_([A-Za-z0-9]+)(?:/|$)")
_GALGAME_SOURCE = re.compile(
    r"^(?:VO_[A-Za-z0-9_./-]+/)?(?:Galgame|GalGame)_([^_/]+)_([^_/]+)_(\d+)(?:_\d+)*$",
    re.IGNORECASE,
)
_TIMELINE_CSR_SOURCE = re.compile(r"^Timeline_Csr_[A-Za-z0-9_]+_([A-Za-z][A-Za-z0-9]*)_\d+$")
_OTHER_VOICE_SOURCE = re.compile(
    r"^(?:Chat|ChatAudio|ChatPlus|Bubble|BubbleStory|OngoingLevel|OngoingMainCity|OngoingAntique|Ongoing)"
    r"(?:_Bubmale)?_Chapter[^_]+_([^_]+)_\d+(?:_\d+)*$"
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
    "GalNPC",
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
    "victima": "遇害者A",
    "victimb": "遇害者B",
    "victimc": "遇害者C",
    "victimd": "遇害者D",
    "victime": "遇害者E",
    "saraswhispercroon": "莎拉",
    "youkai": "幻祟",
    "scaredcorporateexecutive": "惊恐的高管",
    "mother": "母亲",
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

    # GalNPC keys in TextMap directly map character alias to Chinese display name:
    # e.g. GalNPCParo -> 帕罗, GalNPCMianzai -> 绵仔, GalNPCFeebleman -> 虚弱的男人.
    for key in text_map.keys():
        if key.startswith("GalNPC"):
            display = text_map.get(key)
            if display and _CJK.search(display) and len(display) <= 24 and display not in _GENERIC_NAMES:
                alias = normalize_name(key[6:])
                if alias and len(alias) >= 2:
                    aliases.setdefault(alias, display)

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
    timeline: dict | None = None
    perform: dict | None = None


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
    tips_speakers: int = 0
    timeline_clips: int = 0
    timeline_mapped: int = 0
    perform_graphs: int = 0
    perform_graph_errors: int = 0
    perform_gender_keys: int = 0
    perform_copy_keys: int = 0


def alias_from_source(source: str) -> str | None:
    found = _ALIAS_IN_PATH.findall(source)
    if found:
        # Prefer the last VO_ segment; in practice there is exactly one.
        return found[-1]

    filename = source.rsplit("/", 1)[-1]
    timeline = _TIMELINE_CSR_SOURCE.fullmatch(filename)
    if timeline:
        return timeline.group(1)
    other = _OTHER_VOICE_SOURCE.fullmatch(filename)
    if other and not other.group(1).isdigit():
        return other.group(1)
    match = _GALGAME_SOURCE.match(filename)
    if match:
        alias = match.group(2)
        # In GalGame_<chapter>_<speaker>_<line> the middle segment is the
        # character alias.  Numeric middle segments are scene ids, not names.
        if alias and not alias.isdigit():
            return alias
    return None


def structured_speaker(link: dict, text_map, aliases: dict[str, str], existing: SpeakerInfo | None = None) -> SpeakerInfo:
    """Resolve same-node fields; an empty field cannot inherit a nearby name."""
    avatars = link["avatars"]
    avatar = avatars[0] if len(avatars) == 1 else None
    displays = [text_map.get(value) or resolve_alias(value, aliases) for value in avatars]
    display = displays[0] if displays and all(displays) and len(set(displays)) == 1 else None
    resolved = [(resolve_alias(alias, aliases), alias) for voice in link["voice_keys"]
                if (alias := alias_from_source(voice))]
    names = {name for name, _ in resolved if name}
    if not avatars and len(names) == 1:
        display = next(iter(names))
    voice_aliases = {alias for name, alias in resolved if name == display}
    alias = avatar or (next(iter(voice_aliases)) if len(voice_aliases) == 1 else None)
    if not alias:
        unresolved = {alias for _, alias in resolved}
        alias = next(iter(unresolved)) if len(unresolved) == 1 else None
    # Typed occurrences supersede the legacy scanner, including explicit
    # unnamed narration, conflicting names and unresolved local actor slots.
    exact = bool(link.get("occurrences"))
    return SpeakerInfo(
        display or (existing.speaker if existing and not exact else None),
        alias or (existing.alias if existing and not exact else None),
        0.98 if display else (existing.confidence if existing and not exact else 0.0),
        "perform" if display or exact else (existing.source if existing else "none"),
        bool(link["voice_keys"]) or bool(existing and existing.has_voice and not exact),
        perform=link,
    )


def canonical_text_id(value: str) -> str:
    value = value.strip()
    if value.startswith("Main_"):
        value = value[5:]
    value = _CHAPTER_NORMALIZE.sub(lambda m: f"chapter{int(m.group(1))}", value)
    return value.lower()


def _normalized_key_index(text_keys: set[str]) -> dict[str, str]:
    buckets: dict[str, list[str]] = {}
    for key in text_keys:
        buckets.setdefault(canonical_text_id(key), []).append(key)
    # A canonical collision is ambiguous. Returning one arbitrary set member
    # made speaker assignment depend on hash iteration order.
    return {
        canonical: values[0]
        for canonical, values in buckets.items()
        if len(values) == 1
    }


def ongoing_tips_speakers(
    data_paths: dict[str, Path],
    text_map,
    alias_map: dict[str, str],
    protagonist: str = "M",
) -> dict[str, tuple[str, str | None]]:
    """Speakers for in-level dialogue (Ongoing*) from OngoingTipsConfigTemplateTb.

    Each row ties a TextMap line key to a display-name key and to the voice
    bank of the speaking character ( Belle/Wise variants included), which
    covers lines the Perform block scan cannot reach.
    """
    path = data_paths.get("FileCfg/OngoingTipsConfigTemplateTb.json")
    candidates: dict[str, set[tuple[str, str | None]]] = {}
    if not path or not path.exists():
        return {}
    payload = read_json(path)
    rows = payload.get("IAEFFFFLKNB", []) if isinstance(payload, dict) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text_key = row.get("FGAHJLHNEDB")
        if not isinstance(text_key, str):
            continue
        # TextMap membership avoids assigning a missing source. Support the
        # old test map protocol as well as the normal TextMap dictionary.
        if hasattr(text_map, "__contains__") and text_key not in text_map:
            continue
        name = text_map.get(str(row.get("BLOGJEGIBOH") or ""))
        if name and name not in _GENERIC_NAMES and name not in _TIPS_NAME_IGNORE:
            candidates.setdefault(text_key, set()).add((name, None))
            continue
        primary, secondary = (
            ("CIBKAFBOGCI", "PFOBGIIIICG") if protagonist == "M" else ("PFOBGIIIICG", "CIBKAFBOGCI")
        )
        voice = row.get(primary) or row.get(secondary) or ""
        match = _TIPS_VOICE_RE.match(voice) if isinstance(voice, str) else None
        alias = match.group(1) if match else None
        speaker = resolve_alias(alias, alias_map) if alias else None
        if speaker:
            candidates.setdefault(text_key, set()).add((speaker, alias))
    out = {}
    for text_key, choices in candidates.items():
        names = {name for name, _ in choices}
        if len(names) != 1:
            continue
        aliases = {alias for _, alias in choices if alias}
        out[text_key] = (next(iter(names)), next(iter(aliases)) if len(aliases) == 1 else None)
    return out


def ongoing_voice_names(data_paths: dict[str, Path], text_map, protagonist: str = "M") -> dict[str, list[dict]]:
    """Keep display-name evidence scoped to a complete configured voice key.

    One actor alias may have multiple displayed identities. Names must never
    propagate by the alias alone, and a conflicting exact key stays unknown.
    """
    path = data_paths.get("FileCfg/OngoingTipsConfigTemplateTb.json")
    if not path or not path.exists():
        return {}
    payload = read_json(path)
    rows = payload.get("IAEFFFFLKNB", []) if isinstance(payload, dict) else []
    candidates = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        text_key, name_key = row.get("FGAHJLHNEDB"), row.get("BLOGJEGIBOH")
        if not isinstance(text_key, str) or not isinstance(name_key, str):
            continue
        if hasattr(text_map, "__contains__") and text_key not in text_map:
            continue
        name = text_map.get(name_key)
        if not name or name in _GENERIC_NAMES or name in _TIPS_NAME_IGNORE:
            continue
        # Preserve the displayed identity for the selected protagonist route.
        name = clean_text(name, protagonist).text
        fields = ("CIBKAFBOGCI", "PFOBGIIIICG") if protagonist == "M" else ("PFOBGIIIICG", "CIBKAFBOGCI")
        voice = next((row.get(field) for field in fields if row.get(field)), None)
        if not isinstance(voice, str) or not voice or voice.startswith(("Play_", "Stop_")):
            continue
        candidates.setdefault(voice, []).append({"source": "FileCfg/OngoingTipsConfigTemplateTb.json",
                                                "source_key": text_key, "name_key": name_key, "name": name,
                                                "row_id": row.get("IDGNMKGGEGK")})
    return {voice: evidence for voice, evidence in candidates.items()
            if len({item["name"] for item in evidence}) == 1}


def resolve_ongoing_voice_names(speakers: dict[str, SpeakerInfo], evidence: dict[str, list[dict]], text_map) -> int:
    count = 0
    for key, info in speakers.items():
        link = info.perform or {}
        if info.speaker or link.get("avatars") or link.get("is_narration") or link.get("is_option"):
            continue
        voices = link.get("voice_keys") or []
        # Every reference needs the same exact voice key/name evidence. Partial
        # or mixed references must not acquire a name from one occurrence.
        occurrences = link.get("occurrences") or []
        if not voices or any(voice not in evidence for voice in voices):
            continue
        if not occurrences or any(not item.get("voice_keys") or item.get("is_narration")
                                  or item.get("is_option") for item in occurrences):
            continue
        values = [item for voice in voices for item in evidence[voice]]
        names = {item["name"] for item in values}
        if len(names) != 1:
            continue
        info.speaker = next(iter(names))
        info.confidence, info.source = 0.95, "tips"
        link["speaker_evidence"] = {
            "kind": "exact_configured_voice", "voice_keys": voices, "references": values,
            "text_difference": any(text_map.get(item["source_key"]) != text_map.get(key) for item in values),
        }
        count += 1
    return count


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
    if no_speakers:
        return SpeakerIndex({}, stats), stats

    avatar_path = data_paths.get("FileCfg/AvatarBaseTemplateTb.json")
    if not avatar_path or not avatar_path.exists():
        print("warning: speaker inputs missing; continuing without per-line speakers")
        return SpeakerIndex({}, stats), stats

    en_map = load_language_map(data_paths, "EN")
    alias_map = load_alias_map(text_map, en_map, read_json(avatar_path))
    print(f"  alias table: {len(alias_map)} entries (EN names + AvatarBase)")
    tips = ongoing_tips_speakers(data_paths, text_map, alias_map, "M")
    if tips:
        print(f"  ongoing tips: {len(tips)} speaker keys")

    perform_path = data_paths.get("FileCfg/PerformTemplateTb.json")
    voice_path = data_paths.get("Data/_unsorted/VoiceData.json")
    speakers: dict[str, SpeakerInfo] = {}
    option_keys: set[str] = set()
    if game_dir is None or not perform_path or not voice_path:
        print("warning: game data missing; only ongoing-tip speakers available")
    else:
        speakers, option_keys = _perform_speakers(
            text_map, alias_map, perform_path, game_dir, cache_path, refresh, stats
        )

    # Ongoing tips cover in-level barks the Perform blocks cannot reach.
    for text_id, (name, alias) in tips.items():
        info = speakers.get(text_id)
        link = info.perform or {} if info else {}
        if info is None or (not info.speaker and not link.get("avatars")
                            and not link.get("is_narration") and not link.get("is_option")):
            speakers[text_id] = SpeakerInfo(
                name,
                alias or (info.alias if info else None),
                0.9,
                "tips",
                bool(info and info.has_voice),
                info.timeline if info else None,
                info.perform if info else None,
            )
            stats.tips_speakers += 1
    stats.tips_speakers += resolve_ongoing_voice_names(
        speakers, ongoing_voice_names(data_paths, text_map, "M"), text_map)
    _recount_speaker_gaps(speakers, stats)
    return _index_from_speakers(speakers, text_keys, stats, option_keys), stats


def _recount_speaker_gaps(speakers: dict[str, SpeakerInfo], stats: SpeakerStats) -> None:
    """Recount gaps after the avatar/tips passes.

    ``unresolved_aliases`` and ``ambiguous`` used to be incremented while
    scanning Perform links and never adjusted, so the reported numbers counted
    entries that a later pass had already resolved (3.2.0 reported 810 where
    only 372 were left).  Recounting keeps ``coverage.json`` honest.
    """
    voiced = [info for info in speakers.values() if info.has_voice and not info.speaker]
    stats.unresolved_aliases = sum(1 for info in voiced if info.alias)
    stats.ambiguous = sum(1 for info in voiced if not info.alias)


def _speaker_fingerprint(text_map, alias_map: dict[str, str], perform_path: Path, game_dir: Path) -> str:
    """Bind cache to tables, resolver code and local resource inventory.

    Resource updates are detected by version and block path/size/mtime. For
    in-place binary edits preserving all metadata, use --refresh.
    """
    root = game_dir / "ZenlessZoneZero_Data"
    inventory = []
    paths = [path for blocks in resource_block_dirs(game_dir) for path in blocks.rglob("*.blk")]
    paths.extend(root / rel for rel in ("Persistent/res_version_persist", "StreamingAssets/res_version")
                 if (root / rel).is_file())
    for path in sorted(paths):
        stat = path.stat()
        inventory.append((path.relative_to(root).as_posix(), stat.st_size, stat.st_mtime_ns))
    inputs = {
        "perform": sha256_file(perform_path),
        "textmap": sorted(text_map.items()),
        "aliases": sorted(alias_map.items()),
        "resolver": {name: sha256_file(Path(__file__).with_name(name))
                     for name in ("speakers.py", "perform.py", "catalog.py", "mhy1.py", "timeline.py", "odin.py",
                                  "perform_graph.py", "partner_dialogue.py", "street_dialogue.py")},
        "game": str(game_dir.resolve()),
        "game_version": read_game_version(game_dir),
        "blocks": inventory,
    }
    return hashlib.sha256(json.dumps(inputs, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _perform_speakers(
    text_map,
    alias_map: dict[str, str],
    perform_path: Path,
    game_dir: Path,
    cache_path: Path,
    refresh: bool,
    stats: SpeakerStats,
) -> tuple[dict[str, SpeakerInfo], set[str]]:
    fingerprint = _speaker_fingerprint(text_map, alias_map, perform_path, game_dir)
    if cache_path.exists() and not refresh:
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if payload.get("version") != CACHE_VERSION:
                raise ValueError("speaker cache version changed")
            if payload.get("fingerprint") != fingerprint:
                raise ValueError("speaker inputs/resources changed or fingerprint missing")
            speakers = {
                text_id: SpeakerInfo(**info)
                for text_id, info in payload.get("speakers", {}).items()
            }
            options = set(payload.get("options", []))
            for key, value in payload.get("stats", {}).items():
                if hasattr(stats, key):
                    setattr(stats, key, value)
            print(f"Loaded speaker cache: {len(speakers)} text ids, {len(options)} options")
            return speakers, options
        except Exception as exc:  # noqa: BLE001 - rebuild on corrupt cache
            print(f"Speaker cache unreadable, rebuilding: {exc}")

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
    for block_id in sorted(by_block):
        path = find_resource_block(game_dir, block_id)
        if path:
            block_paths.append(path)
        else:
            print(f"  warning: missing block {block_id}.blk")
    print(
        f"  perform assets: {len(asset_paths)} paths, {matched} matched, "
        f"{len(block_paths)} blocks"
    )
    if not block_paths:
        print("warning: no Perform blocks found; continuing without per-line speakers")
        return {}, set()

    # Agent interactions and street dialogue share the same typed node reader.
    # Only configured assets are selected; unrelated event/side assets remain
    # outside the exported scope unless they were already GalGame sources.
    routes = {path: sides for path, sides in configured_routes(perform_payload).items()
              if "/Data/GalGame/" in path or Path(path).stem.startswith(
                  ("Main_", "MainChat_") + PARTNER_DIALOGUE_PREFIXES + STREET_DIALOGUE_PREFIXES)}
    source_to_text, avatar_to_text, option_keys, scan_stats = scan_perform_blocks(block_paths, set(routes))
    stats.links = scan_stats.links
    stats.sources = scan_stats.sources
    stats.blocks = scan_stats.blocks
    stats.avatar_links = scan_stats.avatar_links
    stats.avatar_values = scan_stats.avatar_values
    print(
        f"Scan complete: {scan_stats.links} voice links, {scan_stats.sources} sources, "
        f"{scan_stats.avatar_links} avatar links, {scan_stats.avatar_values} text ids with avatar, "
        f"{len(option_keys)} options"
    )

    text_to_infos: dict[str, list[tuple[str | None, str | None, str]]] = {}
    for source, text_ids in source_to_text.items():
        alias = alias_from_source(source)
        speaker = resolve_alias(alias, alias_map) if alias else None
        for text_id in text_ids:
            text_to_infos.setdefault(text_id, []).append((speaker, alias, source))

    speakers: dict[str, SpeakerInfo] = {}
    for text_id, infos in text_to_infos.items():
        # Multiple voice banks can point at one text id. Distinct aliases do
        # not imply distinct speakers: a character may have a skin/voice-bank
        # alias. Only disagreeing resolved display names are ambiguous.
        named_speakers = {speaker for speaker, _, _ in infos if speaker}
        if len(named_speakers) == 1:
            speaker = next(iter(named_speakers))
            aliases = {alias for resolved, alias, _ in infos if resolved == speaker and alias}
            alias = next(iter(aliases)) if len(aliases) == 1 else None
            speakers[text_id] = SpeakerInfo(speaker, alias, 1.0, "voice", True)
        elif len(named_speakers) > 1:
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
        existing = speakers.get(text_id)
        if existing and existing.speaker:
            continue
        display = text_map.get(avatar_name) or resolve_alias(avatar_name, alias_map)
        if not display:
            continue
        # Keep the voice bit when avatar data resolves an otherwise unresolved
        # voice line; coverage must not silently turn it into an unvoiced line.
        speakers[text_id] = SpeakerInfo(
            display,
            avatar_name,
            0.95,
            "avatar",
            bool(existing and existing.has_voice),
        )
        stats.avatar_speakers += 1

    links = graph_links(scan_stats.graphs, routes)
    link_unused_copies(links, scan_stats.graphs, routes, text_map)
    for key, link in links.items():
        speakers[key] = structured_speaker(link, text_map, alias_map, speakers.get(key))
        if link.get("is_option"):
            option_keys.add(key)
    stats.perform_graphs = len(scan_stats.graphs)
    stats.perform_graph_errors = len(scan_stats.graph_errors)
    stats.perform_gender_keys = sum(link["explicit_gender"] for link in links.values())
    stats.perform_copy_keys = sum(bool(link.get("copy_of")) for link in links.values())
    print(f"  structured Perform: {stats.perform_graphs} assets, {stats.perform_gender_keys} gender keys, {stats.perform_graph_errors} parse failures")

    print("Finding ChatPlus timeline resources...")
    clips = scan_timeline_clips(game_dir, catalog, perform_payload)
    timeline_links = link_main_copies(clips, text_map, perform_payload)
    for key, link in timeline_links.items():
        avatar = link["avatar"]
        display = text_map.get(avatar) if avatar else None
        aliases = {VOICE_RE.fullmatch(voice)[2] for voice in link["voice_keys"]}
        alias = next(iter(aliases)) if len(aliases) == 1 else None
        if not display and alias:
            display = resolve_alias(alias, alias_map)
        existing = speakers.get(key)
        # The timeline's avatar is the displayed identity, even when a voice
        # bank belongs to a character whose identity is hidden in this scene.
        speakers[key] = SpeakerInfo(
            display or (existing.speaker if existing else None), alias, 0.95,
            "timeline", bool(link["voice_keys"]), link,
        )
    stats.timeline_clips = len(clips)
    stats.timeline_mapped = len(timeline_links)
    print(f"  timeline clips: {len(clips)}, main keys linked: {len(timeline_links)}")

    stats.text_ids = len(speakers)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "fingerprint": fingerprint,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "speakers": {key: asdict(value) for key, value in speakers.items()},
        "options": sorted(option_keys),
        "stats": asdict(stats),
        "perform_inventory": {path: {"name": graph.name, "keys": sorted(graph.keys), "gender_conditions": graph.conditions,
                                     "status": graph.status, "null_nodes": graph.null_nodes}
                              for path, graph in scan_stats.graphs.items()},
        "perform_graph_errors": scan_stats.graph_errors,
    }
    from .writers import _atomic_write_text
    _atomic_write_text(cache_path, json.dumps(payload, ensure_ascii=False))
    print(f"Cached speaker map: {cache_path}")
    return speakers, option_keys


def _index_from_speakers(
    speakers: dict[str, SpeakerInfo],
    text_keys: set[str],
    stats: SpeakerStats,
    options: set[str] | None = None,
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
    return SpeakerIndex(key_info, stats, options)


class SpeakerIndex:
    def __init__(
        self,
        key_info: dict[str, SpeakerInfo],
        stats: SpeakerStats,
        options: set[str] | None = None,
    ):
        self._key_info = key_info
        self.stats = stats
        self._options = options or set()
        self._canonical_options = {canonical_text_id(k) for k in self._options}

    def lookup(self, key: str) -> SpeakerInfo | None:
        return self._key_info.get(key)

    def is_option(self, key: str) -> bool:
        if not self._options:
            return False
        if key in self._options:
            return True
        return canonical_text_id(key) in self._canonical_options

    def __len__(self) -> int:
        return len(self._key_info)
