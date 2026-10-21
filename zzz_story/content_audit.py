"""Reproducible full-output content and export audit; findings are not deletions."""

from __future__ import annotations

import argparse
import csv
import json
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from .validate import validate_output
from .narrative import attribution_summary
from .writers import write_chapter_files, write_story_txt, write_supplement_txt, _atomic_write_text


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def export_errors(output: Path, story: list[dict], supplement: list[dict]) -> list[str]:
    errors = []
    with tempfile.TemporaryDirectory(prefix="zzz-export-audit-") as tmp:
        root = Path(tmp)
        if (output / "story.txt").exists():
            write_story_txt(story, root / "story.txt")
            if (root / "story.txt").read_bytes() != (output / "story.txt").read_bytes():
                errors.append("story.txt differs from JSONL rendering")
        if (output / "supplement.txt").exists():
            write_supplement_txt(supplement, root / "supplement.txt")
            if (root / "supplement.txt").read_bytes() != (output / "supplement.txt").read_bytes():
                errors.append("supplement.txt differs from JSONL rendering")
        if (output / "chapters").exists():
            write_chapter_files(story, root / "chapters")
            expected = {p.name for p in (root / "chapters").glob("*.txt")}
            actual = {p.name for p in (output / "chapters").glob("*.txt")}
            if expected != actual:
                errors.append("chapter file inventory differs")
            for name in expected & actual:
                if (root / "chapters" / name).read_bytes() != (output / "chapters" / name).read_bytes():
                    errors.append(f"chapter rendering differs: {name}")
    if (output / "story.csv").exists():
        with (output / "story.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != len(story):
            errors.append("CSV record count differs")
        for expected, actual in zip(story, rows):
            for field in ("source_key", "line_id", "text", "raw_text", "speaker"):
                if actual.get(field, "") != (expected.get(field) or ""):
                    errors.append(f"CSV {field} differs: {expected['source_key']}")
            if actual.get("scene_speakers", "") != "、".join(expected.get("scene_speakers") or []):
                errors.append(f"CSV scene_speakers differs: {expected['source_key']}")
            for field in ("perform", "timeline", "text_variants", "source_attribution", "content_evidence"):
                value = actual.get(field, "")
                try:
                    decoded = json.loads(value) if value else None
                except (ValueError, TypeError):
                    errors.append(f"CSV invalid JSON {field}: {expected['source_key']}")
                    continue
                if decoded != (expected.get(field) or None):
                    errors.append(f"CSV {field} differs: {expected['source_key']}")
    return errors


def audit(output: Path, *, baseline: Path | None = None, cache: Path | None = None) -> dict:
    story = read_rows(output / "story.jsonl")
    supplement = read_rows(output / "supplement.jsonl")
    discarded = read_rows(output / "discarded.jsonl")
    groups = defaultdict(list)
    for row in story:
        groups[(row["chapter"], row["family"], row["scene"])].append(row)
    inventory = json.loads(cache.read_text(encoding="utf-8")).get("perform_inventory", {}) if cache else {}
    prefixes = defaultdict(set)
    for graph in inventory.values():
        prefixes[graph["name"]].update(graph["keys"])
    repeats = []
    for group, rows in groups.items():
        for previous, row in zip(rows, rows[1:]):
            if row["text"] != previous["text"]:
                continue
            source_keys = [previous["source_key"], row["source_key"]]
            metadata = [r.get("perform") or r.get("timeline") for r in (previous, row)]
            if previous["line_type"] == "option" or row["line_type"] == "option":
                status = "option_and_dialogue_or_options"
            elif all(metadata):
                status = "both_referenced_review_playback"
            elif any(metadata):
                status = "partially_referenced"
            else:
                status = "no_structured_evidence"
            repeats.append({"chapter": group[0], "family": group[1], "scene": group[2],
                            "source_keys": source_keys, "speakers": [previous["speaker"], row["speaker"]],
                            "text": row["text"], "length": len(row["text"]), "status": status})
    supplement_groups = defaultdict(list)
    for row in supplement:
        supplement_groups[(row["chapter"], row["family"], row["scene"])].append(row)
    supplement_repeats = [{"source_keys": [a["source_key"], b["source_key"]], "text": b["text"]}
                          for rows in supplement_groups.values() for a, b in zip(rows, rows[1:]) if a["text"] == b["text"]]
    lore_repeats = []
    lore_files = list((output / "lore").rglob("*.md"))
    for path in lore_files:
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, (a, b) in enumerate(zip(lines, lines[1:]), 2):
            if a.strip() and a == b and a.strip() != "---":
                lore_repeats.append({"file": path.relative_to(output).as_posix(), "line": index, "text": b})
    lore_dialogues = read_rows(output / "lore/agents/dialogue-audit.jsonl")
    lore_retained = [row for row in lore_dialogues if row["retained"]]
    lore_pairs = [{"source_keys": [a["source_key"], b["source_key"]], "text": b["text"]}
                  for a, b in zip(lore_retained, lore_retained[1:]) if a["text"] == b["text"]]
    gaps = [{"chapter": group[0], "family": group[1], "scene": group[2], "lines": len(rows)}
            for group, rows in groups.items() if not any(r["speaker"] for r in rows)
            and any(r.get("speaker_status") == "unresolved" if "speaker_status" in r
                    else r.get("line_type") == "unknown" for r in rows)]
    unreferenced = []
    for group, rows in groups.items():
        if group[1] != "GalGame":
            continue
        prefix = f"Main_GalGame_{group[0]}_{group[2]}"
        if prefix not in prefixes:
            continue
        missing = [r["source_key"] for r in rows if r["source_key"] not in prefixes[prefix] and not r.get("timeline")]
        if missing:
            unreferenced.append({"chapter": group[0], "family": group[1], "scene": group[2],
                                 "retained_lines": len(rows), "referenced_keys": len(prefixes[prefix]), "unreferenced_keys": missing})
    anomalies = []
    markup = re.compile(r"</?(?:color|size|b|i|u|sprite)(?:[=>\s])|LAYOUT_[A-Z]", re.IGNORECASE)
    for row in story + supplement:
        reasons = []
        if not row.get("text", "").strip():
            reasons.append("empty_text")
        if "\ufffd" in row.get("text", ""):
            reasons.append("replacement_character")
        if markup.search(row.get("text", "")):
            reasons.append("uncleaned_markup")
        if reasons:
            anomalies.append({"source_key": row["source_key"], "reasons": reasons, "text": row["text"]})
    errors = export_errors(output, story, supplement)
    errors += [str(issue) for issue in validate_output(output) if issue.level == "error"]
    change = {}
    if baseline:
        old = {r["source_key"]: r for r in read_rows(baseline / "story.jsonl")}
        new = {r["source_key"]: r for r in story}
        common = old.keys() & new.keys()
        reason_by_key = {r["source_key"]: r["reason"] for r in discarded}
        change = {"removed": sorted(old.keys() - new.keys()), "restored": sorted(new.keys() - old.keys()),
                  "retained_text_changes": [k for k in sorted(common) if old[k]["text"] != new[k]["text"]],
                  "speaker_changes": [{"source_key": k, "before": old[k]["speaker"], "after": new[k]["speaker"]}
                                      for k in sorted(common) if old[k]["speaker"] != new[k]["speaker"]],
                  "removed_by_reason": dict(Counter(reason_by_key.get(k, "MISSING_AUDIT") for k in old.keys() - new.keys()))}
    return {"summary": {"main_lines": len(story), "supplement_lines": len(supplement), "scene_groups": len(groups),
                         "adjacent_equal_pairs": len(repeats), "long_equal_pairs": sum(r["length"] >= 12 for r in repeats),
                         "equal_pair_status": dict(Counter(r["status"] for r in repeats)),
                         "unattributed_scene_groups": len(gaps), "partially_referenced_scenes": len(unreferenced),
                         "supplement_equal_pairs": len(supplement_repeats), "lore_files_checked": len(lore_files),
                         "lore_adjacent_equal_lines": len(lore_repeats),
                         "lore_dialogue_candidates": len(lore_dialogues), "lore_dialogue_retained": len(lore_retained),
                         "lore_dialogue_equal_pairs": len(lore_pairs),
                         "structured_assets": len(inventory), "text_anomalies": len(anomalies), "export_errors": len(errors)},
            "reviewed_placeholders": [row for row in story if row.get("content_status") == "reviewed_placeholder"],
            "notes": ["相邻同文是待核对信号，不等同于提取错误；选项与回答、停顿和真实重复必须保留。",
                      "未引用文本可能来自旧版本、子剧情、外部时间轴或缺失资源；不能仅凭未引用删除。",
                      "本文核验目录结构、原文保存及本地资源证据，不声称已确认所有运行时播放路径。"],
            "attribution": attribution_summary(story),
            "export_errors": errors, "repeated_pairs": repeats, "unattributed_scenes": gaps,
            "unreferenced_scene_candidates": unreferenced, "text_anomalies": anomalies, "changes": change,
            "supplement_repeated_pairs": supplement_repeats, "lore_repeated_lines": lore_repeats,
            "lore_dialogue_repeated_pairs": lore_pairs}


def write_report(result: dict, path: Path) -> None:
    lines = ["# 3.3 全量提取质量检查", "", "## 汇总", ""]
    lines += [f"- {key}: {value}" for key, value in result["summary"].items()]
    lines += ["", *result["notes"], "", "## 修复对比", ""]
    changes = result["changes"]
    lines += [f"- 新增移入审计: {len(changes.get('removed', []))}",
              f"- 恢复候选: {len(changes.get('restored', []))}",
              f"- 保留正文变化: {len(changes.get('retained_text_changes', []))}",
              f"- 角色标注变化: {len(changes.get('speaker_changes', []))}",
              f"- 新增删减原因: {changes.get('removed_by_reason', {})}", "", "## 长同文待核对", ""]
    for pair in result["repeated_pairs"]:
        if pair["length"] >= 12:
            lines += [f"- {' / '.join(pair['source_keys'])} [{pair['status']}]",
                      "  " + pair["text"].replace("\n", " ")]
    lines += ["", "完整逐项结果见同目录 content-audit.json，所有删减原文见 discarded.jsonl。"]
    _atomic_write_text(path / "content-audit.md", "\n".join(lines) + "\n")
    _atomic_write_text(path / "content-audit.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()
    result = audit(args.output, baseline=args.baseline, cache=args.cache)
    write_report(result, args.output)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    if result["export_errors"]:
        raise SystemExit(1)
