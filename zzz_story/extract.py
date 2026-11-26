"""Main extraction pipeline."""

from __future__ import annotations

import bisect
import hashlib
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .chapters import (
    CHAPTER_ORDER_SCALE,
    chapter_info,
    parse_season_chapter,
    season_chapter_token,
)
from .clean import catalog_text, clean_text, dialogue_readings
from .dedupe import display_side
from .extras import candidate_keys as extra_candidate_keys
from .extras import extract_extras
from .fetch import (
    DEFAULT_VERSION,
    PROJECT_ROOT,
    detect_game_dir,
    ensure_data,
    fetch_source_version,
    read_game_version,
    read_json,
    sha256_file,
)
from .keys import (
    LEGACY_GALGAME_RE,
    ParsedKey,
    natural_scene_key,
    parse_key,
    source_gender_pairs,
)
from .lore import extract_lore
from .narrative import (
    annotate_attribution,
    annotate_content,
    annotate_local_order,
    attribution_summary,
)
from .partner_dialogue import PARTNER_DIALOGUE_PREFIXES
from .source_audit import (
    annotate_source_variants,
    collect_source_variants,
)
from .speakers import _MANUAL_ALIASES, SpeakerInfo, build_speaker_index, normalize_name
from .street_dialogue import STREET_DIALOGUE_PREFIXES
from .supplement_context import annotate_supplement_context, scan_comic_context
from .textmap import TextMap, load_language_map, load_text_map
from .validate import validate_records
from .writers import write_json, write_jsonl

MAIN_FAMILIES = {
    "GalGame",
    "Chat",
    "OngoingLevel",
    "OngoingMainCity",
    "Ongoing",
    "OngoingAntique",
    "BubbleStory",
    "Bubble",
    "ChatAudio",
    "ChatPlus",
}
# Deterministic per-chapter block order.  GalGame (S2+) and MainChat (S1)
# carry the main story; the rest is supplementary dialogue.  Cross-family
# chronology does not exist in the public data, so families are not
# interleaved on purpose.
FAMILY_ORDER = {
    "GalGame": 0,
    "MainChat": 1,
    "Chat": 2,
    "ChatAudio": 3,
    "ChatPlus": 4,
    "BubbleStory": 5,
    "Bubble": 6,
    "OngoingLevel": 7,
    "OngoingMainCity": 8,
    "Ongoing": 9,
    "OngoingAntique": 10,
}

NAME_IGNORE = {"选项", "玩家选项", "旁白"}
OPTION_SPEAKERS = {"选项", "玩家选项"}
PLAYER_NAMES = {"铃", "哲"}
# Explicit male forms of address; lines using them are male-branch content.
MALE_ADDRESS = ("小师弟", "师弟", "哲小哥", "哲先生", "哲哥")
# Test/dev or side-content tables that are not part of the shipped main story.
EXCLUDED_CHAPTERS = {"Chapter020", "Chapter080", "PortChapter110"}
# Fallback costume / flashback forms of the two protagonists, mirroring the
# game's GalNPC<Form>Belle / GalNPC<Form>Wise table.  The live extraction
# derives the actual set from the TextMap (see ``costume_prefixes``) and only
# falls back to this list when those keys are unavailable:
#   玩家铃/玩家哲, 学生铃/学生哲, 道士铃/道士哲, 泳装铃/泳装哲, 佩洛伊斯铃/佩洛伊斯哲
# A bare "short name ending in 铃/哲" rule would also catch props such as 门铃.
DEFAULT_COSTUME_PREFIXES = frozenset({"玩家", "学生", "道士", "泳装", "佩洛伊斯"})


@dataclass
class ExtractStats:
    selected_keys: int = 0
    line_keys: int = 0
    name_keys: int = 0
    missing_text: int = 0
    missing_examples: list[str] = field(default_factory=list)
    total_lines: int = 0
    speaker_lines: int = 0
    voice_linked: int = 0
    voice_speaker: int = 0
    scene_fallback: int = 0
    scene_alias: int = 0
    speaker_null: int = 0
    options_count: int = 0
    deduped: int = 0
    branch_filtered: int = 0
    gender_pair_filtered: int = 0
    by_family: dict[str, int] = field(default_factory=dict)
    by_chapter: dict[str, int] = field(default_factory=dict)
    supplement_lines: int = 0
    raw_text_omitted: int = 0
    speaker_stats: dict = field(default_factory=dict)


