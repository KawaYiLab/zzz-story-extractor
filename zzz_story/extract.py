"""Main extraction pipeline."""

from __future__ import annotations

import bisect
import csv
import difflib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .chapters import (
    chapter_info,
    parse_season_chapter,
    season_chapter_token,
    sort_key as chapter_sort_key,
)
from .clean import clean_text
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
from .keys import ParsedKey, natural_scene_key, parse_key
from .lore import extract_lore
from .speakers import _MANUAL_ALIASES, SpeakerInfo, build_speaker_index, normalize_name
from .textmap import TextMap, load_text_map
from .validate import validate_records
from .writers import (
    write_chapter_files,
    write_json,
    write_jsonl,
    write_story_txt,
    write_supplement_txt,
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

NAME_IGNORE = {"选项", "玩家选项", "旁白", "咨询", "购买", "找零"}
OPTION_SPEAKERS = {"选项", "玩家选项"}
PLAYER_NAMES = {"铃", "哲"}
# Explicit male forms of address; lines using them are male-branch content.
MALE_ADDRESS = ("小师弟", "师弟", "哲小哥", "哲先生", "哲哥")
# Test/dev or side-content tables that are not part of the shipped main story.
EXCLUDED_CHAPTERS = {"Chapter020", "Chapter080", "PortChapter110"}


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
    speaker_stats: dict = field(default_factory=dict)


# Comic/CS resources carry no chapter token of their own, so a CS key's prefix
# is its only chapter hint: CS_21_01_010 means season 2, chapter 1.  Season 1
# tokens are irregular (01.5 / 028 / 05.2 ...) and stay explicit; season 2+ is
# derived through chapters.season_chapter_token so that renumbering the main
# story can never silently move old content under a new season again.
CS_SPECIAL_CHAPTERS: dict[str, tuple[str, str, float]] = {
    "00": ("Chapter00", "序章", 1.0),
    "01": ("Chapter01", "第一季 第一章", 2.0),
    "01.5": ("Chapter015", "第一季 第一章间章", 2.5),
    "02": ("Chapter02", "第一季 第二章", 3.0),
    "02.5": ("Chapter025", "第一季 第二章间章", 4.0),
    "028": ("Chapter028", "第一季 第二章", 4.5),
    "03": ("Chapter03", "第一季 第三章", 5.0),
    "03.5": ("Chapter035", "第一季 第三章间章", 5.5),
    "04": ("Chapter04", "第一季 第四章", 6.0),
    "04.5": ("Chapter045", "第一季 第四章间章", 6.5),
    "05": ("Chapter05", "第一季 第五章", 9.0),
    "05.2": ("Chapter052", "第一季 第五章", 9.2),
    "05.5": ("Chapter055", "第一季 第五章间章", 9.5),
    "05.8": ("Chapter058", "第一季 第五章", 9.8),
    "Burnice": ("Story_Burnice", "角色过场 · 柏妮思", 100.0),
    "Lighter": ("Story_Lighter", "角色过场 · 莱特", 101.0),
    "Lycaon": ("Story_Lycaon", "角色过场 · 莱卡恩", 102.0),
    "Nekomiya": ("Story_Nekomiya", "角色过场 · 猫又", 103.0),
    "QingYi": ("Story_QingYi", "角色过场 · 青衣", 104.0),
    "Rina": ("Story_Rina", "角色过场 · 丽娜", 105.0),
}


def cs_chapter(token: str) -> tuple[str, str, float]:
    """Resolve a CS prefix into ``(chapter_token, chapter_label, chapter_order)``."""
    special = CS_SPECIAL_CHAPTERS.get(token)
    if special:
        return special
    parsed = parse_season_chapter(token)
    if parsed and parsed[0] >= 2:
        chapter_token = f"Chapter{season_chapter_token(*parsed)}"
        info = chapter_info(chapter_token)
        return chapter_token, info.label, info.order
    return f"CS_{token}", f"过场动画（{token}）", 900.0


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
        if not val or not isinstance(val, str):
            continue
        cleaned = val.strip().strip("「」")
        if not cleaned:
            continue
        if key.startswith("Title_"):
            sc = key[6:]
            titles.setdefault(sc, cleaned)
        elif key.startswith("Quest_VHSPerformName_"):
            sc = key[len("Quest_VHSPerformName_"):]
            titles.setdefault(sc, cleaned)

    return titles



def _load_archive_order(data_paths: dict[str, Path], text_map: TextMap) -> tuple[dict[str, tuple[int, int]], dict[int, str]]:
    """Official story-replay order of GalGame scenes, plus quest names.

    ArchivePerformTemplateTb lists replayable scenes in story order; its id
    divided by 100 is the quest id from QuestConfigTemplateTb.
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
                scene_order[str(scene)] = (index, archive_id // 100)
    return scene_order, quest_names


def _galgame_scene_positions(scenes: list[str], scene_order: dict[str, tuple[int, int]]) -> dict[str, float]:
    """Position scenes by the official replay archive order.

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
        record["line_no"],
        record["sub_no"] or 0,
        record["variant"] or "",
        record["source_key"],
    )


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
) -> ExtractStats:
    out_dir.mkdir(parents=True, exist_ok=True)
    data_paths = ensure_data(lang=lang, refresh=refresh, data_dir=data_dir)
    print("Loading TextMap...")
    text_map = load_text_map(data_paths, language=lang)
    print(f"  {len(text_map)} entries loaded")
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
    selected_keys: list[str] = []

    # Keys ending in F are the female-protagonist copies of the base key.
    # Male-only extraction drops them and keeps the base (male) version.
    f_variant_keys: set[str] = set()
    for key in text_map.keys():
        if key.endswith("F") and re.search(r"(?:Name_?\d+|\d+)F$", key):
            if key[:-1] in text_map:
                f_variant_keys.add(key)

    for key in text_map.keys():
        if not (
            key.startswith("Main_")
            or key.startswith("MainChat_")
            or key.startswith("Comic_")
            or key.startswith("CS_")
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
        if key in f_variant_keys:
            continue
        if parsed.family in MAIN_FAMILIES or parsed.family == "MainChat":
            if limit is not None and stats.line_keys >= limit:
                continue
            if parsed.kind == "name":
                raw = text_map.get(key)
                cleaned = clean_text(raw, "M").text
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
            cleaned = clean_text(raw, "M")
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
            cleaned = clean_text(raw, "M")
            if not cleaned.text:
                continue
            if parsed.family == "CS":
                ch_token, ch_label, ch_order = cs_chapter(parsed.chapter_token)
            else:
                ch_token = "Comic"
                ch_label = "动态漫画"
                ch_order = 999
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
                }
            )
            stats.supplement_lines += 1

    print(f"  line keys: {stats.line_keys}, name keys: {stats.name_keys}, missing text: {stats.missing_text}")

    text_keys = {record["_source_key"] for record in pending}
    cache_root = PROJECT_ROOT / "data" / "cache" / DEFAULT_VERSION
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
    alias_name_map = _infer_alias_names(pending, speaker_index, names_global)

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

        if not speaker:
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
            "text": pending_record["_text"],
            "raw_text": pending_record["_raw"],
            "text_variants": pending_record["_variants"],
            "source_key": source_key,
            "line_type": line_type,
            "scene_speakers": display_speakers,
            "order": 0,
        }
        records.append(record)

    _mark_unattributed_scenes(records)

    # Address filtering must see both branches before pair collapsing
    # keeps one of them by speaker alone.
    records, dropped = _filter_branch_lines(records)
    stats.branch_filtered += dropped
    records, dropped = _collapse_gender_pairs(records, "M")
    stats.gender_pair_filtered += dropped

    galgame_scenes: dict[str, list[str]] = {}
    for record in records:
        if record["family"] == "GalGame" and record["scene"] not in galgame_scenes.setdefault(record["chapter"], []):
            galgame_scenes[record["chapter"]].append(record["scene"])
    scene_positions: dict[tuple[str, str], float] = {}
    for chapter, scenes in galgame_scenes.items():
        for scene, position in _galgame_scene_positions(scenes, scene_order).items():
            scene_positions[(chapter, scene)] = position
    records.sort(key=lambda record: _line_sort_key(record, scene_positions))
    if dedupe:
        records, dropped = _dedupe_records(records, "M")
        stats.deduped += dropped

    scene_acts_by_chapter: dict[str, dict[str, int]] = {}
    for record in records:
        chapter = record["chapter"]
        scene = record["scene"]
        acts = scene_acts_by_chapter.setdefault(chapter, {})
        if scene not in acts:
            acts[scene] = len(acts) + 1
        record["scene_act"] = acts[scene]
        title = (
            scene_titles.get(scene)
            or scene_titles.get(scene.lstrip("0"))
            or scene_titles.get(scene.zfill(4))
        )
        record["scene_title"] = title

    _assign_line_ids(records)
    stats.total_lines = len(records)
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
            item.get("chapter_order", 999),
            item["chapter"],
            natural_scene_key(item["scene"]),
            item["line_no"],
            item["source_key"],
        )
    )
    if dedupe:
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
                    continue
                if (
                    prev["family"] == rec["family"]
                    and prev["chapter"] == rec["chapter"]
                    and prev["scene"] == rec["scene"]
                ):
                    p_txt = prev["text"]
                    c_txt = rec["text"]
                    # Male-only: keep the version addressing Belle (妹妹).
                    if "妹妹" in p_txt and "哥哥" in c_txt:
                        continue
                    if "哥哥" in p_txt and "妹妹" in c_txt:
                        kept_supp[-1] = rec
                        continue
            kept_supp.append(rec)
        supplement = kept_supp

    _assign_supplement_ids(supplement)
    stats.supplement_lines = len(supplement)

    issues = validate_records(records, supplement)
    errors = [issue for issue in issues if issue.level == "error"]
    warnings = [issue for issue in issues if issue.level == "warning"]
    if issues:
        print(f"  validation: {len(errors)} error(s), {len(warnings)} warning(s)")
        for issue in issues[:8]:
            print(f"    {issue}")

    formats_set = {part.strip().lower() for part in formats.split(",") if part.strip()}
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

    lore_stats: dict[str, int] = {}
    if include_lore:
        print("Extracting worldbuilding lore...")
        avatar_path = data_paths.get("FileCfg/AvatarBaseTemplateTb.json")
        avatar_base = read_json(avatar_path) if avatar_path and avatar_path.exists() else None
        lore_stats = extract_lore(text_map, avatar_base, out_dir)
        print(
            f"  lore extracted: {lore_stats.get('lore_agents', 0)} agents, "
            f"{lore_stats.get('lore_discs', 0)} discs, "
            f"{lore_stats.get('lore_w_engines', 0)} engines, "
            f"{lore_stats.get('lore_quests', 0)} quests, "
            f"{lore_stats.get('lore_messages', 0)} messages"
        )

    source_version = fetch_source_version()
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
        "supplement_lines": stats.supplement_lines,
        "speaker_stats": stats.speaker_stats,
        "lore_stats": lore_stats,
        "chapters": chapters_manifest,
        "validation": validation_manifest,
    }
    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "language": lang,
        "source_version": source_version,
        "local_game_version": read_game_version(game_dir) if game_dir else "",
        "game_dir": str(game_dir) if game_dir else "",
        "protagonist": "M",
        "counts": {
            "line_keys": stats.line_keys,
            "name_keys": stats.name_keys,
            "selected_keys": stats.selected_keys,
            "total_lines": stats.total_lines,
            "speaker_lines": stats.speaker_lines,
            "supplement_lines": stats.supplement_lines,
            "branch_filtered": stats.branch_filtered,
            "gender_pair_filtered": stats.gender_pair_filtered,
            "lore": lore_stats,
        },
        "chapter_numbering": "第N季第M章 => Chapter{(N-1)*100 + M*10}",
        "chapters": chapters_manifest,
        "validation": validation_manifest,
        "files": file_hashes,
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


