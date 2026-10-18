"""Main extraction pipeline."""

from __future__ import annotations

import csv
import difflib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .chapters import chapter_info, sort_key as chapter_sort_key
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
from .speakers import SpeakerInfo, build_speaker_index
from .textmap import TextMap, load_text_map
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
FAMILY_ORDER = {
    "GalGame": 0,
    "Chat": 1,
    "BubbleStory": 2,
    "Bubble": 3,
    "OngoingLevel": 4,
    "OngoingMainCity": 5,
    "Ongoing": 6,
    "ChatAudio": 7,
    "ChatPlus": 8,
    "OngoingAntique": 9,
    "MainChat": 10,
}

NAME_IGNORE = {"选项", "玩家选项", "旁白", "咨询", "购买", "找零"}
PLAYER_NAMES = {"铃", "哲"}
# Explicit forms of address that identify the two protagonist branches.
MALE_ADDRESS = ("小师弟", "师弟", "哲小哥", "哲先生", "哲哥")
FEMALE_ADDRESS = ("小师妹", "师妹", "小铃", "铃小姐", "铃姐")
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
    deduped: int = 0
    branch_filtered: int = 0
    gender_pair_filtered: int = 0
    by_family: dict[str, int] = field(default_factory=dict)
    by_chapter: dict[str, int] = field(default_factory=dict)
    supplement_lines: int = 0
    speaker_stats: dict = field(default_factory=dict)


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


def _line_sort_key(record: dict) -> tuple:
    info = chapter_info(record["chapter"])
    return (
        info.order,
        natural_scene_key(record["scene"]),
        FAMILY_ORDER.get(record["family"], 50),
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
    protagonist: str = "F",
    formats: str = "jsonl,txt",
    include_supplement: bool = True,
    dedupe: bool = True,
    canonical_gender: bool = True,
    limit: int | None = None,
) -> ExtractStats:
    protagonist = protagonist.upper()
    if protagonist not in {"M", "F", "BOTH"}:
        raise ValueError("protagonist must be M, F or BOTH")

    out_dir.mkdir(parents=True, exist_ok=True)
    data_paths = ensure_data(lang=lang, refresh=refresh, data_dir=data_dir)
    print("Loading TextMap...")
    text_map = load_text_map(data_paths, language=lang)
    print(f"  {len(text_map)} entries loaded")
    scene_titles = _load_scene_titles(data_paths, text_map)

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

    # Keys ending in F are sibling-protagonist variants of the base key.
    # In the default female-protagonist mode keep F and drop the base line;
    # in male mode do the reverse.  This removes duplicate male/female copies.
    f_base_keys: set[str] = set()
    f_variant_keys: set[str] = set()
    for key in text_map.keys():
        if key.endswith("F") and re.search(r"(?:Name_?\d+|\d+)F$", key):
            base = key[:-1]
            if base in text_map:
                f_base_keys.add(base)
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
        if protagonist == "F" and key in f_base_keys:
            continue
        if protagonist == "M" and key in f_variant_keys:
            continue
        if parsed.family in MAIN_FAMILIES or parsed.family == "MainChat":
            if limit is not None and stats.line_keys >= limit:
                continue
            if parsed.kind == "name":
                raw = text_map.get(key)
                cleaned = clean_text(raw, protagonist if protagonist != "BOTH" else "F").text
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
            if protagonist == "BOTH":
                cleaned_m = clean_text(raw, "M")
                cleaned_f = clean_text(raw, "F")
                if not cleaned_m.text and not cleaned_f.text:
                    continue
                if cleaned_m.text == cleaned_f.text:
                    pending.append(
                        _pending_record(
                            parsed,
                            cleaned_f.text or cleaned_m.text,
                            raw,
                            None,
                            parsed.variant,
                        )
                    )
                else:
                    variants = {
                        gender: cleaned.text
                        for gender, cleaned in (("M", cleaned_m), ("F", cleaned_f))
                        if cleaned.text
                    }
                    for gender, text in variants.items():
                        pending.append(_pending_record(parsed, text, raw, variants, gender))
            else:
                cleaned = clean_text(raw, protagonist)
                if not cleaned.text:
                    continue
                if canonical_gender and protagonist in {"M", "F"}:
                    has_male = any(token in cleaned.text for token in MALE_ADDRESS)
                    has_female = any(token in cleaned.text for token in FEMALE_ADDRESS)
                    if protagonist == "F" and has_male and not has_female:
                        stats.branch_filtered += 1
                        continue
                    if protagonist == "M" and has_female and not has_male:
                        stats.branch_filtered += 1
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
            cleaned = clean_text(raw, "F" if protagonist == "BOTH" else protagonist)
            if not cleaned.text:
                continue
            supplement.append(
                {
                    "family": parsed.family,
                    "source_key": key,
                    "chapter": "补充",
                    "chapter_label": "补充文本",
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
        no_speakers=no_speakers or game_dir is None,
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

        if has_voice:
            stats.voice_linked += 1
            if speaker:
                stats.voice_speaker += 1

        info_chapter = chapter_info(chapter)
        display_speakers = [name for name in scene_names if name not in NAME_IGNORE]
        record = {
            "line_id": "",
            "chapter": chapter,
            "chapter_label": info_chapter.label,
            "chapter_order": info_chapter.order,
            "scene": scene,
            "scene_act": 0,
            "scene_title": None,
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
            "line_type": "dialogue" if speaker else ("unknown" if has_voice else "narration"),
            "scene_speakers": display_speakers,
            "order": 0,
        }
        records.append(record)

    if canonical_gender and protagonist in {"M", "F"}:
        records, dropped = _collapse_gender_pairs(records, protagonist)
        stats.gender_pair_filtered += dropped

    records.sort(key=_line_sort_key)
    if dedupe:
        seen: set[tuple] = set()
        kept: list[dict] = []
        for record in records:
            key = (
                record["chapter"],
                record["scene"],
                record["variant"],
                record["text"],
            )
            if key in seen:
                stats.deduped += 1
                continue
            seen.add(key)
            kept.append(record)
        records = kept

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
        stats.by_chapter[record["chapter_label"]] = stats.by_chapter.get(record["chapter_label"], 0) + 1

    supplement.sort(key=lambda item: (item["family"], item["source_key"]))
    _assign_supplement_ids(supplement)

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

    source_version = fetch_source_version()
    file_hashes = {}
    for rel, path in data_paths.items():
        try:
            file_hashes[rel] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
        except OSError:
            file_hashes[rel] = {"sha256": "", "bytes": 0}

    coverage = {
        "total_lines": stats.total_lines,
        "speaker_lines": stats.speaker_lines,
        "speaker_null": stats.speaker_null,
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
    }
    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "language": lang,
        "source_version": source_version,
        "local_game_version": read_game_version(game_dir) if game_dir else "",
        "game_dir": str(game_dir) if game_dir else "",
        "protagonist": protagonist,
        "counts": {
            "line_keys": stats.line_keys,
            "name_keys": stats.name_keys,
            "selected_keys": stats.selected_keys,
            "total_lines": stats.total_lines,
            "speaker_lines": stats.speaker_lines,
            "supplement_lines": stats.supplement_lines,
            "branch_filtered": stats.branch_filtered,
            "gender_pair_filtered": stats.gender_pair_filtered,
        },
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
            row["text_variants"] = json.dumps(row["text_variants"], ensure_ascii=False) if row["text_variants"] else ""
            row["scene_speakers"] = "、".join(row["scene_speakers"])
            writer.writerow(row)