# Comic/CS resources carry no chapter token of their own, so a CS key's prefix
# is its only chapter hint: CS_21_01_010 means season 2, chapter 1.  Season 1
# tokens are irregular (01.5 / 028 / 05.2 ...) and stay explicit; season 2+ is
# derived through chapters.season_chapter_token so that renumbering the main
# story can never silently move old content under a new season again.
CS_SPECIAL_CHAPTERS: dict[str, tuple[str, str, int]] = {
    "00": ("Chapter00", "序章", 10),
    "01": ("Chapter01", "第一季 第一章", 20),
    "01.5": ("Chapter015", "第一季 第一章间章", 25),
    "02": ("Chapter02", "第一季 第二章", 30),
    "02.5": ("Chapter025", "第一季 第二章间章", 40),
    "028": ("Chapter028", "第一季 第二章", 45),
    "03": ("Chapter03", "第一季 第三章", 50),
    "03.5": ("Chapter035", "第一季 第三章间章", 55),
    "04": ("Chapter04", "第一季 第四章", 60),
    "04.5": ("Chapter045", "第一季 第四章间章", 65),
    "05": ("Chapter05", "第一季 第五章", 90),
    "05.2": ("Chapter052", "第一季 第五章", 92),
    "05.5": ("Chapter055", "第一季 第五章间章", 95),
    "05.8": ("Chapter058", "第一季 第五章", 98),
    "Burnice": ("Story_Burnice", "角色过场 · 柏妮思", 1000),
    "Lighter": ("Story_Lighter", "角色过场 · 莱特", 1010),
    "Lycaon": ("Story_Lycaon", "角色过场 · 莱卡恩", 1020),
    "Nekomiya": ("Story_Nekomiya", "角色过场 · 猫又", 1030),
    "QingYi": ("Story_QingYi", "角色过场 · 青衣", 1040),
    "Rina": ("Story_Rina", "角色过场 · 丽娜", 1050),
}


def cs_chapter(token: str) -> tuple[str, str, int]:
    """Resolve a CS prefix into ``(chapter_token, chapter_label, chapter_order)``."""
    special = CS_SPECIAL_CHAPTERS.get(token)
    if special:
        return special
    parsed = parse_season_chapter(token)
    if parsed and parsed[0] >= 2:
        chapter_token = f"Chapter{season_chapter_token(*parsed)}"
        info = chapter_info(chapter_token)
        return chapter_token, info.label, info.order
    return f"CS_{token}", f"过场动画（{token}）", 900 * CHAPTER_ORDER_SCALE


def _load_scene_titles(data_paths: dict[str, Path], text_map: TextMap, *,
                       json_loader: Callable[[Path], object] | None = None) -> dict[str, str]:
    titles: dict[str, str] = {}
    perform_path = data_paths.get("FileCfg/PerformTemplateTb.json")
    if perform_path and perform_path.exists():
        try:
            perf = (json_loader or read_json)(perform_path)
            rows = perf.get("IAEFFFFLKNB", []) if isinstance(perf, dict) else []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                title_key = row.get("PMINKNAOFOO")
                if not title_key:
                    continue
                title = text_map.get(title_key)
                if not title:
                    continue
                title = catalog_text(title).strip("「」")
                if not title:
                    continue
                asset = row.get("BCKKFAEFDPP", "")
                m = re.search(r"Chapter\w+/[A-Za-z]+_Chapter\w+_(\w+)\.asset", asset, re.IGNORECASE)
                if m:
                    titles[m.group(1)] = title
                pid = str(row.get("PFOAJKNPCHL") or "")
                if pid:
                    titles[pid] = title
        except Exception:
            pass

    for key, val in text_map.items():
        if not (key.startswith("Title_") or key.startswith("Quest_VHSPerformName_")):
            continue
        if not val or not isinstance(val, str):
            continue
        cleaned = catalog_text(val).strip("「」")
        if not cleaned:
            continue
        if key.startswith("Title_"):
            sc = key[6:]
            titles.setdefault(sc, cleaned)
        else:
            sc = key[len("Quest_VHSPerformName_"):]
            titles.setdefault(sc, cleaned)

    return titles



