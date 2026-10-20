"""Compare two extraction outputs.

``line_id`` is stable across versions (chapter token, not chapter order), so a
new game version can be diffed by id: added / removed / changed lines.  This
is the "3.3 到底改了什么" view that used to require diffing two 28 MB JSONLs by
hand.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .chapters import chapter_info

_COMPARE = ("text", "speaker", "line_type")


@dataclass
class ChapterDiff:
    token: str
    label: str
    added: int = 0
    removed: int = 0
    changed: int = 0
    examples: list[tuple[str, dict]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.added + self.removed + self.changed


@dataclass
class DiffResult:
    old_dir: Path
    new_dir: Path
    chapters: list[ChapterDiff]

    @property
    def added(self) -> int:
        return sum(chapter.added for chapter in self.chapters)

    @property
    def removed(self) -> int:
        return sum(chapter.removed for chapter in self.chapters)

    @property
    def changed(self) -> int:
        return sum(chapter.changed for chapter in self.chapters)


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _changed(old: dict, new: dict) -> bool:
    return any(old.get(field) != new.get(field) for field in _COMPARE)


def diff_outputs(old_dir: Path, new_dir: Path, examples: int = 3) -> DiffResult:
    old_dir, new_dir = Path(old_dir), Path(new_dir)
    old_rows = _read(old_dir / "story.jsonl")
    new_rows = _read(new_dir / "story.jsonl")
    old_by_id = {row["line_id"]: row for row in old_rows}
    new_by_id = {row["line_id"]: row for row in new_rows}

    per_chapter: dict[str, ChapterDiff] = {}

    def entry(record: dict) -> ChapterDiff:
        token = record.get("chapter") or "未分章"
        item = per_chapter.get(token)
        if item is None:
            item = ChapterDiff(token, record.get("chapter_label") or token)
            per_chapter[token] = item
        return item

    def sample(item: ChapterDiff, kind: str, old: dict | None, new: dict | None) -> None:
        if examples <= 0 or len(item.examples) >= examples:
            return
        source = new or old or {}
        item.examples.append(
            (
                kind,
                {
                    "line_id": source.get("line_id"),
                    "speaker": source.get("speaker"),
                    "old_text": (old or {}).get("text"),
                    "text": (new or {}).get("text"),
                },
            )
        )

    for line_id in sorted(new_by_id.keys() - old_by_id.keys(), key=lambda key: new_by_id[key].get("order", 0)):
        new = new_by_id[line_id]
        item = entry(new)
        item.added += 1
        sample(item, "added", None, new)

    for line_id in sorted(old_by_id.keys() - new_by_id.keys(), key=lambda key: old_by_id[key].get("order", 0)):
        old = old_by_id[line_id]
        item = entry(old)
        item.removed += 1
        sample(item, "removed", old, None)

    for line_id in old_by_id.keys() & new_by_id.keys():
        old, new = old_by_id[line_id], new_by_id[line_id]
        if not _changed(old, new):
            continue
        item = entry(new)
        item.changed += 1
        sample(item, "changed", old, new)

    chapters = sorted(
        (chapter for chapter in per_chapter.values() if chapter.total),
        key=lambda chapter: (chapter_info(chapter.token).order, chapter.token),
    )
    return DiffResult(old_dir, new_dir, chapters)


def format_diff(result: DiffResult) -> str:
    lines = [
        f"章节对比：{result.old_dir} → {result.new_dir}",
        "",
        f"合计：+{result.added} 新增，-{result.removed} 删除，~{result.changed} 修改",
    ]
    if not result.chapters:
        lines.append("逐行一致，没有变化。")
        return "\n".join(lines)

    lines.append("")
    for chapter in result.chapters:
        lines.append(
            f"  {chapter.label}（{chapter.token}）：+{chapter.added} -{chapter.removed} ~{chapter.changed}"
        )
        for kind, sample in chapter.examples:
            speaker = sample.get("speaker") or "旁白"
            text = (sample.get("text") or "").replace("\n", " ")[:40]
            old_text = (sample.get("old_text") or "").replace("\n", " ")[:40]
            if kind == "changed":
                lines.append(f"    ~ {speaker}：「{old_text}」 → 「{text}」")
            elif kind == "added":
                lines.append(f"    + {speaker}：{text}")
            else:
                lines.append(f"    - {speaker}：{text}")
    return "\n".join(lines)
