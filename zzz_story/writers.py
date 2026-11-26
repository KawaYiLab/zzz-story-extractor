"""Write the JSONL and manifest members of the story corpus."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_jsonl(records: Iterable[dict], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    count = 0
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")
                count += 1
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return count


def _record_line(record: dict) -> str:
    if record.get("content_status") == "reviewed_placeholder":
        return f"（剧情占位说明）{record.get('text', '')}"
    if record.get("line_type") == "option":
        return f"> 选项：{record.get('text', '')}"
    speaker = record.get("speaker")
    text = record.get("text", "")
    if speaker:
        return f"【{speaker}】{text}"
    if record.get("line_type") == "unknown":
        if record.get("speaker_slot"):
            return f"（角色槽位 {record['speaker_slot']}，姓名未关联）{text}"
        return f"（未标注）{text}"
    # Akasha-style presentation: narration is plain text, not a fake speaker.
    return text


def write_json(path: Path, payload: dict) -> None:
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