# Perform 资源文件名里的剧情族和场景号：Main_GalGame_Chapter240_124000001、Side_GalGame_RAB_100000026。
# 旧式命名（GalGame_Chapter00_01、C00_01 等）和记录的场景号不是同一套编号，不在这里配。
_PERFORM_SCENE_RE = re.compile(r"[A-Za-z]+_([A-Za-z]+)_(?:\w+_)?(\d+)\.asset$")
# 策划写在梗概位置的占位说明（「gal跳过内容」「黑屏跳过战斗」「关卡3-占位」），不是剧情。
_INTRO_PLACEHOLDER_RE = re.compile(r"跳过|占位|黑屏|刷怪|\bTL\b|gal", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _load_scene_intros(data_paths: dict[str, Path], text_map: TextMap, *,
                       json_loader: Callable[[Path], object] | None = None) -> dict[tuple[str, str], str]:
    """Scene synopses: the one-sentence outline the game shows for each scene (``Intro_*``).

    Keyed by ``(family, scene)`` from the Perform row's asset file name, and only matched to a
    record with exactly that family and scene: a synopsis on the wrong scene is worse than none,
    so there are no loose fallbacks (``Intro_<scene>`` keys, stripped or padded scene numbers).
    Gendered synopses retain both readings.
    """
    intros: dict[tuple[str, str], str] = {}
    perform_path = data_paths.get("FileCfg/PerformTemplateTb.json")
    if not (perform_path and perform_path.exists()):
        return intros
    try:
        perf = (json_loader or read_json)(perform_path)
    except Exception:
        return intros
    rows = perf.get("IAEFFFFLKNB", []) if isinstance(perf, dict) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw = text_map.get(row.get("BCGIEODKGDG") or "")
        intro = catalog_text(raw).strip() if isinstance(raw, str) else ""
        if len(_CJK_RE.findall(intro)) < 4 or _INTRO_PLACEHOLDER_RE.search(intro):
            continue
        name = (row.get("BCKKFAEFDPP") or "").rsplit("/", 1)[-1]
        match = _PERFORM_SCENE_RE.fullmatch(name)
        if match:
            intros[(match.group(1), match.group(2))] = intro
    return intros


def _load_archive_order(data_paths: dict[str, Path], text_map: TextMap) -> tuple[dict[str, tuple[int, int]], dict[int, str]]:
    """Archive table order, with validated legacy quest-id associations.

    The archive enumerates replay entries, not necessarily their playback
    order. Newer ids can be scene ids themselves; only retain the legacy
    division rule when its result actually resolves to a named quest.
    """
    quest_names: dict[int, str] = {}
    quest_path = data_paths.get("FileCfg/QuestConfigTemplateTb.json")
    if quest_path and quest_path.exists():
        rows = read_json(quest_path)
        rows = rows.get("IAEFFFFLKNB", []) if isinstance(rows, dict) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = catalog_text(text_map.get(str(row.get("ANCOBODLNIK", ""))))
            if row.get("ODCODEPMLGG") and name:
                quest_names[row["ODCODEPMLGG"]] = name

    scene_order: dict[str, tuple[int, int]] = {}
    archive_path = data_paths.get("FileCfg/ArchivePerformTemplateTb.json")
    if archive_path and archive_path.exists():
        rows = read_json(archive_path)
        rows = rows.get("IAEFFFFLKNB", []) if isinstance(rows, dict) else []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            scene = row.get("JFHCIJHJLOH")
            archive_id = row.get("PFOAJKNPCHL")
            if scene and archive_id:
                quest_id = archive_id // 100
                scene_order[str(scene)] = (index, quest_id if quest_id in quest_names else 0)
    return scene_order, quest_names


def _galgame_scene_positions(scenes: list[str], scene_order: dict[str, tuple[int, int]]) -> dict[str, float]:
    """List scenes deterministically using the replay archive table.

    Scenes missing from the archive (prologue, unreplayable fights) keep
    their numeric order and are slotted between their archived neighbours.
    """
    archived = sorted(
        (scene_order[scene][0], scene) for scene in scenes if scene in scene_order
    )
    if not archived:
        return {}
    positions = {scene: float(index) for index, (_, scene) in enumerate(archived)}
    by_number = sorted(
        (int(scene), positions[scene]) for _, scene in archived if scene.isdigit()
    )
    numbers = [number for number, _ in by_number]
    pending: dict[tuple[float, float], list[str]] = {}
    rest: list[str] = []
    for scene in scenes:
        if scene in positions:
            continue
        if not scene.isdigit() or not by_number:
            rest.append(scene)
            continue
        slot = bisect.bisect_left(numbers, int(scene))
        low = by_number[slot - 1][1] if slot else by_number[0][1] - 1.0
        high = by_number[slot][1] if slot < len(by_number) else by_number[-1][1] + 1.0
        if high <= low:
            # Numeric neighbours can appear in reverse archive order. That
            # gives no usable insertion interval; keep the scene in fallback.
            rest.append(scene)
            continue
        pending.setdefault((low, high), []).append(scene)
    for (low, high), group in pending.items():
        group.sort(key=int)
        step = (high - low) / (len(group) + 1)
        for index, scene in enumerate(group, 1):
            positions[scene] = low + step * index
    next_pos = max(positions.values()) + 1.0
    for scene in sorted(rest, key=natural_scene_key):
        positions[scene] = next_pos
        next_pos += 1.0
    return positions

def _line_sort_key(record: dict, scene_positions: dict[tuple[str, str], float]) -> tuple:
    info = chapter_info(record["chapter"])
    position = scene_positions.get((record["chapter"], record["scene"]))
    scene_key = (0, position) if position is not None else (1,) + natural_scene_key(record["scene"])
    return (
        info.order,
        FAMILY_ORDER.get(record["family"], 50),
        scene_key,
        record.get("_local_order", (record["line_no"], record["sub_no"] or 0)),
        record["line_no"],
        record["sub_no"] or 0,
        record["variant"] or "",
        record["source_key"],
    )


def _scene_metadata(family: str, scene: str, scene_order: dict[str, tuple[int, int]]) -> dict:
    """Expose the evidence behind deterministic listing order, never chronology."""
    archived = scene_order.get(scene) if family == "GalGame" else None
    return {
        "order_source": "archive_table" if archived else "source_key",
        "chronology_status": "unknown",
        "archive_order": archived[0] if archived else None,
        "quest_id": archived[1] if archived and archived[1] else None,
        "quest_source": "validated_archive_id" if archived and archived[1] else None,
    }


def _speaker_identity(speaker: str | None, costumes: frozenset[str]) -> tuple[str | None, str | None]:
    """Separate proven display-name forms from identity; do not merge by substring."""
    if not speaker:
        return None, None
    if _protagonist_side(speaker, costumes):
        return speaker[-1], speaker[:-1] or None
    match = re.fullmatch(r"(林德薇恩)「(中挽昼|皮肤版)」", speaker)
    if match:
        return match.group(1), match.group(2)
    return speaker, None


def _scene_names(names_by_scene: dict[tuple[str, str], list[str]], names_global: dict[tuple[str, str], list[str]], chapter: str, scene: str, family: str) -> list[str]:
    values = names_by_scene.get((f"{family}:{chapter}", scene))
    if values is None:
        values = names_global.get((chapter, scene), [])
    out: list[str] = []
    for value in values:
        value = value.strip()
        if value and value not in out:
            out.append(value)
    return out


def _cache_root(data_dir: Path | None, lang: str) -> Path:
    """Return a speaker/source cache namespace tied to the input dataset.

    The default CHS dataset keeps the historical path for compatibility.  An
    explicitly supplied data directory (or a non-CHS language) gets a stable
    digest namespace so its speaker map cannot accidentally reuse the default
    3.2.0 cache.
    """
    root = PROJECT_ROOT / "data" / "cache" / DEFAULT_VERSION
    if data_dir is None and lang.upper() == "CHS":
        return root
    identity = f"{lang.upper()}\0{Path(data_dir).resolve() if data_dir else 'default'}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return root / f"source-{digest}"


def extract(
    *,
    out_dir: Path,
    data_dir: Path | None = None,
    game_dir: Path | None = None,
) -> ExtractStats:
    """Write the MCP corpus, retaining both protagonist routes."""
    lang = "CHS"
    out_dir.mkdir(parents=True, exist_ok=True)
    if any(out_dir.iterdir()):
        raise FileExistsError(f"提取工作目录须为空：{out_dir}")
    game_dir = detect_game_dir(game_dir)
    game_version = read_game_version(game_dir) if game_dir else ""
    data_paths = ensure_data(data_dir=data_dir, game_version=game_version)
    input_tables: dict[Path, object] = {}

    def load_input_json(path: Path):
        if path not in input_tables:
            input_tables[path] = read_json(path)
        return input_tables[path]

    print("Loading TextMap...")
    text_map = load_text_map(data_paths, language=lang)
    print(f"  {len(text_map)} entries loaded")
    costumes = costume_prefixes(text_map)
    print(f"  protagonist forms: {len(costumes)} ({', '.join(sorted(costumes))})")
    scene_titles = _load_scene_titles(data_paths, text_map, json_loader=load_input_json)
    scene_intros = _load_scene_intros(data_paths, text_map, json_loader=load_input_json)
    scene_order, quest_names = _load_archive_order(data_paths, text_map)
    if scene_order:
        print(f"  story archive: {len(scene_order)} ordered scenes, {len(quest_names)} quest names")

    if game_dir:
        print(f"Game directory: {game_dir}")
        if game_version:
            print(f"  local version: {game_version}")
    else:
        print("warning: game directory not found; per-line speakers will be unavailable")

    stats = ExtractStats()
    names_by_scene: dict[tuple[str, str], list[str]] = {}
    names_global: dict[tuple[str, str], list[str]] = {}
    pending: list[dict] = []
    supplement: list[dict] = []
    source_audit_keys: list[str] = []
    # TextMap contains many repeated values (especially short pauses and
    # common acknowledgements).  Cleaning markup is pure for a given raw
    # value/protagonist, so reuse the result within this extraction run.
    clean_cache = {}

    def clean_cached(raw: str, gender: str):
        cache_key = (raw, gender)
        cleaned = clean_cache.get(cache_key)
        if cleaned is None:
            cleaned = clean_text(raw, gender)
            clean_cache[cache_key] = cleaned
        return cleaned

    candidates = []
    for key in text_map.keys():
        if not (
            key.startswith(("Main_", "MainChat_", "Comic_", "CS_"))
            or LEGACY_GALGAME_RE.match(key)
        ):
            continue
        parsed = parse_key(key)
        if parsed is None:
            continue
        if parsed.kind == "other":
            continue
        if parsed.chapter_token in EXCLUDED_CHAPTERS:
            continue
        if parsed.family == "MainChat" and not parsed.chapter_token.startswith("Chapter"):
            continue
        if parsed.family in MAIN_FAMILIES or parsed.family == "MainChat":
            source_audit_keys.append(key)
        if parsed.kind == "source_variant":
            continue
        candidates.append(parsed)

    # Index both alternatives before choosing one. Some legacy F-suffixed
    # keys are referenced by the Wise asset and their base keys by Belle's.
    main_keys = {p.key: p.route_variant for p in candidates if p.family in MAIN_FAMILIES or p.family == "MainChat"}
    text_keys = {p.key for p in candidates if p.kind == "line" and p.key in main_keys and text_map.get(p.key)}
    extra_candidates = extra_candidate_keys(text_map)
    text_keys.update(item.key for item in extra_candidates if item.kind == "line")
    text_keys.update(key for key in text_map.keys() if key.startswith(PARTNER_DIALOGUE_PREFIXES + STREET_DIALOGUE_PREFIXES))
    cache_root = _cache_root(data_dir, lang)
    en_map = load_language_map(data_paths, "EN")
    speaker_index, speaker_stats = build_speaker_index(
        text_map=text_map, text_keys=text_keys, data_paths=data_paths, game_dir=game_dir,
        cache_path=cache_root / "speakers_cache.json", protagonist=None,
        en_map=en_map, json_loader=load_input_json,
    )
    del en_map
    pairs = source_gender_pairs(main_keys, text_map, speaker_index)
    for parsed in candidates:
        key = parsed.key
        if parsed.family in MAIN_FAMILIES or parsed.family == "MainChat":
            info = speaker_index.lookup(key)
            route = pairs[key][1] if key in pairs else display_side(info, main_keys[key])
            raw = text_map.get(key)
            cleaned = clean_cached(raw, route or "M")
            if parsed.kind == "name":
                if cleaned.text:
                    stats.selected_keys += 1
                    stats.name_keys += 1
                    scoped = (f"{parsed.family}:{parsed.chapter_token}", parsed.scene)
                    for _, name, _ in dialogue_readings(cleaned, None, route):
                        names_by_scene.setdefault(scoped, []).append(name)
                        names_global.setdefault((parsed.chapter_token, parsed.scene), []).append(name)
                continue
            if not cleaned.text:
                if not raw:
                    stats.missing_text += 1
                continue
            for side, text, name in dialogue_readings(cleaned, info.speaker if info else None, route):
                record = _pending_record(parsed, text, raw, cleaned.variants, side)
                record["_speaker"] = name
                pending.append(record)
            stats.selected_keys += 1
            stats.line_keys += 1
            if stats.line_keys % 10000 == 0:
                print(f"  parsed {stats.line_keys} line keys...")
            continue

        if parsed.family in {"Comic", "CS"}:
            raw = text_map.get(key)
            if not raw:
                continue
            cleaned = clean_cached(raw, "M")
            if not cleaned.text:
                continue
            if parsed.family == "CS":
                ch_token, ch_label, ch_order = cs_chapter(parsed.chapter_token)
            else:
                ch_token = "Comic"
                ch_label = "动态漫画"
                ch_order = 999 * CHAPTER_ORDER_SCALE
            supplement.append(
                {
                    "family": parsed.family,
                    "source_key": key,
                    "chapter": ch_token,
                    "chapter_label": ch_label,
                    "chapter_order": ch_order,
                    "scene": parsed.scene,
                    "line_no": parsed.line_no or 0,
                    "text": cleaned.text,
                    "raw_text": raw,
                    "text_variants": cleaned.variants,
                    "order_source": "source_key",
                    "chronology_status": "unknown",
                    "context_status": "unlinked" if parsed.family == "Comic" else "chapter_only",
                }
            )
            stats.supplement_lines += 1

    print(f"  line keys: {stats.line_keys}, name keys: {stats.name_keys}, missing text: {stats.missing_text}")
    source_variants = collect_source_variants(text_map, source_audit_keys)
    input_tables.pop(data_paths.get("FileCfg/OngoingTipsConfigTemplateTb.json"), None)
    stats.speaker_stats = asdict(speaker_stats)
    comic_context = {"links": {}, "errors": {}, "stats": {}}
    if game_dir and any(row["family"] == "Comic" for row in supplement):
        perform_path = data_paths.get("FileCfg/PerformTemplateTb.json")
        if perform_path:
            print("Finding comic scene and speaker references...")
            comic_context = scan_comic_context(game_dir, load_input_json(perform_path),
                                               cache_root / "comic_context_cache.json")
    comic_stats = annotate_supplement_context(supplement, comic_context, protagonist=None)
    input_tables.pop(data_paths.get("FileCfg/PerformTemplateTb.json"), None)

    records: list[dict] = []
    for pending_record in pending:
        source_key = pending_record["_source_key"]
        chapter = pending_record["_chapter"]
        scene = pending_record["_scene"]
        family = pending_record["_family"]
        scene_names = _scene_names(names_by_scene, names_global, chapter, scene, family)
        info: SpeakerInfo | None = speaker_index.lookup(source_key)
        has_voice = bool(info and info.has_voice)
        alias = info.alias if info else None
        confidence = info.confidence if info else 0.0
        speaker_source = info.source if info else "none"

        gender = pending_record["_gender"]
        speaker = _normalize_speaker(pending_record["_speaker"], gender or "M")
        forced_option = speaker in OPTION_SPEAKERS
        if speaker in NAME_IGNORE:
            speaker = None

        if has_voice:
            stats.voice_linked += 1
            if speaker:
                stats.voice_speaker += 1

        is_opt = forced_option
        if not is_opt and (not speaker or speaker in PLAYER_NAMES):
            if source_key in speaker_index._options:
                is_opt = True
            elif speaker_index.is_option(source_key):
                is_opt = True
            elif "_Option" in source_key or "_Opt" in source_key:
                is_opt = True

        if is_opt:
            line_type = "option"
            speaker = None
            stats.options_count += 1
        elif speaker:
            line_type = "dialogue"
        elif has_voice:
            line_type = "unknown"
        else:
            line_type = "narration"

        info_chapter = chapter_info(chapter)
        display_speakers = [name for name in scene_names if name not in NAME_IGNORE]
        quest_name = None
        if family == "GalGame" and scene in scene_order:
            quest_name = quest_names.get(scene_order[scene][1])
        raw = pending_record["_raw"]
        raw_text = raw if raw != pending_record["_text"] else None
        record = {
            "line_id": "",
            "chapter": chapter,
            "chapter_label": info_chapter.label,
            "chapter_order": info_chapter.order,
            "scene": scene,
            "scene_act": 0,
            "scene_title": None,
            "quest_name": quest_name,
            "family": family,
            "line_no": pending_record["_line_no"],
            "sub_no": pending_record["_sub_no"],
            "variant": pending_record["_variant"],
            "speaker": speaker,
            "speaker_alias": alias,
            "speaker_confidence": round(confidence, 3),
            "speaker_source": speaker_source if speaker else ("voice" if has_voice else "none"),
            "has_voice": has_voice,
            "text": pending_record["_text"],
            "raw_text": raw_text,
            "text_variants": pending_record["_variants"],
            "selected_variant": gender,
            "source_key": source_key,
            "line_type": line_type,
            "scene_speakers": display_speakers,
            "order": 0,
            **_scene_metadata(family, scene, scene_order),
        }
        record["speaker_id"], record["speaker_form"] = _speaker_identity(speaker, costumes)
        if info and info.timeline:
            record["timeline"] = info.timeline
        if info and info.perform:
            record["perform"] = info.perform
        records.append(record)

    del pending
    clean_cache.clear()
    annotate_source_variants(records, source_variants)

    _mark_unattributed_scenes(records)
    annotate_attribution(records)
    annotate_content(records)

    galgame_scenes: dict[str, list[str]] = {}
    seen_galgame_scenes: set[tuple[str, str]] = set()
    for record in records:
        if record["family"] == "GalGame":
            identity = record["chapter"], record["scene"]
            if identity not in seen_galgame_scenes:
                seen_galgame_scenes.add(identity)
                galgame_scenes.setdefault(record["chapter"], []).append(record["scene"])
    scene_positions: dict[tuple[str, str], float] = {}
    archived_counts: dict[str, int] = {}
    for chapter, scenes in galgame_scenes.items():
        archived_counts[chapter] = sum(scene in scene_order for scene in scenes)
        for scene, position in _galgame_scene_positions(scenes, scene_order).items():
            scene_positions[(chapter, scene)] = position
    for record in records:
        position = scene_positions.get((record["chapter"], record["scene"]))
        archived_count = archived_counts.get(record["chapter"], 0)
        if record["family"] == "GalGame" and record["archive_order"] is None and position is not None and position < archived_count:
            record["order_source"] = "archive_interpolation"
    annotate_local_order(records)
    records.sort(key=lambda record: _line_sort_key(record, scene_positions))
    for record in records:
        record.pop("_local_order", None)
    scene_acts_by_chapter: dict[str, dict[tuple[str, str], int]] = {}
    for record in records:
        chapter = record["chapter"]
        scene = record["scene"]
        acts = scene_acts_by_chapter.setdefault(chapter, {})
        scene_key = (record["family"], scene)
        if scene_key not in acts:
            acts[scene_key] = len(acts) + 1
        record["scene_act"] = acts[scene_key]
        title = (
            scene_titles.get(scene)
            or scene_titles.get(scene.lstrip("0"))
            or scene_titles.get(scene.zfill(4))
        )
        record["scene_title"] = title
        record["scene_intro"] = scene_intros.get((record["family"], scene))

    _assign_line_ids(records)
    stats.total_lines = len(records)
    stats.voice_linked = sum(row["has_voice"] for row in records)
    stats.voice_speaker = sum(row["has_voice"] and bool(row["speaker"]) for row in records)
    stats.raw_text_omitted = sum(1 for record in records if record["raw_text"] is None)
    stats.speaker_lines = sum(1 for record in records if record["speaker"])
    stats.speaker_null = stats.total_lines - stats.speaker_lines
    for record in records:
        stats.by_family[record["family"]] = stats.by_family.get(record["family"], 0) + 1
        # Key by token: several chapters share a label (04/040, 05/050, 08/09/090),
        # so a label-keyed counter silently merges them.
        stats.by_chapter[record["chapter"]] = stats.by_chapter.get(record["chapter"], 0) + 1

    supplement.sort(
        key=lambda item: (
            0 if item["family"] == "CS" else 1,
            item.get("chapter_order", 999 * CHAPTER_ORDER_SCALE),
            item["chapter"],
            natural_scene_key(item["scene"]),
            item["line_no"],
            item["source_key"],
        )
    )
    subtitle_rows = []
    for row in supplement:
        cleaned = clean_text(row["raw_text"], "M")
        for side, text, name in dialogue_readings(cleaned, row.get("speaker"), None):
            subtitle = {**row, "text": text, "selected_variant": side}
            if name:
                subtitle["speaker"] = name
            subtitle_rows.append(subtitle)
    supplement = subtitle_rows
    _assign_supplement_ids(supplement)
    stats.supplement_lines = len(supplement)
    quality = _quality_metrics(records, supplement)

    print("正在提取活动、支线和代理人剧情……")
    extra_records, extra_stats = extract_extras(
        text_map, speaker_index=speaker_index, scene_order=scene_order,
        quest_names=quest_names, candidates=extra_candidates,
    )
    for record in extra_records:
        if intro := scene_intros.get((record["family"], record["scene"])):
            record["scene_intro"] = intro
    issues = validate_records(records, supplement, extra_records)
    errors = [issue for issue in issues if issue.level == "error"]
    if errors:
        raise ValueError("语料校验失败：" + "；".join(str(issue) for issue in errors[:8]))
    write_jsonl(({key: value for key, value in row.items() if value is not None} for row in records),
                out_dir / "story.jsonl")
    write_jsonl(({key: value for key, value in row.items() if value is not None} for row in supplement),
                out_dir / "supplement.jsonl")
    write_jsonl(extra_records, out_dir / "extra.jsonl")

    print("正在提取设定、互动和短信……")
    avatar_path = data_paths.get("FileCfg/AvatarBaseTemplateTb.json")
    avatar_base = load_input_json(avatar_path) if avatar_path and avatar_path.exists() else None
    lore_stats = extract_lore(text_map, avatar_base, out_dir, speaker_index=speaker_index, data_paths=data_paths)
    input_tables.clear()

    source_root = data_dir if data_dir is not None else PROJECT_ROOT / "data" / "cache" / DEFAULT_VERSION
    source_version = fetch_source_version(source_root, required_files=list(data_paths))
    if source_version == "unknown":
        print("  warning: 数据文件没有可核验的版本来源；source_version=unknown，manifest 保留输入哈希")
    file_hashes = {}
    for rel, path in data_paths.items():
        try:
            file_hashes[rel] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
        except OSError:
            file_hashes[rel] = {"sha256": "", "bytes": 0}

    chapter_rows: dict[str, dict] = {}
    for record in records:
        row = chapter_rows.setdefault(
            record["chapter"],
            {
                "token": record["chapter"],
                "label": record["chapter_label"],
                "order": record["chapter_order"],
                "known": chapter_info(record["chapter"]).known,
                "lines": 0,
                "supplement_lines": 0,
            },
        )
        row["lines"] += 1
    for item in supplement:
        row = chapter_rows.setdefault(
            item["chapter"],
            {
                "token": item["chapter"],
                "label": item["chapter_label"],
                "order": item["chapter_order"],
                "known": chapter_info(item["chapter"]).known,
                "lines": 0,
                "supplement_lines": 0,
            },
        )
        row["supplement_lines"] += 1
    chapters_manifest = sorted(chapter_rows.values(), key=lambda row: (row["order"], row["token"]))
    validation_manifest = {
        "errors": len(errors),
        "warnings": len(issues) - len(errors),
        "issues": [asdict(issue) for issue in issues],
    }

    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "language": lang,
        "source_version": source_version,
        "chapter_order_scale": CHAPTER_ORDER_SCALE,
        "local_game_version": game_version,
        # Basename only: the manifest travels inside the upload bundle, so the
        # user's absolute game path must not leak into it.
        "game_dir": game_dir.name if game_dir else "",
        "protagonist": "mixed",
        "accuracy_first": True,  # The MCP reads this format-1 field to describe branch coverage.
        "lore_schema_version": 1,
        "counts": {
            "line_keys": stats.line_keys,
            "name_keys": stats.name_keys,
            "selected_keys": stats.selected_keys,
            "total_lines": stats.total_lines,
            "speaker_lines": stats.speaker_lines,
            "supplement_lines": stats.supplement_lines,
            "lore": lore_stats,
            "extra_lines": extra_stats.lines,
            "extra_by_domain": extra_stats.by_domain,
        },
        "chapter_numbering": "第N季第M章 => Chapter{(N-1)*100 + M*10}",
        "ordering": {"mode": "catalog", "chronology_status": "unknown"},
        "quality": quality,
        "chapters": chapters_manifest,
        "validation": validation_manifest,
        "files": file_hashes,
        "attribution": attribution_summary(records),
        "reviewed_placeholder_lines": sum(record.get("content_status") == "reviewed_placeholder" for record in records),
        "source_variant_entries": len(source_variants),
        "supplement_context": {**comic_context["stats"], **comic_stats},
    }

    write_json(out_dir / "manifest.json", manifest)
    print(f"主线 {stats.total_lines:,} 条，活动及支线 {extra_stats.lines:,} 条，漫画及过场 {len(supplement):,} 条。")
    return stats


