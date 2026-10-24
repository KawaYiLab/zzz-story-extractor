"""Main extraction pipeline."""

from __future__ import annotations

import bisect
import csv
import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .chapters import (
    CHAPTER_ORDER_SCALE,
    chapter_info,
    parse_season_chapter,
    season_chapter_token,
)
from .clean import clean_text
from .content import coverage_report
from .extras import candidate_keys as extra_candidate_keys
from .extras import extract_extras, render_extra_txt
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
from .keys import LEGACY_GALGAME_RE, ParsedKey, natural_scene_key, parse_key
from .lore import extract_lore
from .narrative import (
    annotate_attribution,
    annotate_content,
    annotate_local_order,
    attribution_summary,
)
from .speakers import _MANUAL_ALIASES, SpeakerInfo, build_speaker_index, normalize_name
from .textmap import TextMap, load_text_map
from .validate import validate_records
from .writers import (
    write_chapter_files,
    write_json,
    write_jsonl,
    write_story_txt,
    write_supplement_txt,
    write_text,
)

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
_F_VARIANT_RE = re.compile(r"(?:Name_?\d+|\d+)F$")


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


def _load_scene_titles(data_paths: dict[str, Path], text_map: TextMap) -> dict[str, str]:
    titles: dict[str, str] = {}
    perform_path = data_paths.get("FileCfg/PerformTemplateTb.json")
    if perform_path and perform_path.exists():
        try:
            perf = read_json(perform_path)
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
                title = title.strip().strip("「」")
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
        cleaned = val.strip().strip("「」")
        if not cleaned:
            continue
        if key.startswith("Title_"):
            sc = key[6:]
            titles.setdefault(sc, cleaned)
        else:
            sc = key[len("Quest_VHSPerformName_"):]
            titles.setdefault(sc, cleaned)

    return titles



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
            name = text_map.get(str(row.get("ANCOBODLNIK", ""))).strip()
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