def _collapse_gender_pairs(records: list[dict], protagonist: str) -> tuple[list[dict], int]:
    """Drop the opposite protagonist's near-duplicate player line.

    Some scenes encode the two protagonists as adjacent line numbers instead
    of a ``...F`` suffix.  Only same-scene, close, high-similarity pairs with
    speakers 铃/哲 are collapsed; unrelated dialogue is left untouched.
    """
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for record in records:
        if record.get("speaker") not in {"铃", "哲"}:
            continue
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
                if {first["speaker"], second["speaker"]} != {"铃", "哲"}:
                    continue
                ratio = difflib.SequenceMatcher(None, first["text"], second["text"]).ratio()
                if ratio < 0.82:
                    continue
                if protagonist == "F":
                    drop_id = id(first if first["speaker"] == "哲" else second)
                else:
                    drop_id = id(first if first["speaker"] == "铃" else second)
                drop.add(drop_id)
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


# Belle-side markers: lines addressing Belle (师妹, 哥哥, ...) belong to the
# female-protagonist branch of a sibling pair.
_BELLE_MARKERS = ("小师妹", "师妹", "小铃", "铃小姐", "铃姐", "哥哥")

# Gendered tokens blanked out when comparing two lines, so the male and
# female branch of the same beat normalize to the same text.
_GENDER_TOKENS = (
    ("小师妹", "小师弟"),
    ("师妹", "师弟"),
    ("铃小姐", "哲先生"),
    ("小铃", "哲小哥"),
    ("铃姐", "哲哥"),
    ("哥哥", "哥哥"),
    ("铃", "哲"),
    ("她", "他"),
)