def _pending_record(
    parsed: ParsedKey,
    text: str,
    raw: str,
    variants: dict[str, str] | None,
    gender: str | None,
) -> dict:
    return {
        "_chapter": parsed.chapter_token,
        "_scene": parsed.scene,
        "_family": parsed.family,
        "_line_no": parsed.line_no or 0,
        "_sub_no": parsed.sub_no,
        "_variant": parsed.variant,
        "_gender": gender,
        "_source_key": parsed.key,
        "_text": text,
        "_raw": raw,
        "_variants": variants,
    }


def _normalize_speaker(speaker: str | None, gender: str) -> str | None:
    """Clean display names that come straight from Perform avatar keys."""
    if not speaker:
        return None
    if "{" in speaker:
        speaker = clean_text(speaker, gender).text
    speaker = speaker.strip()
    if speaker.isascii():
        speaker = _MANUAL_ALIASES.get(normalize_name(speaker), speaker)
    return speaker or None


def _mark_unattributed_scenes(records: list[dict]) -> None:
    """Use ``unknown`` instead of ``narration`` where speaker data is absent.

    A speaker-less line is only plausible narration when the scene has
    speaker data at all; scenes without any (Bubble/Ongoing families, some
    prologue tables) are simply not covered by the Perform scan.
    """
    attributed = {
        (record["chapter"], record["scene"], record["family"])
        for record in records
        if record["speaker"]
    }
    # These families are character barks / UI dialogue, never narration.
    non_narration = {
        "BubbleStory", "Bubble",
        "OngoingLevel", "OngoingMainCity", "Ongoing", "OngoingAntique",
        "ChatPlus",
    }
    for record in records:
        if record["line_type"] != "narration":
            continue
        if record["family"] in non_narration:
            record["line_type"] = "unknown"
        elif (record["chapter"], record["scene"], record["family"]) not in attributed:
            record["line_type"] = "unknown"