def _normalize_chapter_filter(tokens: set[str] | None) -> set[str] | None:
    """Accept ``230`` / ``Chapter230`` / ``210,220`` and return full tokens."""
    if not tokens:
        return None
    normalized = set()
    for token in tokens:
        token = (token or "").strip()
        if not token:
            continue
        normalized.add(token if token.startswith("Chapter") else f"Chapter{token}")
    return normalized or None


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
    lang: str = "CHS",
    data_dir: Path | None = None,
    game_dir: Path | None = None,
    refresh: bool = False,
    refresh_speakers: bool = False,
    no_speakers: bool = False,
    require_speakers: float | None = None,
    formats: str = "jsonl,txt",
    include_supplement: bool = True,
    dedupe: bool = True,
    limit: int | None = None,
    include_lore: bool = True,
    strict: bool = True,
    keep_raw: bool = False,
    only_chapters: set[str] | None = None,
    accuracy_first: bool = False,
    include_extra: bool = True,
) -> ExtractStats:
    formats_set = {part.strip().lower() for part in formats.split(",") if part.strip()}
    if not formats_set or formats_set - {"jsonl", "txt", "csv"}:
        raise ValueError("format 必须为 jsonl、txt、csv 的组合")
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("limit 必须为正整数")
    if require_speakers is not None and not 0 <= require_speakers <= 1:
        raise ValueError("require-speakers 必须在 0 到 1 之间")
    # Refuse reserved output paths before writing anything. Reusing a folder
    # can combine new manifests with stale JSONL, chapters or lore.
    reserved = ("story.jsonl", "story.txt", "story.csv", "supplement.jsonl", "supplement.txt",
                "chapters", "lore", "discarded.jsonl", "name_candidates.jsonl", "speaker-gaps.jsonl", "placeholder-records.jsonl", "coverage.json", "manifest.json",
                "extra.jsonl", "extra.txt", "extra-discarded.jsonl", "content-coverage.json")
    if any((out_dir / name).exists() for name in reserved):
        raise FileExistsError(f"输出目录已有提取产物：{out_dir}；请指定新的 --out 目录")
    out_dir.mkdir(parents=True, exist_ok=True)
    only = _normalize_chapter_filter(only_chapters)
    data_paths = ensure_data(lang=lang, refresh=refresh, data_dir=data_dir)
    print("Loading TextMap...")
    text_map = load_text_map(data_paths, language=lang)
    print(f"  {len(text_map)} entries loaded")
    if only:
        print(f"  chapter filter: {', '.join(sorted(only))}")
    costumes = costume_prefixes(text_map)
    print(f"  protagonist forms: {len(costumes)} ({', '.join(sorted(costumes))})")
    scene_titles = _load_scene_titles(data_paths, text_map)
    scene_order, quest_names = _load_archive_order(data_paths, text_map)
    if scene_order:
        print(f"  story archive: {len(scene_order)} ordered scenes, {len(quest_names)} quest names")

    game_dir = detect_game_dir(game_dir)
    if game_dir:
        print(f"Game directory: {game_dir}")
        game_version = read_game_version(game_dir)
        if game_version:
            print(f"  local version: {game_version}")
    else:
        print("warning: game directory not found; per-line speakers will be unavailable")

    stats = ExtractStats()
    names_by_scene: dict[tuple[str, str], list[str]] = {}
    names_global: dict[tuple[str, str], list[str]] = {}
    pending: list[dict] = []
    supplement: list[dict] = []
    early_discarded: list[dict] = []
    name_candidates: list[dict] = []
    # TextMap contains many repeated values (especially short pauses and
    # common acknowledgements).  Cleaning markup is pure for a given raw
    # value/protagonist, so reuse the result within this extraction run.
    clean_cache = {}

    def clean_cached(raw: str, gender: str = "M"):
        cache_key = (raw, gender)
        cleaned = clean_cache.get(cache_key)
        if cleaned is None:
            cleaned = clean_text(raw, gender)
            clean_cache[cache_key] = cleaned
        return cleaned

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
        if only is not None:
            # CS keys carry a season.chapter prefix, Comic keys carry none.
            scoped = cs_chapter(parsed.chapter_token)[0] if parsed.family == "CS" else parsed.chapter_token
            if parsed.family == "Comic" or scoped not in only:
                continue
        if parsed.chapter_token in EXCLUDED_CHAPTERS:
            continue
        if parsed.family == "MainChat" and not parsed.chapter_token.startswith("Chapter"):
            continue
        if parsed.family in MAIN_FAMILIES or parsed.family == "MainChat":
            if limit is not None and stats.line_keys >= limit:
                continue
            if accuracy_first and parsed.kind == "name":
                name_candidates.append({"source_key": key, "raw_text": text_map.get(key)})
        # Keys ending in F are the female-protagonist copies of the base key.
        # Check this while processing the candidate instead of making a
        # separate pass over all 400k TextMap entries.
        if (
            not accuracy_first
            and (parsed.family in MAIN_FAMILIES or parsed.family == "MainChat")
            and key.endswith("F")
            and _F_VARIANT_RE.search(key)
            and key[:-1] in text_map
        ):
            raw = text_map.get(key)
            early_discarded.append({
                "source_key": key, "chapter": parsed.chapter_token,
                "record_kind": parsed.kind,
                "scene": parsed.scene, "family": parsed.family,
                "line_no": parsed.line_no, "sub_no": parsed.sub_no,
                "variant": parsed.variant, "speaker": None,
                "text": clean_cached(raw, "F").text, "raw_text": raw,
                "reason": "explicit_gender_variant", "paired_source_key": key[:-1],
            })
            continue
        if parsed.family in MAIN_FAMILIES or parsed.family == "MainChat":
            if parsed.kind == "name":
                raw = text_map.get(key)
                gender = parsed.variant if accuracy_first and parsed.variant in {"M", "F"} else "M"
                cleaned = clean_cached(raw, gender).text
                if not cleaned:
                    continue
                stats.selected_keys += 1
                stats.name_keys += 1
                scoped = (f"{parsed.family}:{parsed.chapter_token}", parsed.scene)
                names_by_scene.setdefault(scoped, []).append(cleaned)
                names_global.setdefault((parsed.chapter_token, parsed.scene), []).append(cleaned)
                continue

            raw = text_map.get(key)
            if not raw:
                stats.missing_text += 1
                if len(stats.missing_examples) < 100:
                    stats.missing_examples.append(key)
                continue
            gender = parsed.variant if accuracy_first and parsed.variant in {"M", "F"} else "M"
            cleaned = clean_cached(raw, gender)
            if not cleaned.text:
                continue
            pending.append(_pending_record(parsed, cleaned.text, raw, cleaned.variants, parsed.variant))
            stats.selected_keys += 1
            stats.line_keys += 1
            if stats.line_keys % 10000 == 0:
                print(f"  parsed {stats.line_keys} line keys...")
            continue

        if include_supplement and parsed.family in {"Comic", "CS"}:
            raw = text_map.get(key)
            if not raw:
                continue
            cleaned = clean_cached(raw)
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
    if only is not None and stats.line_keys == 0:
        raise SystemExit(
            f"no story lines matched --only-chapter {', '.join(sorted(only))}; "
            "check the chapter token (e.g. 110, 230)"
        )

    text_keys = {record["_source_key"] for record in pending}
    # Extras share the speaker index; a chapter filter writes a partial corpus.
    include_extra = include_extra and only is None and limit is None
    if include_extra:
        text_keys.update(item.key for item in extra_candidate_keys(text_map) if item.kind == "line")
    if include_lore:
        text_keys.update(key for key in text_map.keys() if key.startswith(("PartnerTalk_", "Chat_PartnerTalk_")))
    cache_root = _cache_root(data_dir, lang)
    speaker_index, speaker_stats = build_speaker_index(
        text_map=text_map,
        text_keys=text_keys,
        data_paths=data_paths,
        game_dir=game_dir,
        cache_path=cache_root / "speakers_cache.json",
        refresh=refresh_speakers,
        no_speakers=no_speakers,
    )
    stats.speaker_stats = asdict(speaker_stats)
    alias_name_map = {} if accuracy_first else _infer_alias_names(pending, speaker_index, names_global)

    records: list[dict] = []
    for pending_record in pending:
        source_key = pending_record["_source_key"]
        chapter = pending_record["_chapter"]
        scene = pending_record["_scene"]
        family = pending_record["_family"]
        scene_names = _scene_names(names_by_scene, names_global, chapter, scene, family)
        info: SpeakerInfo | None = speaker_index.lookup(source_key)
        has_voice = bool(info and info.has_voice)
        speaker = info.speaker if info else None
        alias = info.alias if info else None
        confidence = info.confidence if info else 0.0
        speaker_source = info.source if info else "none"

        if not speaker and alias:
            inferred = alias_name_map.get(alias)
            if inferred:
                speaker = inferred
                confidence = 0.6
                speaker_source = "scene_alias"
                stats.scene_alias += 1

        if not speaker and not accuracy_first:
            candidates = [name for name in scene_names if name not in NAME_IGNORE and name not in PLAYER_NAMES]
            if len(candidates) == 1 and (has_voice or (info and info.source == "avatar")):
                speaker = candidates[0]
                confidence = 0.4
                speaker_source = "scene_name"
                stats.scene_fallback += 1

        speaker = _normalize_speaker(speaker, "M")
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
            elif alias and alias_name_map.get(alias) in {"选项", "玩家选项"}:
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
        raw_text = _record_raw_text(
            pending_record["_raw"],
            pending_record["_text"],
            keep_raw or accuracy_first,
        )
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

    # Keep references to every parsed story record. Filtering functions return
    # shorter lists, but the original objects remain available for the audit
    # sidecar so no dropped line disappears without a reason.
    all_story_records = list(records)

    _mark_unattributed_scenes(records)
    annotate_attribution(records)
    annotate_content(records)

    if not accuracy_first:
        records, dropped = _filter_perform_routes(records)
        stats.branch_filtered += dropped
        records, dropped = _filter_timeline_copies(records)
        stats.branch_filtered += dropped
        # Address filtering must see both branches before pair collapsing
        # keeps one of them by speaker alone.
        records, dropped = _filter_branch_lines(records, costumes)
        stats.branch_filtered += dropped
        unknown_forms = _unknown_costume_forms(records, costumes)
        if unknown_forms:
            detail = "、".join(f"{name}×{count}" for name, count in sorted(unknown_forms.items()))
            print(f"  warning: 未登记的主角形态 {detail}（GalNPC 表里没有，折叠可能漏掉）")
        records, dropped = _collapse_gender_pairs(records, "M", costumes)
        stats.gender_pair_filtered += dropped

    galgame_scenes: dict[str, list[str]] = {}
    for record in records:
        if record["family"] == "GalGame" and record["scene"] not in galgame_scenes.setdefault(record["chapter"], []):
            galgame_scenes[record["chapter"]].append(record["scene"])
    scene_positions: dict[tuple[str, str], float] = {}
    for chapter, scenes in galgame_scenes.items():
        for scene, position in _galgame_scene_positions(scenes, scene_order).items():
            scene_positions[(chapter, scene)] = position
    for record in records:
        position = scene_positions.get((record["chapter"], record["scene"]))
        archived_count = sum(scene in scene_order for scene in galgame_scenes.get(record["chapter"], []))
        if record["family"] == "GalGame" and record["archive_order"] is None and position is not None and position < archived_count:
            record["order_source"] = "archive_interpolation"
    annotate_local_order(records)
    records.sort(key=lambda record: _line_sort_key(record, scene_positions))
    for record in records:
        record.pop("_local_order", None)
    if dedupe and not accuracy_first:
        records, dropped = _dedupe_records(records, "M", costumes=costumes)
        stats.deduped += dropped

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
    all_supplement_records = list(supplement)
    if dedupe and not accuracy_first:
        kept_supp: list[dict] = []
        for rec in supplement:
            if kept_supp:
                prev = kept_supp[-1]
                if (
                    prev["family"] == rec["family"]
                    and prev["chapter"] == rec["chapter"]
                    and prev["scene"] == rec["scene"]
                    and prev["text"] == rec["text"]
                ):
                    _mark_discard(rec, "supplement_duplicate", prev)
                    continue
                if (
                    prev["family"] == rec["family"]
                    and prev["chapter"] == rec["chapter"]
                    and prev["scene"] == rec["scene"]
                ):
                    p_txt = prev["text"]
                    c_txt = rec["text"]
                    # Only collapse an otherwise identical address pair.
                    paired = p_txt.replace("哥哥", "妹妹") == c_txt.replace("哥哥", "妹妹")
                    if paired and "妹妹" in p_txt and "哥哥" in c_txt:
                        _mark_discard(rec, "supplement_gender_address", prev)
                        continue
                    if paired and "哥哥" in p_txt and "妹妹" in c_txt:
                        _mark_discard(prev, "supplement_gender_address", rec)
                        kept_supp[-1] = rec
                        continue
            kept_supp.append(rec)
        supplement = kept_supp

    _assign_supplement_ids(supplement)
    stats.supplement_lines = len(supplement)

    kept_objects = {id(record) for record in records + supplement}
    discarded = early_discarded + [
        _discarded_record(record)
        for record in all_story_records + all_supplement_records
        if id(record) not in kept_objects and record.get("_discard_reason")
    ]
    for record in records + supplement:
        for field_name in ("_discard_reason", "_paired_source_key", "_discard_similarity"):
            record.pop(field_name, None)
    quality = _quality_metrics(records, supplement)
    discarded_names = sum(row.get("record_kind") == "name" for row in discarded)

    issues = validate_records(records, supplement)
    errors = [issue for issue in issues if issue.level == "error"]
    warnings = [issue for issue in issues if issue.level == "warning"]
    if issues:
        print(f"  validation: {len(errors)} error(s), {len(warnings)} warning(s)")
        for issue in issues[:8]:
            print(f"    {issue}")

    if "jsonl" in formats_set:
        write_jsonl(records, out_dir / "story.jsonl")
        if supplement:
            write_jsonl(supplement, out_dir / "supplement.jsonl")
    if "txt" in formats_set:
        write_story_txt(records, out_dir / "story.txt")
        write_chapter_files(records, out_dir / "chapters")
        if supplement:
            write_supplement_txt(supplement, out_dir / "supplement.txt")
    if "csv" in formats_set:
        _write_csv(records, out_dir / "story.csv")

    # Every heuristic removal is retained in a reviewable sidecar. Accuracy
    # first mode produces an empty file, which is itself a useful assertion.
    write_jsonl(discarded, out_dir / "discarded.jsonl")
    write_jsonl((record for record in records if record.get("speaker_status") == "unresolved"), out_dir / "speaker-gaps.jsonl")
    write_jsonl((record for record in records if record.get("content_status") == "reviewed_placeholder"), out_dir / "placeholder-records.jsonl")
    if accuracy_first:
        write_jsonl(name_candidates, out_dir / "name_candidates.jsonl")

    extra_stats = None
    if include_extra:
        print("Extracting activity / side / agent stories...")
        extra_records, extra_discarded, extra_stats = extract_extras(
            text_map,
            speaker_index=speaker_index,
            accuracy_first=accuracy_first,
            dedupe=dedupe,
            scene_order=scene_order,
            quest_names=quest_names,
        )
        if "jsonl" in formats_set:
            write_jsonl(extra_records, out_dir / "extra.jsonl")
        if "txt" in formats_set:
            write_text(out_dir / "extra.txt", render_extra_txt(extra_records))
        write_jsonl(extra_discarded, out_dir / "extra-discarded.jsonl")
        detail = ", ".join(f"{name} {count}" for name, count in extra_stats.by_domain.items())
        print(f"  extra lines: {extra_stats.lines} in {len(extra_stats.groups)} groups ({detail})")
    content_coverage = coverage_report(text_map)
    write_json(out_dir / "content-coverage.json", content_coverage)
    unknown = content_coverage["unclassified"]
    if unknown:
        top = ", ".join(f"{row['family']}×{row['keys']}" for row in unknown[:5])
        print(f"  content registry: {len(unknown)} unclassified dialogue-like families (largest: {top})")

    lore_stats: dict[str, int] = {}
    if include_lore and only is not None:
        print("  lore skipped: --only-chapter writes a partial corpus")
    elif include_lore:
        print("Extracting worldbuilding lore...")
        avatar_path = data_paths.get("FileCfg/AvatarBaseTemplateTb.json")
        avatar_base = read_json(avatar_path) if avatar_path and avatar_path.exists() else None
        lore_stats = extract_lore(text_map, avatar_base, out_dir, speaker_index=speaker_index, accuracy_first=accuracy_first)
        print(
            f"  lore extracted: {lore_stats.get('lore_agents', 0)} agents, "
            f"{lore_stats.get('lore_discs', 0)} discs, "
            f"{lore_stats.get('lore_w_engines', 0)} engines, "
            f"{lore_stats.get('lore_quests', 0)} quests, "
            f"{lore_stats.get('lore_messages', 0)} messages"
        )

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
        "warnings": len(warnings),
        "issues": [asdict(issue) for issue in issues],
    }

    coverage = {
        "total_lines": stats.total_lines,
        "speaker_lines": stats.speaker_lines,
        "speaker_null": stats.speaker_null,
        "options_count": stats.options_count,
        "voice_linked": stats.voice_linked,
        "voice_speaker": stats.voice_speaker,
        "voice_speaker_coverage": round(stats.voice_speaker / stats.voice_linked, 4) if stats.voice_linked else None,
        "scene_fallback": stats.scene_fallback,
        "scene_alias": stats.scene_alias,
        "deduped": stats.deduped,
        "branch_filtered": stats.branch_filtered,
        "gender_pair_filtered": stats.gender_pair_filtered,
        "missing_text": stats.missing_text,
        "missing_examples": stats.missing_examples,
        "by_family": stats.by_family,
        "by_chapter": stats.by_chapter,
        "raw_text_omitted": stats.raw_text_omitted,
        "supplement_lines": stats.supplement_lines,
        "speaker_stats": stats.speaker_stats,
        "attribution": attribution_summary(records),
        "reviewed_placeholder_lines": sum(record.get("content_status") == "reviewed_placeholder" for record in records),
        "accuracy_first": accuracy_first,
        "ordering": {"mode": "catalog", "chronology_status": "unknown"},
        "quality": quality,
        "discarded_lines": len(discarded) - discarded_names,
        "discarded_names": discarded_names,
        "discarded_entries": len(discarded),
        "discarded_by_reason": _count_discard_reasons(discarded),
        "lore_stats": lore_stats,
        "extra": asdict(extra_stats) if extra_stats else None,
        "chapters": chapters_manifest,
        "validation": validation_manifest,
    }
    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "language": lang,
        "source_version": source_version,
        "chapter_order_scale": CHAPTER_ORDER_SCALE,
        "local_game_version": read_game_version(game_dir) if game_dir else "",
        # Basename only: the manifest travels inside the upload bundle, so the
        # user's absolute game path must not leak into it.
        "game_dir": game_dir.name if game_dir else "",
        "protagonist": "mixed" if accuracy_first else "M",
        "counts": {
            "line_keys": stats.line_keys,
            "name_keys": stats.name_keys,
            "selected_keys": stats.selected_keys,
            "total_lines": stats.total_lines,
            "speaker_lines": stats.speaker_lines,
            "supplement_lines": stats.supplement_lines,
            "branch_filtered": stats.branch_filtered,
            "gender_pair_filtered": stats.gender_pair_filtered,
            "raw_text_omitted": stats.raw_text_omitted,
            "discarded_lines": len(discarded) - discarded_names,
            "discarded_names": discarded_names,
            "discarded_entries": len(discarded),
            "lore": lore_stats,
            "extra_lines": extra_stats.lines if extra_stats else 0,
            "extra_by_domain": extra_stats.by_domain if extra_stats else {},
        },
        "chapter_numbering": "第N季第M章 => Chapter{(N-1)*100 + M*10}",
        "chapter_filter": sorted(only) if only else [],
        "limit": limit,
        "include_supplement": include_supplement,
        "accuracy_first": accuracy_first,
        "ordering": {"mode": "catalog", "chronology_status": "unknown"},
        "quality": quality,
        "chapters": chapters_manifest,
        "validation": validation_manifest,
        "files": file_hashes,
        "attribution": attribution_summary(records),
        "reviewed_placeholder_lines": sum(record.get("content_status") == "reviewed_placeholder" for record in records),
    }

    write_json(out_dir / "coverage.json", coverage)
    write_json(out_dir / "manifest.json", manifest)

    print("")
    print("Done.")
    print(f"  lines: {stats.total_lines} (speaker: {stats.speaker_lines}, null: {stats.speaker_null})")
    print(f"  voice-linked: {stats.voice_linked}, voice speaker: {stats.voice_speaker}")
    if stats.voice_linked:
        print(f"  voice speaker coverage: {stats.voice_speaker / stats.voice_linked:.1%}")
    print(f"  supplement lines: {stats.supplement_lines}, deduped: {stats.deduped}")
    print(f"  output: {out_dir}")

    if require_speakers is not None:
        coverage_value = (stats.voice_speaker / stats.voice_linked) if stats.voice_linked else 0.0
        if coverage_value < require_speakers:
            raise SystemExit(
                f"speaker coverage {coverage_value:.1%} is below required {require_speakers:.1%}"
            )

    if errors and strict:
        raise SystemExit(
            f"validation failed with {len(errors)} error(s); "
            "see coverage.json for details, or rerun with --allow-issues to keep the output"
        )

    return stats


