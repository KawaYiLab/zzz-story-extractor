"""Output writers for JSONL, TXT and manifests."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_jsonl(records: Iterable[dict], path: Path) -> int:
    lines: list[str] = []
    count = 0
    for record in records:
        lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        count += 1
    _atomic_write_text(path, "\n".join(lines) + ("\n" if lines else ""))
    return count


def _record_line(record: dict) -> str:
    if record.get("line_type") == "option":
        return f"> 选项：{record.get('text', '')}"
    speaker = record.get("speaker")
    text = record.get("text", "")
    if speaker:
        return f"【{speaker}】{text}"
    if record.get("line_type") == "unknown":
        return f"（未标注）{text}"
    # Akasha-style presentation: narration is plain text, not a fake speaker.
    return text


def _chapters_in_order(records: list[dict]) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    for record in records:
        chapter = record.get("chapter") or "未分章"
        seen.setdefault(chapter, record.get("chapter_label") or chapter)
    return list(seen.items())


def write_story_txt(records: list[dict], path: Path, include_index: bool = True) -> None:
    chunks: list[str] = []
    if any(record.get("chronology_status") == "unknown" for record in records):
        chunks.extend(["> 以下按目录排列；场景编号和幕次不代表剧情时间先后。", ""])
    if include_index:
        chunks.append("# 绝区零主线剧情")
        chunks.append("")
        chunks.append("章节：")
        for chapter, label in _chapters_in_order(records):
            count = sum(1 for record in records if record.get("chapter") == chapter)
            chunks.append(f"- {label}（{chapter}，{count} 行）")
        chunks.append("")
        chunks.append("---")
        chunks.append("")

    scene_cast_map: dict[tuple, list[str]] = {}
    for record in records:
        key = (record.get("chapter"), record.get("family"), record.get("scene"))
        cast = scene_cast_map.setdefault(key, [])
        for spk in (record.get("scene_speakers") or []):
            if spk and spk not in cast and spk != "未标注":
                cast.append(spk)
        spk = record.get("speaker")
        if spk and spk not in cast and spk != "未标注":
            cast.append(spk)

    scene_acts: dict[tuple[str, str], int] = {}
    current_chapter_for_acts = None
    act_counter = 0
    for record in records:
        ch = record.get("chapter") or ""
        sc = record.get("scene") or ""
        if ch != current_chapter_for_acts:
            current_chapter_for_acts = ch
            act_counter = 0
        if (ch, sc) not in scene_acts:
            act_counter += 1
            scene_acts[(ch, sc)] = act_counter

    current_chapter = None
    current_scene = None
    current_quest = None
    opt_buffer: list[dict] = []

    def flush_options() -> None:
        if not opt_buffer:
            return
        chunks.append("")
        if len(opt_buffer) == 1:
            chunks.append(f"> 选项：{opt_buffer[0].get('text', '')}")
        else:
            for idx, opt in enumerate(opt_buffer, 1):
                chunks.append(f"> 选项 {idx}：{opt.get('text', '')}")
        chunks.append("")
        opt_buffer.clear()

    for record in records:
        chapter = record.get("chapter")
        if chapter != current_chapter:
            flush_options()
            current_chapter = chapter
            current_scene = None
            current_quest = None
            label = record.get("chapter_label") or chapter
            chunks.append("")
            chunks.append(f"# {label}（{chapter}）")
            chunks.append("")
        scene_key = (record.get("family"), record.get("scene"))
        if scene_key != current_scene:
            flush_options()
            current_scene = scene_key
            quest = record.get("quest_name") if record.get("family") == "GalGame" else None
            if quest != current_quest:
                current_quest = quest
                if quest:
                    chunks.append("")
                    chunks.append(f"### 任务：{quest}")
                    chunks.append("")
            ch = record.get("chapter") or ""
            sc = record.get("scene") or ""
            key = (ch, record.get("family"), sc)
            cast = scene_cast_map.get(key, [])
            act_num = record.get("scene_act") or scene_acts.get((ch, sc), 1)
            title = record.get("scene_title")
            title_str = f"：{title}" if title else ""
            cast_str = f"（出场：{'、'.join(cast)}）" if cast else ""
            chunks.append("")
            chunks.append(f"## 第 {act_num} 幕{title_str}{cast_str}")
            chunks.append("")

        if record.get("line_type") == "option":
            opt_buffer.append(record)
        else:
            flush_options()
            chunks.append(_record_line(record))

    flush_options()

    raw_text = "\n".join(chunks).strip() + "\n"
    text = re.sub(r"\n{3,}", "\n\n", raw_text)
    _atomic_write_text(path, text)


def _safe_filename(value: str, limit: int = 60) -> str:
    value = re.sub(r'[\\/:*?"<>|\s]+', "_", value)
    value = value.strip("._")
    return (value or "chapter")[:limit]


def write_chapter_files(records: list[dict], directory: Path) -> list[Path]:
    """Write one Akasha-style document per chapter, plus an index."""
    directory.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict]] = {}
    for record in records:
        grouped.setdefault(record.get("chapter") or "未分章", []).append(record)

    written: list[Path] = []
    index_lines = ["# 绝区零主线章节", ""]
    for chapter, chapter_records in grouped.items():
        label = chapter_records[0].get("chapter_label") or chapter
        order = int(chapter_records[0].get("chapter_order") or 9999)
        name = f"CH{order:02d}_{_safe_filename(chapter)}_{_safe_filename(label)}.txt"
        path = directory / name
        write_story_txt(chapter_records, path, include_index=False)
        written.append(path)
        index_lines.append(f"- [{label}]({name})（{chapter}，{len(chapter_records)} 行）")

    _atomic_write_text(directory / "index.txt", "\n".join(index_lines).strip() + "\n")
    return written


def write_supplement_txt(records: list[dict], path: Path) -> None:
    chunks: list[str] = ["# 绝区零补充文本（过场动画 CS / 动态漫画 Comic）", ""]
    current_family = None
    current_chapter = None
    current_scene = None
    for record in records:
        family = record.get("family")
        if family != current_family:
            current_family = family
            current_chapter = None
            current_scene = None
            chunks.append("")
            fam_title = "过场动画（CS）" if family == "CS" else ("动态漫画（Comic）" if family == "Comic" else family)
            chunks.append(f"## {fam_title}")
            chunks.append("")

        if family == "CS":
            chapter = record.get("chapter")
            if chapter != current_chapter:
                current_chapter = chapter
                current_scene = None
                label = record.get("chapter_label") or chapter
                chunks.append("")
                chunks.append(f"### {label}")
                chunks.append("")

            scene = record.get("scene")
            if scene != current_scene:
                current_scene = scene
                chunks.append("")
                chunks.append(f"#### 过场 {scene}")
                chunks.append("")

        if family == "Comic":
            source = record.get("source_key") or record.get("line_id") or "未知来源"
            chunks.extend(["", f"### 独立片段 {source}（上下文未关联；相邻片段不代表连续剧情）", ""])
        elif family != "CS" and record.get("scene") != current_scene:
            current_scene = record.get("scene")
            chunks.extend(["", f"### 片段 {current_scene}", ""])
        chunks.append(record.get("text", ""))

    raw_text = "\n".join(chunks).strip() + "\n"
    text = re.sub(r"\n{3,}", "\n\n", raw_text)
    _atomic_write_text(path, text)


def write_json(path: Path, payload: dict) -> None:
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