def costume_prefixes(text_map) -> frozenset[str]:
    """Derive protagonist costume prefixes from ``GalNPC<Form>Belle`` names.

    ``GalNPCStudentBelle => 学生铃`` yields ``学生``; the base ``GalNPCBelle``
    (``铃``) and combined names (``铃&伊芙琳``) are skipped.  Deriving the set
    keeps the branch folding working when a new version adds a costume form.
    """
    prefixes: set[str] = set()
    for key, value in text_map.items():
        if not key.startswith("GalNPC") or not key.endswith("Belle"):
            continue
        if not isinstance(value, str) or len(value) < 2 or value[-1] != "铃":
            continue
        prefix = value[:-1]
        if prefix:
            prefixes.add(prefix)
    return frozenset(prefixes) or DEFAULT_COSTUME_PREFIXES


def _protagonist_side(name: str | None, costumes: frozenset[str] = DEFAULT_COSTUME_PREFIXES) -> str | None:
    """``"M"`` for 哲 (incl. 学生哲/道士哲/…), ``"F"`` for 铃, else ``None``."""
    if not name:
        return None
    if name in {"哲", "铃"}:
        return "M" if name == "哲" else "F"
    if name[-1] in "铃哲" and name[:-1] in costumes:
        return "M" if name[-1] == "哲" else "F"
    return None