def _normalize_gender(text: str) -> str:
    for female, male in _GENDER_TOKENS:
        text = text.replace(female, "#").replace(male, "#")
    return text


def _filter_branch_lines(records: list[dict]) -> tuple[list[dict], int]:
    """Drop the female branch of sibling-paired lines (male-only extraction).

    Many beats are written twice, once per protagonist.  Two lines form a
    pair when they sit in the same scene and match after gendered tokens
    (师妹/师弟, 铃/哲, 哥哥, ...) are blanked out.  Within a pair the
    Belle-side line is dropped: first lines with Belle markers, then bare-铃
    vocatives whose twin addresses 哲.  Lines spoken by 哲 himself and lines
    with male markers (师弟, 哲先生, ...) are always kept, and so is every
    line without a twin, which preserves Belle's dialogue as the NPC sister
    and NPC lines about other people (潘师弟, ...).
    """
    grouped: dict[tuple[str, str, str], list[int]] = {}
    for index, record in enumerate(records):
        grouped.setdefault((record["chapter"], record["scene"], record["family"]), []).append(index)

    drop: set[int] = set()  # global indices into records
    for indices in grouped.values():
        normalized = [_normalize_gender(records[i]["text"]) for i in indices]

        def find_twin(position: int) -> int | None:
            record = records[indices[position]]
            norm = normalized[position]
            for other_pos, c_norm in enumerate(normalized):
                other = indices[other_pos]
                if other_pos == position or other in drop:
                    continue
                c_text = records[other]["text"]
                if c_text == record["text"]:
                    continue  # same wording is a duplicate, not a branch pair
                if abs(len(c_text) - len(record["text"])) > max(4, len(record["text"]) // 5):
                    continue
                # Branch pairs often rephrase slightly (我查过了/我查了一下),
                # so after blanking the gendered tokens a 0.7 bar is enough.
                if difflib.SequenceMatcher(None, norm, c_norm).ratio() < 0.7:
                    continue
                return other
            return None

        # Pass 1: explicit Belle markers (师妹, 哥哥, ...).
        for position, index in enumerate(indices):
            record = records[index]
            speaker = record["speaker"]
            if speaker and len(speaker) <= 4 and speaker.endswith("哲"):
                continue  # Wise himself is speaking
            text = record["text"]
            if any(token in text for token in MALE_ADDRESS):
                continue  # male-branch address is kept
            if not any(marker in text for marker in _BELLE_MARKERS):
                continue
            if find_twin(position) is not None:
                drop.add(index)

        # Pass 2: bare-铃 vocatives whose surviving twin addresses 哲.
        for position, index in enumerate(indices):
            if index in drop:
                continue
            record = records[index]
            speaker = record["speaker"]
            if speaker and len(speaker) <= 4 and speaker.endswith("哲"):
                continue
            text = record["text"]
            if "铃" not in text or any(marker in text for marker in _BELLE_MARKERS):
                continue
            if any(token in text for token in MALE_ADDRESS):
                continue
            twin = find_twin(position)
            if twin is None:
                continue
            twin_text = records[twin]["text"]
            if "哲" in twin_text and "铃" not in twin_text:
                drop.add(index)

    if not drop:
        return records, 0
    return [record for index, record in enumerate(records) if index not in drop], len(drop)

def _is_protagonist_name(name: str | None) -> bool:
    # Covers 铃/哲 and costume variants such as 学生铃 or 道士哲.
    return bool(name) and len(name) <= 4 and name[-1] in "铃哲"


def _same_up_to_protagonist(a: str | None, b: str | None) -> bool:
    return bool(a and b) and a != b and a.replace("哲", "铃") == b.replace("哲", "铃")


def _dedupe_records(
    records: list[dict],
    protagonist: str | None,
    *,
    canonical: bool = True,
) -> tuple[list[dict], int]:
    """Remove duplicated protagonist-branch copies of the same line.

    Identical text alone is not a duplicate: NPCs legitimately repeat short
    lines such as ``……`` within one scene.  A repeat is dropped only when it
    is the other protagonist's copy, sits right next to its twin, or belongs
    to a duplicated run (a branch block copied for both protagonists).
    With ``canonical=False`` only adjacent same-speaker repeats are removed.
    """
    own = "铃" if protagonist == "F" else ("哲" if protagonist == "M" else None)

    def preference(record: dict) -> int:
        speaker = record["speaker"]
        if own and _is_protagonist_name(speaker) and speaker.endswith(own):
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
                    _same_up_to_protagonist(a, b)
                    or (gap <= 3 and (a is None or b is None) and (_is_protagonist_name(a) or _is_protagonist_name(b)))
                    or (gap == 1 and (a == b or a is None or b is None))
                    or (j > 0 and i - 1 != j and group[i - 1]["text"] == group[j - 1]["text"])
                    or (i + 1 < len(group) and j + 1 != i and group[i + 1]["text"] == group[j + 1]["text"])
                )
            else:
                duplicate = gap == 1 and a == b
            if not duplicate:
                continue
            if preference(record) > preference(prev):
                drop.add(id(prev))
                first[text] = i
            else:
                drop.add(id(record))

    if not drop:
        return records, 0
    return [record for record in records if id(record) not in drop], len(drop)


def _assign_line_ids(records: list[dict]) -> None:
    used: set[str] = set()
    for index, record in enumerate(records, 1):
        chapter = chapter_info(record["chapter"]).short or "X"
        base = f"CH{record['chapter_order']:02d}_{chapter}_{record['family']}_{record['scene']}_{record['line_no']:04d}"
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
        record["line_id"] = f"SUP{index:05d}"
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
        "speaker_alias",
        "speaker_confidence",
        "speaker_source",
        "text",
        "raw_text",
        "text_variants",
        "source_key",
        "line_type",
        "scene_speakers",
        "order",
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
            row["scene_speakers"] = "、".join(row["scene_speakers"])
            writer.writerow(row)