def _infer_alias_names(
    pending: list[dict],
    speaker_index,
    names_global: dict[tuple[str, str], list[str]],
) -> dict[str, str]:
    """Infer Chinese names for NPC aliases from scene cast lists.

    Agents are already resolved through AvatarBaseTemplateTb.  NPC aliases
    (Susie, Deline, ...) are not in that table, so use the scene's _Name keys:
    known agents/player names are removed, then one-to-one scenes are mapped.
    """
    scene_aliases: dict[tuple[str, str], list[str]] = {}
    mapping: dict[str, str] = {}
    for record in pending:
        info = speaker_index.lookup(record["_source_key"])
        if not info or not info.alias:
            continue
        scene_aliases.setdefault((record["_chapter"], record["_scene"]), []).append(info.alias)
        if info.speaker:
            mapping[info.alias] = info.speaker

    for scene_key, aliases in scene_aliases.items():
        remaining_aliases: list[str] = []
        for alias in aliases:
            if alias not in mapping and alias not in remaining_aliases:
                remaining_aliases.append(alias)
        if not remaining_aliases:
            continue
        known_names = set(mapping.values())
        remaining_names: list[str] = []
        for name in names_global.get(scene_key, []):
            if name in known_names or name in PLAYER_NAMES or name in NAME_IGNORE:
                continue
            if name not in remaining_names:
                remaining_names.append(name)
        if len(remaining_aliases) == 1 and len(remaining_names) == 1:
            mapping[remaining_aliases[0]] = remaining_names[0]
        elif 1 < len(remaining_aliases) == len(remaining_names) <= 4:
            for alias, name in zip(remaining_aliases, remaining_names):
                mapping.setdefault(alias, name)
    return mapping


