"""Read-only acceptance checks for source-keyed MCP lore documents.

Compare already exported source values and audit references with TextMap. This
does not extract content or parse the presentation Markdown files.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zzz_story.clean import clean_text  # noqa: E402
from zzz_story.textmap import load_text_map  # noqa: E402

CATEGORIES = {"agents", "equipment", "interknot", "cinema", "glossary", "street"}
AUDITS = ("agents/dialogue-audit.jsonl", "street/dialogue-audit.jsonl",
          "interknot/message-audit.jsonl", "interknot/message-extra-sources.jsonl",
          "interknot/message-item-audit.jsonl")
SECTIONS = {"introduction", "biography", "commentary", "trust", "daily", "bubble", "other"}


def rows(path: Path):
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"{path.name}:{number}: record must be an object")
                yield number, value


def relative_file(value, suffix: str) -> bool:
    return (isinstance(value, str) and value.endswith(suffix) and not value.startswith("/")
            and not any(character in value for character in "\\:")
            and all(part not in {"", ".", ".."} for part in value.split("/")))


def check(output: Path, data_dir: Path) -> dict:
    lore = output / "lore"
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    paths = {path.relative_to(data_dir).as_posix(): path for path in (data_dir / "TextMap").glob("*.json")}
    if "TextMap/TextMapTemplateTb.json" not in paths:
        raise ValueError("data-dir must contain TextMap/TextMapTemplateTb.json")
    text_map = load_text_map(paths, language=manifest.get("language", "CHS"))
    document_rows = rows(lore / "documents.jsonl")
    _, header = next(document_rows)
    if header.get("schema_version") != 1 or header.get("record_type") != "manifest":
        raise ValueError("documents.jsonl must start with a version 1 manifest")
    protagonist = header.get("protagonist", "M")
    if protagonist not in {"M", "F"}:
        raise ValueError("documents.jsonl manifest protagonist must be M or F")
    covered = header.get("covered_source_files")
    if not isinstance(covered, list) or not all(relative_file(path, ".md") for path in covered):
        raise ValueError("covered_source_files must contain relative Markdown paths")
    errors = []
    error_count = 0

    def expect(condition: bool, message: str) -> None:
        nonlocal error_count
        if not condition:
            error_count += 1
            if len(errors) < 30:
                errors.append(message)

    expect(len(covered) == len(set(covered)), "manifest repeats a covered source file")
    expect(all((lore / path).is_file() for path in covered), "manifest covers a missing Markdown file")
    category_counts = {category: Counter() for category in sorted(CATEGORIES)}

    def source_value(row: dict, context: str, *, requested: str) -> None:
        key = row.get("source_key")
        if not isinstance(key, str) or key not in text_map:
            expect(False, f"{context}: missing TextMap source {key!r}")
            return
        raw = text_map.get(key)
        provided = row.get("raw_text")
        # Omitted raw_text is allowed only when the original is unchanged.
        expect(provided == raw if provided is not None else row.get("text") == raw,
               f"{context}: raw_text differs from TextMap {key}")
        cleaned = clean_text(raw, row.get("selected_variant") or requested)
        expect(row.get("text") == cleaned.text, f"{context}: text differs from cleaned source {key}")
        expect(row.get("text_variants") == cleaned.variants,
               f"{context}: text_variants differ from original source {key}")
        selected = row.get("selected_variant")
        if selected is not None:
            expect(selected in {"M", "F"}, f"{context}: invalid selected_variant")
            if cleaned.variants:
                expect(cleaned.variants.get(selected) == row.get("text"),
                       f"{context}: selected_variant differs from source text")

    event_ids = set()
    config_path = lore / "interknot/message-config-audit.jsonl"
    if config_path.is_file():
        for _, event in rows(config_path):
            event_ids.add(json.dumps(event.get("config_id"), sort_keys=True))

    audit_index = {}
    audit_contexts = {}
    audit_files = list(AUDITS)
    if not (lore / "agents/dialogue-audit.jsonl").exists():
        audit_files.append("agents/unassigned-dialogue.jsonl")
    for filename in audit_files:
        path = lore / filename
        if not path.is_file():
            continue
        for number, row in rows(path):
            sources = row.get("references", []) if filename.endswith("message-item-audit.jsonl") else [row]
            if not isinstance(sources, list):
                expect(False, f"{filename}:{number}: references must be an array")
                continue
            for source in sources:
                if not isinstance(source, dict):
                    expect(False, f"{filename}:{number}: reference must be an object")
                    continue
                if source.get("retained") is False or not source.get("text"):
                    continue
                key = source.get("source_key")
                context = f"{filename}:{number}"
                requested = source.get("variant") if source.get("variant") in {"M", "F"} else protagonist
                source_value(source, context, requested=requested)
                if not isinstance(key, str):
                    continue
                identity = filename, key
                projection = (source.get("text"), source.get("raw_text"), source.get("text_variants"))
                expect(identity not in audit_index or audit_index[identity] == projection,
                       f"{context}: conflicting occurrences for {key}")
                audit_index[identity] = projection
                contexts = audit_contexts.setdefault(identity, {"items": set(), "threads": set(), "row": {}})
                contexts["row"] = {field: source[field] for field in
                                   ("agent_id", "scope", "family", "scene", "event_tag", "thread_id") if field in source}
                if filename.endswith("message-item-audit.jsonl"):
                    contexts["items"].add(str(row.get("item_id")))
                refs = source.get("config_references", [])
                if not isinstance(refs, list):
                    expect(False, f"{context}: config_references must be an array")
                    continue
                for ref in refs:
                    expect(isinstance(ref, dict) and json.dumps(ref.get("config_id"), sort_keys=True) in event_ids,
                           f"{context}: dangling message configuration reference")
                    if isinstance(ref, dict) and ref.get("thread_id") is not None:
                        contexts["threads"].add(str(ref["thread_id"]))
                if not refs and source.get("thread_id") is not None:
                    contexts["threads"].add(str(source["thread_id"]))

    referenced = set()
    doc_ids = set()
    unique_sources = set()
    for number, document in document_rows:
        context = f"documents.jsonl:{number}"
        category = document.get("category")
        if category not in CATEGORIES:
            expect(False, f"{context}: unsupported category {category!r}")
            continue
        counts = category_counts[category]
        counts["documents"] += 1
        expect(document.get("schema_version") == 1 and document.get("record_type") == "document",
               f"{context}: unsupported document schema")
        doc_id = document.get("doc_id")
        expect(isinstance(doc_id, str) and bool(doc_id) and doc_id not in doc_ids,
               f"{context}: missing or repeated doc_id")
        if isinstance(doc_id, str):
            doc_ids.add(doc_id)
        source_file = document.get("source_file")
        expect(source_file in covered and isinstance(source_file, str) and source_file.startswith(category + "/"),
               f"{context}: source_file is not covered in its category")
        items = document.get("items")
        if not isinstance(items, list) or not items:
            expect(False, f"{context}: document needs nonempty items")
            continue
        for index, item in enumerate(items):
            counts["items"] += 1
            item_context = f"{context}:item{index}"
            if not isinstance(item, dict):
                expect(False, f"{item_context}: item must be an object")
                continue
            expect(item.get("section_kind") in SECTIONS, f"{item_context}: invalid section_kind")
            expect(isinstance(item.get("field"), str) and bool(item["field"]), f"{item_context}: missing field")
            if item.get("kind") == "source":
                counts["source_fields"] += 1
                unique_sources.add((category, item.get("source_key")))
                source_value(item, item_context, requested=protagonist)
                expect(item.get("line_type") == "text" and item.get("speaker") is None
                       and item.get("speaker_status") == "not_applicable",
                       f"{item_context}: source metadata must not acquire dialogue attribution")
            elif item.get("kind") == "audit":
                counts["audit_references"] += 1
                identity = item.get("record_source"), item.get("source_key")
                expect(identity in audit_index, f"{item_context}: dangling audit source {identity}")
                expect(isinstance(identity[0], str) and identity[0].startswith(category + "/"),
                       f"{item_context}: audit source belongs to another category")
                referenced.add(identity)
                if identity in audit_contexts:
                    context_data = audit_contexts[identity]
                    origin = context_data["row"]
                    entity = document.get("entity_id")
                    if category == "agents" and "agent_id" in origin:
                        if origin["agent_id"] is not None:
                            expect(entity == str(origin["agent_id"]), f"{item_context}: audit belongs to another agent")
                        elif all(field in origin for field in ("scope", "family", "scene")):
                            expected = f"{origin['scope']}|{origin['family']}|{origin.get('event_tag') or ''}|{origin['scene']}"
                            expect(entity == expected, f"{item_context}: unknown interaction lost its source group")
                        if all(field in origin for field in ("scope", "family", "scene")):
                            expected = f"{origin['scope']}|{origin['family']}|{origin.get('event_tag') or ''}|{origin['scene']}"
                            expect(item.get("scene_id") == expected, f"{item_context}: interaction scene differs from its source group")
                    elif category == "street" and all(field in origin for field in ("family", "scene")):
                        expect(entity == f"{origin['family']}|{origin['scene']}",
                               f"{item_context}: street source belongs to another scene")
                        expect(item.get("scene_id") == origin["scene"], f"{item_context}: street scene differs from source")
                    elif category == "interknot":
                        if context_data["items"]:
                            expect(entity in context_data["items"], f"{item_context}: attachment belongs to another item")
                        elif context_data["threads"]:
                            expect(entity in context_data["threads"], f"{item_context}: message belongs to another thread")
            else:
                expect(False, f"{item_context}: unsupported item kind")
        profile = document.get("profile")
        if profile is not None:
            expect(category == "agents" and isinstance(profile, dict), f"{context}: invalid profile")
            if not isinstance(profile, dict):
                continue
            for fact in profile.get("facts", []):
                if not isinstance(fact, dict):
                    expect(False, f"{context}: fact must be an object")
                    continue
                item_index = fact.get("item_index")
                if item_index is None:
                    expect(isinstance(fact.get("source_ref"), dict) and bool(fact["source_ref"]),
                           f"{context}: configuration fact needs source_ref")
                else:
                    expect(type(item_index) is int and 0 <= item_index < len(items),
                           f"{context}: profile fact item_index is out of range")
                    if type(item_index) is int and 0 <= item_index < len(items):
                        item = items[item_index]
                        expect(isinstance(item, dict) and item.get("kind") == "source"
                               and fact.get("value") == item.get("text"),
                               f"{context}: profile fact differs from its source item")

    for filename, key in audit_index:
        counts = category_counts[filename.split("/", 1)[0]]
        counts["retained_audit_sources"] += 1
        if (filename, key) not in referenced:
            counts["unreferenced_audit_sources"] += 1
            expect(False, f"retained audit source is not referenced: {filename} / {key}")
    uncovered = sorted(path.relative_to(lore).as_posix() for path in lore.rglob("*.md")
                       if path.relative_to(lore).as_posix() not in covered)
    return {"ok": error_count == 0, "protagonist": protagonist, "categories": category_counts,
            "unique_source_fields": len(unique_sources), "covered_markdown_files": len(covered),
            "uncovered_legacy_markdown_files": uncovered, "error_count": error_count, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = check(args.output, args.data_dir)
    except (OSError, ValueError, StopIteration) as error:
        report = {"ok": False, "error_count": 1, "errors": [str(error) or "documents.jsonl is empty"]}
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
