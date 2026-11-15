"""Source-keyed lore documents, collected while extraction still has TextMap keys.

The Markdown files are presentation outputs. This collector observes explicit
TextMap reads inside an entity scope and retains the original source fields;
it never reads, splits, or reconstructs Markdown. Audit rows remain in their
existing files and are referenced by key rather than copied into this catalog.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .clean import CleanedText, clean_text
from .textmap import TextMap
from .writers import write_jsonl

SCHEMA_VERSION = 1
SECTION_KINDS = frozenset({"introduction", "biography", "commentary", "trust", "daily", "bubble", "other"})


def selected_variant(cleaned: CleanedText, requested: str) -> str | None:
    variants = cleaned.variants or {}
    if not variants:
        return None
    if requested in variants:
        return requested
    return "M" if "M" in variants else "F"


def section_for_key(key: str) -> str:
    if "ProfileDesc" in key:
        return "biography"
    if "Impression" in key:
        return "commentary"
    if "_Talent_" in key:
        # Mindscape Cinema fields are dossier material, not trust invitations.
        return "other"
    if "OutlookDesc" in key or "Item_Avatar_" in key:
        return "introduction"
    return "other"


class Documents:
    def __init__(self, text_map: TextMap, protagonist: str):
        if protagonist not in {"M", "F"}:
            raise ValueError("protagonist must be M or F")
        self.text_map = text_map
        self.protagonist = protagonist
        self.documents: dict[str, dict[str, Any]] = {}
        self.current: dict[str, Any] | None = None
        self._item_keys: dict[str, set[tuple[str, str, str]]] = {}

    def begin(self, category: str, entity_id: str, title: str, source_file: str,
              *, section_kind: str = "other", doc_type: str = "entry") -> dict[str, Any]:
        self.end()
        doc_id = f"lore:{category}:{doc_type}:{entity_id}"
        doc = self.documents.setdefault(doc_id, {
            "schema_version": SCHEMA_VERSION, "record_type": "document", "doc_id": doc_id,
            "category": category, "title": title, "source_file": source_file,
            "entity_id": entity_id, "items": [],
        })
        self._item_keys.setdefault(doc_id, set())
        self.current = doc
        self._section_kind = section_kind
        return doc

    def end(self) -> None:
        self.current = None

    def discard(self) -> None:
        if self.current is not None:
            self.documents.pop(self.current["doc_id"], None)
            self._item_keys.pop(self.current["doc_id"], None)
        self.end()

    def source(self, key: str, *, field: str | None = None, section_kind: str | None = None,
               section_title: str | None = None) -> None:
        if self.current is None or key not in self.text_map:
            return
        raw = self.text_map.get(key)
        cleaned = clean_text(raw, self.protagonist)
        if not cleaned.text:
            return
        doc = self.current
        identity = ("source", "", key)
        if identity in self._item_keys[doc["doc_id"]]:
            return
        self._item_keys[doc["doc_id"]].add(identity)
        kind = section_kind or section_for_key(key)
        if kind == "other":
            kind = self._section_kind
        doc["items"].append({
            "kind": "source", "field": field or key, "source_key": key,
            "text": cleaned.text, "raw_text": raw if raw != cleaned.text else None,
            "text_variants": cleaned.variants,
            "selected_variant": selected_variant(cleaned, self.protagonist),
            "line_type": "text", "speaker": None, "speaker_status": "not_applicable",
            "section_kind": kind, "section_title": section_title or "",
        })

    def audit(self, doc: dict[str, Any], record_source: str, row: dict[str, Any],
              *, section_kind: str = "other", section_title: str = "",
              scene_id: str | None = None, scene_title: str | None = None) -> None:
        if row.get("retained") is False or not row.get("text"):
            return
        key = row["source_key"]
        identity = ("audit", record_source, key)
        if identity in self._item_keys[doc["doc_id"]]:
            return
        self._item_keys[doc["doc_id"]].add(identity)
        doc["items"].append({
            "kind": "audit", "field": "dialogue", "record_source": record_source,
            "source_key": key, "section_kind": section_kind, "section_title": section_title,
            "scene_id": scene_id, "scene_title": scene_title,
        })

    def profile(self, doc: dict[str, Any], *, faction: str, agent_id: str,
                config: dict[str, Any]) -> None:
        facts = [{"field": "agentId", "value": agent_id, "item_index": None,
                  "source_ref": {"file": "FileCfg/AvatarBaseTemplateTb.json", "field": "PFOAJKNPCHL", "id": agent_id}}]
        facts.append({"field": "faction", "value": faction, "item_index": None,
                      "source_ref": {"file": "FileCfg/AvatarBaseTemplateTb.json", "field": "OOOHMBMDLBI",
                                     "id": agent_id, "value": config.get("OOOHMBMDLBI"),
                                     "inputs": {"OOOHMBMDLBI": config.get("OOOHMBMDLBI"),
                                                "CJELJCPENOL": config.get("CJELJCPENOL")},
                                     "derivation": "CAMP_ID_MAP / CJELJCPENOL camp mapping"}})
        for label, token in [("birthday", "Partner_Birthday_"), ("height", "Partner_Stature_"), ("wEngine", "Item_Weapon_")]:
            for index, item in enumerate(doc["items"]):
                key = item.get("source_key", "")
                if item["kind"] == "source" and key.startswith(token) and (label != "wEngine" or key.endswith("_Name")):
                    facts.append({"field": label, "value": item["text"], "item_index": index})
                    break
        doc["profile"] = {"faction": faction, "facts": facts}

    def merge_sources(self, target: dict[str, Any], source_doc_id: str, *, section_kind: str,
                      scene_id: str | None = None) -> None:
        """Retain the extraction's explicit object relation without parsing its display."""
        source_doc = self.documents.pop(source_doc_id, None)
        if source_doc is None:
            return
        self._item_keys.pop(source_doc_id, None)
        for item in source_doc["items"]:
            identity = (item["kind"], item.get("record_source", ""), item["source_key"])
            if identity not in self._item_keys[target["doc_id"]]:
                self._item_keys[target["doc_id"]].add(identity)
                target["items"].append({**item, "section_kind": section_kind, "scene_id": scene_id})

    def write(self, lore_dir: Path) -> dict[str, int]:
        self.end()
        covered = sorted(p.relative_to(lore_dir).as_posix() for p in lore_dir.rglob("*.md"))
        docs = [doc for doc in self.documents.values() if doc["items"]]
        for doc in docs:
            if doc["source_file"] not in covered:
                raise ValueError(f"machine document refers to unrendered file: {doc['source_file']}")
            for item in doc["items"]:
                if item["section_kind"] not in SECTION_KINDS:
                    raise ValueError(f"unknown section kind: {item['section_kind']}")
        header = {"schema_version": SCHEMA_VERSION, "record_type": "manifest", "protagonist": self.protagonist,
                  "covered_source_files": covered}
        write_jsonl([header, *docs], lore_dir / "documents.jsonl")
        return {"lore_machine_documents": len(docs), "lore_machine_items": sum(len(d["items"]) for d in docs),
                "lore_machine_source_fields": sum(i["kind"] == "source" for d in docs for i in d["items"]),
                "lore_machine_audit_references": sum(i["kind"] == "audit" for d in docs for i in d["items"])}


class SourceTextMap:
    """Track source reads only within explicitly chosen extraction entities."""
    def __init__(self, text_map: TextMap, documents: Documents):
        self.source = text_map
        self.machine = documents
        self.language = text_map.language

    def get(self, key: str, default: str = "") -> str:
        self.machine.source(key)
        return self.source.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self.source

    def __len__(self) -> int:
        return len(self.source)

    def keys(self):
        return self.source.keys()

    def items(self):
        return self.source.items()


def begin(tm, category: str, entity_id: str, title: str, source_file: str, **kwargs) -> None:
    if machine := getattr(tm, "machine", None):
        machine.begin(category, entity_id, title, source_file, **kwargs)


def source(tm, key: str, **kwargs) -> None:
    if machine := getattr(tm, "machine", None):
        machine.source(key, **kwargs)


def describe(tm, title: str, *, source_file: str | None = None) -> None:
    if (machine := getattr(tm, "machine", None)) and machine.current is not None:
        machine.current["title"] = title
        if source_file is not None:
            machine.current["source_file"] = source_file


def end(tm) -> None:
    if machine := getattr(tm, "machine", None):
        machine.end()


def discard(tm) -> None:
    if machine := getattr(tm, "machine", None):
        machine.discard()