def _pending_record(
    parsed: ParsedKey,
    text: str,
    raw: str,
    variants: dict[str, str] | None = None,
    variant: str | None = None,
) -> dict:
    return {
        "_chapter": parsed.chapter_token,
        "_scene": parsed.scene,
        "_family": parsed.family,
        "_line_no": parsed.line_no or 0,
        "_sub_no": parsed.sub_no,
        "_variant": variant if variant is not None else parsed.variant,
        "_source_key": parsed.key,
        "_text": text,
        "_raw": raw,
        "_variants": variants,
    }


def _filter_timeline_copies(records: list[dict]) -> tuple[list[dict], int]:
    """Filter only copies/routes verified by the ChatPlus timeline objects."""
    by_key = {record["source_key"]: record for record in records}
    male_by_scene: dict[tuple[str, str, str], list[dict]] = {}
    for record in records:
        link = record.get("timeline") or {}
        if "M" in link.get("sides", []) and not link.get("copy_of"):
            male_by_scene.setdefault((record["chapter"], record["scene"], record["family"]), []).append(record)
    drop: set[int] = set()
    for record in records:
        link = record.get("timeline") or {}
        copied = by_key.get(link.get("copy_of"))
        if copied:
            _mark_discard(record, "timeline_unused_copy", copied)
            drop.add(id(record))
            continue
        if link.get("sides") != ["F"]:
            continue
        candidates = male_by_scene.get((record["chapter"], record["scene"], record["family"]), [])
        if not candidates:
            continue
        paired = min(candidates, key=lambda other: abs(other["line_no"] - record["line_no"]))
        _mark_discard(record, "timeline_gender_route", paired)
        drop.add(id(record))
    return [record for record in records if id(record) not in drop], len(drop)