def _quality_metrics(records: list[dict], supplements: list[dict]) -> dict:
    """Report gaps explicitly so a consumer can choose appropriate evidence."""
    scenes: dict[tuple[str, str, str], dict] = {}
    for row in records:
        scenes.setdefault((row["chapter"], row["family"], row["scene"]), row)
    galgame = [row for row in scenes.values() if row["family"] == "GalGame"]
    by_chapter: dict[str, dict[str, int]] = {}
    for row in galgame:
        counts = by_chapter.setdefault(row["chapter"], {"galgame_scenes": 0, "quest_linked_scenes": 0})
        counts["galgame_scenes"] += 1
        counts["quest_linked_scenes"] += bool(row.get("quest_id"))
    return {
        "galgame_scenes": len(galgame),
        "archive_listed_scenes": sum(row.get("archive_order") is not None for row in galgame),
        "quest_linked_scenes": sum(bool(row.get("quest_id")) for row in galgame),
        "chronology_verified_scenes": 0,
        "unlinked_comic_lines": sum(row.get("context_status") == "unlinked" for row in supplements),
        "by_chapter": by_chapter,
    }


def _assign_line_ids(records: list[dict]) -> None:
    """Stable ids keyed by chapter token, not by chapter order.

    The order prefix used to be part of the id, so inserting a chapter (025,
    040, 050 …) renumbered every later line and invalidated downstream
    references.  The token never moves; ordering is carried by ``order``.
    """
    used: set[str] = set()
    by_source: dict[str, str] = {}
    for index, record in enumerate(records, 1):
        chapter = chapter_info(record["chapter"]).short or "X"
        base = f"CH{chapter}_{record['family']}_{record['scene']}_{record['line_no']:04d}"
        if record["sub_no"] is not None:
            base += f"_{record['sub_no']:02d}"
        if record["variant"]:
            base += record["variant"]
        key = record.get("source_key")
        if key in by_source:
            base = by_source[key] + ":F"
        line_id = base
        counter = 2
        while line_id in used:
            line_id = f"{base}_{counter}"
            counter += 1
        used.add(line_id)
        if key:
            by_source.setdefault(key, line_id)
        record["line_id"] = line_id
        record["order"] = index


def _assign_supplement_ids(records: list[dict]) -> None:
    seen = set()
    for index, record in enumerate(records, 1):
        key = record["source_key"]
        record["line_id"] = "SUP_" + key + (":F" if key in seen else "")
        seen.add(key)
        record["order"] = index
