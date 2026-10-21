"""Post-extraction validation.

The one structural invariant that is easy to break when the game renumbers
chapters: a supplement group (CS cutscene subtitles) must never land on a
main-story chapter token that belongs to a different season.  In 3.2.0 the
season-2 CS keys (``CS_21`` .. ``CS_25``) were still mapped to
``Chapter210`` .. ``Chapter250`` while those tokens had already become
season 3, so every season-3 chapter silently carried another season's
subtitles.  ``validate_records`` is the regression guard for that class of
bug, and ``validate_output`` runs it over a finished extraction directory.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .chapters import chapter_info
from .narrative import reviewed_outline


@dataclass(frozen=True)
class Issue:
    level: str  # error | warning | info
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.code}: {self.message}"


def _chapter_labels(rows: list[dict]) -> dict[str, set[str]]:
    labels: dict[str, set[str]] = {}
    for row in rows:
        chapter = row.get("chapter") or ""
        label = row.get("chapter_label") or ""
        labels.setdefault(chapter, set()).add(label)
    return labels


def validate_records(records: list[dict], supplements: list[dict] | None = None) -> list[Issue]:
    """Check a parsed extraction in memory.  Cheap enough to run on every extract."""
    issues: list[Issue] = []

    if not records:
        issues.append(Issue("error", "empty-story", "主线记录为空，抽取参数或数据源可能有问题"))
        return issues

    all_rows = records + (supplements or [])
    unclassified = [row for row in records if reviewed_outline(row) and row.get("content_status") != "reviewed_placeholder"]
    if unclassified:
        issues.append(Issue("warning", "unclassified-placeholder", f"{len(unclassified)} 条已核对的剧情占位说明仍作为正式正文显示（例如 {unclassified[0].get('source_key')}）"))
    bad_placeholders = [row for row in records if row.get("content_status") == "reviewed_placeholder"
                        and (row.get("speaker") or row.get("scene_speakers") or row.get("line_type") != "placeholder")]
    if bad_placeholders:
        issues.append(Issue("error", "placeholder-attribution", "剧情占位说明仍含对白署名或出场名单"))
    missing = sum(not isinstance(row.get("line_id"), str) or not row["line_id"].strip() for row in all_rows)
    if missing:
        issues.append(Issue("error", "missing-line-id", f"{missing} 条记录缺少有效 line_id"))
    ids = Counter(row["line_id"] for row in all_rows if isinstance(row.get("line_id"), str) and row["line_id"].strip())
    duplicates = sum(count - 1 for count in ids.values() if count > 1)
    if duplicates:
        example = next(line_id for line_id, count in ids.items() if count > 1)
        issues.append(
            Issue("error", "duplicate-line-id", f"{duplicates} 条重复 line_id（例如 {example}）")
        )

    main_labels = _chapter_labels(records)
    for chapter, labels in main_labels.items():
        if len(labels) > 1:
            issues.append(
                Issue("error", "chapter-label-conflict", f"章节 {chapter} 出现多个标题：{sorted(labels)}")
            )
        if chapter and not chapter_info(chapter).known:
            issues.append(
                Issue(
                    "warning",
                    "unknown-chapter",
                    f"章节 {chapter} 不在章节表内，已按规则推导为「{chapter_info(chapter).label}」",
                )
            )

    supplement_labels = _chapter_labels(supplements or [])
    for chapter, labels in supplement_labels.items():
        if chapter not in main_labels:
            continue
        main_label = sorted(main_labels[chapter])[0]
        if all(label == main_label for label in labels):
            continue
        issues.append(
            Issue(
                "error",
                "supplement-chapter-shadow",
                f"补充文本被挂到主线章节 {chapter}（{main_label}）上，标题却是 {sorted(labels)}；"
                "章节编号可能又变过，请检查 CS 编号映射（chapters.season_chapter_token）",
            )
        )

    return issues


def validate_output(out_dir: Path) -> list[Issue]:
    """Validate a directory produced by ``zzz-story extract``."""
    out_dir = Path(out_dir)
    story = out_dir / "story.jsonl"
    if not story.exists():
        return [Issue("error", "missing-output", f"找不到 {story}，请先运行 extract")]

    records = _read_jsonl(story)
    supplements = _read_jsonl(out_dir / "supplement.jsonl")
    return validate_records(records, supplements)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