def _filter_perform_routes(records: list[dict]) -> tuple[list[dict], int]:
    """Remove only explicit, rejoining gender alternatives with a kept peer."""
    by_key = {record["source_key"]: record for record in records}
    drop = set()
    for record in records:
        link = record.get("perform") or {}
        copied = by_key.get(link.get("copy_of"))
        if copied and (record.get("raw_text") or record["text"]) == (copied.get("raw_text") or copied["text"]):
            _mark_discard(record, "perform_unused_copy", copied)
            drop.add(id(record))
            continue
        if not link.get("explicit_gender") or link.get("sides") != ["F"]:
            continue
        paired = by_key.get(link.get("paired_key"))
        peer = paired.get("perform") or {} if paired else {}
        if not paired or not peer.get("explicit_gender") or peer.get("sides") != ["M"] or peer.get("paired_key") != record["source_key"]:
            continue
        if (record["chapter"], record["scene"], record["family"]) != (paired["chapter"], paired["scene"], paired["family"]):
            continue
        _mark_discard(record, "perform_gender_route", paired)
        drop.add(id(record))
    return [record for record in records if id(record) not in drop], len(drop)


def _verified_male_route(record: dict) -> bool:
    perform = record.get("perform") or {}
    timeline = record.get("timeline") or {}
    return (perform.get("explicit_gender") and perform.get("sides") == ["M"]) or (
        "M" in timeline.get("sides", []) and not timeline.get("copy_of"))


