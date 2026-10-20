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

CACHE_VERSION = 5

_TIPS_VOICE_RE = re.compile(r"^[A-Za-z]+_Chapter\w+_([A-Za-z]+)_\d+_\d+$")
_TIPS_NAME_IGNORE = {"选项", "玩家选项", "旁白", "咨询", "购买", "找零"}

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
    out: dict[str, tuple[str, str | None]] = {}
    if not path or not path.exists():
        return out
    payload = read_json(path)
    rows = payload.get("IAEFFFFLKNB", []) if isinstance(payload, dict) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text_key = row.get("FGAHJLHNEDB")
        if not isinstance(text_key, str) or not text_key.startswith(("Main_", "MainChat_")):
            continue
        name = text_map.get(str(row.get("BLOGJEGIBOH") or ""))
        if name and name not in _GENERIC_NAMES and name not in _TIPS_NAME_IGNORE:
            out[text_key] = (name, None)
            continue
        primary, secondary = (
            ("CIBKAFBOGCI", "PFOBGIIIICG") if protagonist == "M" else ("PFOBGIIIICG", "CIBKAFBOGCI")
        )
        voice = row.get(primary) or row.get(secondary) or ""
        match = _TIPS_VOICE_RE.match(voice) if isinstance(voice, str) else None
        alias = match.group(1) if match else None
        speaker = resolve_alias(alias, alias_map) if alias else None
        if speaker:
            out[text_key] = (speaker, alias)
    return out


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
        if info is None or not info.speaker:
            speakers[text_id] = SpeakerInfo(
                name,
                alias or (info.alias if info else None),
                0.9,
                "tips",
                bool(info and info.has_voice),
            )
            stats.tips_speakers += 1
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


def _perform_speakers(
    text_map,
    alias_map: dict[str, str],
    perform_path: Path,
    game_dir: Path,
    cache_path: Path,
    refresh: bool,
    stats: SpeakerStats,
) -> tuple[dict[str, SpeakerInfo], set[str]]:
    if cache_path.exists() and not refresh:
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if payload.get("version") != CACHE_VERSION:
                raise ValueError("speaker cache version changed")
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
        return {}, set()

    source_to_text, avatar_to_text, option_keys, scan_stats = scan_perform_blocks(block_paths)
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

    stats.text_ids = len(speakers)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "speakers": {key: asdict(value) for key, value in speakers.items()},
        "options": sorted(option_keys),
        "stats": asdict(stats),
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
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
