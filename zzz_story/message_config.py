"""Resolve SMS source references and identities from version-bound config tables."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .clean import clean_text

MESSAGE_TABLES = (
    "FileCfg/MessageConfigTemplateTb.json",
    "FileCfg/MessageGroupConfigTemplateTb.json",
    "FileCfg/MessageNPCTemplateTb.json",
    "FileCfg/MessageItemConfigTemplateTb.json",
)

_TEXT_FIELDS = {
    "LDHNMACDKLH": "message",
    "FNOKFPDDECI": "option_1", "GGHOAADLHCF": "option_2",
    "NAPGHEGEOOC": "reply_1", "EEJNOOGPFND": "reply_2",
}


def _rows(payload):
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        values = payload.get("IAEFFFFLKNB", [])
        return [row for row in values if isinstance(row, dict)] if isinstance(values, list) else []
    return []


def message_metadata(config_payload, group_payload, npc_payload, item_payload, tm) -> dict:
    """Keep alternative identity fields and events instead of selecting a guess.

    IDs in both configured name slots must agree, be nonzero and resolve to
    one displayed name. The zero sentinel alone does not identify a player.
    Source references are exact keys, never digit-prefix inference.
    """
    names = defaultdict(list)
    for row in _rows(npc_payload):
        names[row.get("PFOAJKNPCHL")].append(row)

    def identities(ids):
        result = []
        for ident in sorted(set(ids)):
            for row in names.get(ident, []):
                name_key = row.get("HAKHHHCAENA")
                result.append({"id": ident, "name_key": name_key,
                               "name": clean_text(tm.get(name_key or "")).text or None})
        return result

    group_rows = defaultdict(list)
    for row in _rows(group_payload):
        group_rows[str(row.get("EGBBBFIINLO"))].append(row)
    contacts = {}
    for thread, values in group_rows.items():
        ids = [row.get("GJMPCHPFOMM", 0) for row in values]
        candidates = identities(ids)
        displays = {item["name"] for item in candidates}
        contacts[thread] = {"contact": next(iter(displays)) if len(set(ids)) == 1 and len(displays) == 1 and None not in displays else None,
                            "candidates": candidates, "group_rows": values}

    events = []
    by_source = defaultdict(list)
    for row in _rows(config_payload):
        sender_ids = [row.get(field, 0) for field in ("NMIFFJEFBJI", "HPKJODNLJOA")]
        candidates = identities(sender_ids)
        displays = {item["name"] for item in candidates}
        agreed = len(set(sender_ids)) == 1 and bool(sender_ids[0]) and len(displays) == 1 and None not in displays
        sender = next(iter(displays)) if agreed else None
        event = {
            "config_id": row.get("PFOAJKNPCHL"), "thread_id": str(row.get("EGBBBFIINLO")),
            "section": row.get("HBPLELJNAEA"), "sender": sender,
            "sender_status": "resolved" if sender else "unresolved",
            "sender_source": "message_config_identity" if sender else "none",
            "sender_candidates": candidates, "sender_ids": sender_ids,
            "config_row": row, "references": [], "chronology_status": "unknown",
        }
        for field, role in _TEXT_FIELDS.items():
            key = row.get(field)
            if not isinstance(key, str) or not key:
                continue
            raw = tm.get(key)
            # Some reply slots contain emoji paths. Preserve them as nontext
            # references, but never turn a path into a dialogue line.
            is_text = key in tm
            cleaned = clean_text(raw)
            ref = {"source_field": field, "source_key": key, "role": role,
                   "raw_text": raw if is_text else None,
                   "text": cleaned.text if is_text else None,
                   "text_variants": cleaned.variants if is_text else None,
                   "status": "text" if is_text and raw else "empty_text" if is_text else "nontext_or_missing"}
            event["references"].append(ref)
            if is_text:
                by_source[key].append({"config_id": event["config_id"], "thread_id": event["thread_id"],
                                       "section": event["section"], "source_field": field, "role": role,
                                       "sender": sender if role == "message" else None,
                                       "sender_ids": sender_ids if role == "message" else [],
                                       "sender_candidates": candidates if role == "message" else []})
        events.append(event)
    items = []
    for row in _rows(item_payload):
        refs = []
        for field in ("AJEGPOBMPCG", "DOPCCNPLNAF", "GOHLPPCCDPJ"):
            key = row.get(field)
            if isinstance(key, str) and key:
                raw = tm.get(key)
                ct = clean_text(raw)
                refs.append({"source_field": field, "source_key": key, "raw_text": raw,
                             "text": ct.text, "text_variants": ct.variants})
        items.append({"item_id": row.get("HJOEBMMFOMB"), "config_row": row, "references": refs})
    return {"by_source": dict(by_source), "contacts": contacts, "events": events, "items": items}


def load_message_metadata(data_paths: dict[str, Path] | None, tm) -> dict:
    if not data_paths or not all(data_paths.get(rel) and data_paths[rel].is_file() for rel in MESSAGE_TABLES):
        return {}
    payloads = [json.loads(data_paths[rel].read_text(encoding="utf-8")) for rel in MESSAGE_TABLES]
    return message_metadata(*payloads, tm)


def source_identity(metadata: dict, key: str) -> dict:
    values = metadata.get("by_source", {}).get(key, [])
    messages = [value for value in values if value["role"] == "message"]
    displays = {value["sender"] for value in messages}
    # A TextMap key can be reused as both a received message and a reply
    # choice. Its message occurrence's identity cannot label every use.
    sender = (next(iter(displays)) if messages and len(messages) == len(values)
              and len(displays) == 1 and None not in displays else None)
    threads = {value["thread_id"] for value in values}
    return {"sender": sender, "sender_status": "resolved" if sender else "unresolved",
            "sender_source": "message_config_identity" if sender else "none",
            "thread_id": next(iter(threads)) if len(threads) == 1 else None,
            "references": values}