def _collapse_gender_pairs(
    records: list[dict],
    protagonist: str,
    costumes: frozenset[str] = DEFAULT_COSTUME_PREFIXES,
) -> tuple[list[dict], int]:
    """Drop the opposite protagonist's near-duplicate player line.

    Some scenes encode the two protagonists as adjacent line numbers instead
    of a ``...F`` suffix.  Only same-scene, close, high-similarity pairs whose
    speakers sit on opposite sides (哲 / 铃, including costume forms such as
    学生哲 / 道士铃) are collapsed; unrelated dialogue is left untouched, so
    the sister's genuinely different NPC lines survive.
    """
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    sides: dict[int, str] = {}
    for record in records:
        side = _protagonist_side(record.get("speaker"), costumes)
        if side is None:
            continue
        sides[id(record)] = side
        key = (record["chapter"], record["scene"], record["family"])
        grouped.setdefault(key, []).append(record)

    drop: set[int] = set()
    for group in grouped.values():
        group.sort(key=lambda item: (item["line_no"], item["sub_no"] or 0))
        for index, first in enumerate(group):
            if id(first) in drop:
                continue
            for second in group[index + 1:]:
                if second["line_no"] - first["line_no"] > 5:
                    break
                first_side = sides[id(first)]
                second_side = sides[id(second)]
                if first_side == second_side or id(second) in drop:
                    continue
                # Similarity cannot distinguish negation or other changed
                # meaning. Only identical player wording is evidence here.
                if first["text"] != second["text"]:
                    continue
                removed, retained = (first, second) if first_side != protagonist else (second, first)
                if _verified_male_route(removed):
                    continue
                _mark_discard(removed, "gender_speaker_pair", retained, 1.0)
                drop.add(id(removed))
                break

    if not drop:
        return records, 0
    return [record for record in records if id(record) not in drop], len(drop)


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


