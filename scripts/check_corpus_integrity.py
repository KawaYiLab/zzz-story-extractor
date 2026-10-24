"""Check optimized output against an accuracy-first extraction of the same input."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def rows(path: Path, *, optional: bool = False) -> list[dict]:
    if optional and not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def raw_text(row: dict) -> str:
    return row.get("raw_text") if row.get("raw_text") is not None else row.get("text", "")


def check(output: Path, audit: Path) -> dict:
    manifests = [json.loads((directory / "manifest.json").read_text(encoding="utf-8")) for directory in (output, audit)]
    require(manifests[0].get("accuracy_first") is False and manifests[1].get("accuracy_first") is True,
            "必须分别提供默认输出与完整性输出")
    for key in ("language", "files", "chapter_filter", "limit", "include_supplement"):
        require(manifests[0].get(key) == manifests[1].get(key), f"两次输入/范围不同：{key}")
    require(bool(manifests[0].get("files")), "manifest 必须保留输入文件哈希")
    retained = rows(output / "story.jsonl") + rows(output / "supplement.jsonl", optional=True)
    candidates = rows(audit / "story.jsonl") + rows(audit / "supplement.jsonl", optional=True)
    removed = rows(output / "discarded.jsonl")
    candidate_keys = Counter(row["source_key"] for row in candidates)
    retained_keys = Counter(row["source_key"] for row in retained)
    removed_lines = [row for row in removed if row.get("record_kind", "line") == "line"]
    removed_keys = Counter(row["source_key"] for row in removed_lines)
    require(all(n == 1 for n in candidate_keys.values()), "候选来源键不得重复")
    require(retained_keys + removed_keys == candidate_keys, "候选记录必须全部落在正文或删减审计中")
    require(not (retained_keys & removed_keys), "正文与删减审计不得重叠")
    ids = [row.get("line_id") for row in retained]
    require(all(isinstance(i, str) and i for i in ids) and len(set(ids)) == len(retained), "稳定 ID 不得缺失或重复")
    originals = {row["source_key"]: row for row in candidates}
    for row in retained + removed_lines:
        require(raw_text(row) == raw_text(originals[row["source_key"]]), f"原文不一致：{row['source_key']}")
    for row in removed_lines:
        require(bool(row.get("reason")) and bool(row.get("raw_text")), row["source_key"])
        require(row.get("paired_source_key") in candidate_keys and row.get("paired_source_key") != row["source_key"],
                f"配对来源无效：{row['source_key']}")
    for row in retained:
        require(row["line_id"] == originals[row["source_key"]]["line_id"], f"稳定 ID 漂移：{row['source_key']}")
        require(row.get("chronology_status") == "unknown", row["source_key"])
        require(not any(key.startswith("_discard") or key == "_paired_source_key" for key in row), row["source_key"])
    names = {row["source_key"]: row for row in rows(audit / "name_candidates.jsonl")}
    for row in removed:
        if row.get("record_kind") != "name":
            continue
        key = row["source_key"]
        require(key in names and row.get("paired_source_key") in names, f"姓名候选缺失：{key}")
        require(raw_text(row) == raw_text(names[key]) and bool(row.get("reason")), f"姓名原文/原因无效：{key}")
    require(not rows(audit / "discarded.jsonl"), "完整性模式不应删减")
    result = {"candidates": len(candidates), "retained": len(retained), "removed_lines": len(removed_lines), "removed_names": len(removed) - len(removed_lines)}
    for filename, label in (("source-variants.jsonl", "source_variants"), ("source-gaps.jsonl", "source_gaps")):
        default_sources = rows(output / filename, optional=True)
        audit_sources = rows(audit / filename, optional=True)
        require(default_sources == audit_sources, f"来源审计两种模式不一致：{filename}")
        keys = [row["source_key"] for row in default_sources]
        require(len(keys) == len(set(keys)), f"来源审计重复：{filename}")
        result[label] = len(keys)
    lore_rel = "lore/agents/dialogue-audit.jsonl"
    if (output / lore_rel).exists() or (audit / lore_rel).exists():
        defaults, full = rows(output / lore_rel), rows(audit / lore_rel)
        full_by_key = {row["source_key"]: row for row in full}
        default_by_key = {row["source_key"]: row for row in defaults}
        require(len(full_by_key) == len(full) and len(default_by_key) == len(defaults), "设定互动来源键重复")
        require(default_by_key.keys() == full_by_key.keys(), "设定互动候选来源键缺失")
        require(all(row["retained"] or row.get("reason") == "empty_text" for row in full), "完整性设定互动不应删减非空原文")
        for row in defaults:
            require(row["raw_text"] == full_by_key[row["source_key"]]["raw_text"], f"设定原文变化：{row['source_key']}")
            if not row["retained"]:
                if row.get("reason") == "empty_text":
                    require(not row.get("text"), f"空文本标记无效：{row['source_key']}")
                    continue
                peer = default_by_key.get(row.get("paired_source_key"))
                require(bool(row.get("reason")) and peer is not None and peer["retained"], f"设定删减配对无效：{row['source_key']}")
        result.update(lore_dialogue_candidates=len(full), lore_dialogue_removed=sum(not row["retained"] for row in defaults))
    for rel, label in (("lore/street/dialogue-audit.jsonl", "street_dialogue"),
                       ("lore/interknot/message-audit.jsonl", "messages"),
                       ("lore/interknot/message-extra-sources.jsonl", "message_extra_sources")):
        if not (output / rel).exists() and not (audit / rel).exists():
            continue
        defaults, full = rows(output / rel), rows(audit / rel)
        by_key = {row["source_key"]: row for row in full}
        default_by_key = {row["source_key"]: row for row in defaults}
        require(len(by_key) == len(full) and len(default_by_key) == len(defaults), f"来源键重复：{rel}")
        require(by_key.keys() == default_by_key.keys(), f"来源键缺失：{rel}")
        for row in defaults:
            require(raw_text(row) == raw_text(by_key[row["source_key"]]), f"原文变化：{row['source_key']}")
            if row.get("retained") is False:
                if row.get("reason") == "empty_text":
                    require(not row.get("text"), row["source_key"])
                else:
                    peer = default_by_key.get(row.get("paired_source_key"))
                    require(peer is not None and peer.get("retained") and bool(row.get("reason")), row["source_key"])
        require(all(row.get("retained") is not False or row.get("reason") == "empty_text" for row in full),
                f"完整性审计仍有非空删减：{rel}")
        result[label + "_candidates"] = len(full)
    for rel, label in (("lore/interknot/message-config-audit.jsonl", "message_config_events"),
                       ("lore/interknot/message-item-audit.jsonl", "message_items"),
                       ("lore/street/metadata-audit.jsonl", "street_metadata")):
        defaults, full = rows(output / rel, optional=True), rows(audit / rel, optional=True)
        require(defaults == full, f"配置来源/事件审计不一致：{rel}")
        result[label] = len(full)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.output, args.audit), ensure_ascii=False, indent=2))