# Only explicit address substitutions with unchanged wording are branch evidence.
_ADDRESS_PAIRS = (("小师妹", "小师弟"), ("师妹", "师弟"), ("铃小姐", "哲先生"),
                  ("小铃", "哲小哥"), ("铃姐", "哲哥"), ("铃", "哲"))


def _filter_branch_lines(records: list[dict], costumes: frozenset[str] = DEFAULT_COSTUME_PREFIXES) -> tuple[list[dict], int]:
    """Keep uncertain pairs; remove only equivalent explicit branch addresses.

    Similarity alone loses changed meaning, and an address alone does not
    establish who is speaking. Known matching speakers are required, except
    for an exact sibling-address pair backed by a known protagonist speaker.
    """
    groups: dict[tuple, list[dict]] = {}
    for row in records:
        groups.setdefault((row["chapter"], row["scene"], row["family"]), []).append(row)
    dropped: set[int] = set()
    for group in groups.values():
        by_text: dict[str, list[dict]] = {}
        for row in group:
            by_text.setdefault(row["text"], []).append(row)
        for row in group:
            speaker = row.get("speaker")
            if _verified_male_route(row):
                continue
            if _protagonist_side(speaker, costumes) == "M":
                continue
            text = row["text"]
            candidates = []
            for female, male in _ADDRESS_PAIRS:
                # Bare names must be separate vocatives, not part of 门铃 etc.
                if female == "铃" and not re.search(r"(?:^|[，、！？。…\s])铃(?=$|[，、！？。…\s])", text):
                    continue
                if female in text:
                    candidates.extend(by_text.get(text.replace(female, male), []))
            if "哥哥" in text:
                candidates.extend(by_text.get(text.replace("哥哥", "铃"), []))
            for twin in candidates:
                if id(twin) in dropped or twin is row:
                    continue
                other_speaker = twin.get("speaker")
                same_speaker = bool(speaker) and speaker == other_speaker
                sibling = "哥哥" in text and _protagonist_side(other_speaker, costumes) == "M" and (
                    speaker is None or _protagonist_side(speaker, costumes) == "F")
                if not (same_speaker or sibling):
                    continue
                _mark_discard(row, "gender_address", twin, 1.0)
                dropped.add(id(row))
                break
    return [row for row in records if id(row) not in dropped], len(dropped)


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


def _unknown_costume_forms(records: list[dict], costumes: frozenset[str]) -> dict[str, int]:
    """哲/铃 names that look like an unregistered costume pair.

    Only pairs count: an unknown form that exists for both protagonists is a
    costume the table is missing, while a lone ``门铃`` is just a prop.
    """
    seen: dict[str, int] = {}
    for record in records:
        speaker = record.get("speaker")
        if speaker and len(speaker) <= 6 and speaker[-1] in "铃哲":
            seen[speaker] = seen.get(speaker, 0) + 1

    unknown: dict[str, int] = {}
    for name, count in seen.items():
        prefix = name[:-1]
        if name in {"哲", "铃"} or not prefix or prefix in costumes:
            continue
        twin = prefix + ("铃" if name[-1] == "哲" else "哲")
        if twin in seen:
            unknown[name] = count
    return unknown


def _protagonist_side(name: str | None, costumes: frozenset[str] = DEFAULT_COSTUME_PREFIXES) -> str | None:
    """``"M"`` for 哲 (incl. 学生哲/道士哲/…), ``"F"`` for 铃, else ``None``."""
    if not name:
        return None
    if name in {"哲", "铃"}:
        return "M" if name == "哲" else "F"
    if name[-1] in "铃哲" and name[:-1] in costumes:
        return "M" if name[-1] == "哲" else "F"
    return None


def _dedupe_records(
    records: list[dict],
    protagonist: str | None,
    *,
    canonical: bool = True,
    costumes: frozenset[str] = DEFAULT_COSTUME_PREFIXES,
) -> tuple[list[dict], int]:
    """Collapse identical nearby lines spoken by opposite known protagonists.

    Unattributed lines and NPC repetitions are ambiguous and remain intact.
    With canonical=False, only adjacent same-speaker repeats are removed.
    """
    own = "铃" if protagonist == "F" else ("哲" if protagonist == "M" else None)

    def preference(record: dict) -> int:
        speaker = record["speaker"]
        if own and _protagonist_side(speaker, costumes) == protagonist:
            return 2
        return 1 if speaker else 0

    groups: dict[tuple, list[dict]] = {}
    order: list[tuple] = []
    for record in records:
        key = (record["chapter"], record["scene"], record["family"], record["variant"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(record)

    drop: set[int] = set()
    for key in order:
        group = groups[key]
        first: dict[str, int] = {}
        for i, record in enumerate(group):
            text = record["text"]
            j = first.get(text)
            if j is None:
                first[text] = i
                continue
            prev = group[j]
            a, b = prev["speaker"], record["speaker"]
            gap = i - j
            if canonical:
                duplicate = (
                    _protagonist_side(a, costumes) is not None
                    and _protagonist_side(b, costumes) is not None
                    and _protagonist_side(a, costumes) != _protagonist_side(b, costumes)
                    and gap <= 5
                )
            else:
                duplicate = gap == 1 and a == b
            if not duplicate:
                continue
            removed = prev if preference(record) > preference(prev) else record
            if _verified_male_route(removed):
                continue
            if preference(record) > preference(prev):
                _mark_discard(prev, "duplicate_branch", record)
                drop.add(id(prev))
                first[text] = i
            else:
                _mark_discard(record, "duplicate_branch", prev)
                drop.add(id(record))

    if not drop:
        return records, 0
    return [record for record in records if id(record) not in drop], len(drop)


def _record_raw_text(raw: str, text: str, keep_raw: bool) -> str | None:
    """Keep the pre-clean TextMap value only when cleaning actually changed it.

    95% of lines clean to themselves, so writing both fields doubles
    story.jsonl for no information gain; ``--keep-raw`` restores the old
    behaviour when full fidelity matters.
    """
    if keep_raw or raw != text:
        return raw
    return None


def _mark_discard(record: dict, reason: str, paired: dict, similarity: float | None = None) -> None:
    record["_discard_reason"] = reason
    record["_paired_source_key"] = paired.get("source_key")
    if similarity is not None:
        record["_discard_similarity"] = round(similarity, 4)


def _discarded_record(record: dict) -> dict:
    """Return the reviewable subset of a line removed by a heuristic."""
    return {
        "source_key": record.get("source_key"),
        "record_kind": "line",
        "chapter": record.get("chapter"),
        "scene": record.get("scene"),
        "family": record.get("family"),
        "line_no": record.get("line_no"),
        "sub_no": record.get("sub_no"),
        "variant": record.get("variant"),
        "speaker": record.get("speaker"),
        "speaker_alias": record.get("speaker_alias"),
        "text": record.get("text"),
        "raw_text": record.get("raw_text") or record.get("text"),
        "reason": record.get("_discard_reason"),
        "paired_source_key": record.get("_paired_source_key"),
        "similarity": record.get("_discard_similarity"),
        **({"timeline": record["timeline"]} if record.get("timeline") else {}),
        **({"perform": record["perform"]} if record.get("perform") else {}),
    }


def _count_discard_reasons(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        reason = record.get("reason") or "unknown"
        counts[reason] = counts.get(reason, 0) + 1
    return counts


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
    for index, record in enumerate(records, 1):
        chapter = chapter_info(record["chapter"]).short or "X"
        base = f"CH{chapter}_{record['family']}_{record['scene']}_{record['line_no']:04d}"
        if record["sub_no"] is not None:
            base += f"_{record['sub_no']:02d}"
        if record["variant"]:
            base += record["variant"]
        line_id = base
        counter = 2
        while line_id in used:
            line_id = f"{base}_{counter}"
            counter += 1
        used.add(line_id)
        record["line_id"] = line_id
        record["order"] = index


def _assign_supplement_ids(records: list[dict]) -> None:
    for index, record in enumerate(records, 1):
        record["line_id"] = "SUP_" + record["source_key"]
        record["order"] = index


def _write_csv(records: list[dict], path: Path) -> None:
    fields = [
        "line_id",
        "chapter",
        "chapter_label",
        "chapter_order",
        "scene",
        "scene_act",
        "scene_title",
        "quest_name",
        "family",
        "line_no",
        "sub_no",
        "variant",
        "speaker",
        "speaker_id",
        "speaker_form",
        "speaker_alias",
        "speaker_confidence",
        "speaker_source",
        "source_attribution",
        "content_status",
        "content_evidence",
        "speaker_status",
        "speaker_gap_reason",
        "speaker_slot",
        "has_voice",
        "text",
        "raw_text",
        "text_variants",
        "timeline",
        "perform",
        "source_key",
        "line_type",
        "scene_speakers",
        "order",
        "order_source",
        "line_order_source",
        "line_order_status",
        "chronology_status",
        "archive_order",
        "quest_id",
        "quest_source",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = dict(record)
            row["scene_title"] = row.get("scene_title") or ""
            row["quest_name"] = row.get("quest_name") or ""
            row["text_variants"] = json.dumps(row["text_variants"], ensure_ascii=False) if row["text_variants"] else ""
            row["timeline"] = json.dumps(row["timeline"], ensure_ascii=False) if row.get("timeline") else ""
            row["perform"] = json.dumps(row["perform"], ensure_ascii=False) if row.get("perform") else ""
            for field in ("source_attribution", "content_evidence"):
                row[field] = json.dumps(row[field], ensure_ascii=False) if row.get(field) else ""
            row["scene_speakers"] = "、".join(row["scene_speakers"])
            writer.writerow(row)
