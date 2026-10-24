"""Source-preserving street dialogue; identical text is not a playback identity."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

from .clean import clean_text
from .narrative import annotate_attribution, annotate_local_order
from .writers import _record_line, write_jsonl

STREET_DIALOGUE_PREFIXES = (
    "PasserBy_Chat_", "PasserBy_BubbleStory_", "PasserBy_Bubble_",
    "PasserBy_BubbleNpc_", "PasserByChat_", "PasserByBubble_",
    "BubbleByChat_", "StoreChat_", "StoreBubble_", "MainChat_StoreNPC_",
    # These source families were already covered by the legacy
    # ``"Bubble" in key and "PasserBy" in key`` rule. Keep their identities
    # separate even when scene numbers or dialogue text coincide.
    "Bubble_PasserBy_", "Activity_Bubble_PasserBy21Spring_",
    "Enclave_Bubble_PasserByWhitFiled_",
)
_NAME = re.compile(r"^(.*)_(?:Name|name)_?\d*[MF]?$")
_METADATA = re.compile(r"(?:^|_)(?:[A-Za-z]*Name|Nametag)(?:_?\d*[MF]?)?$", re.IGNORECASE)
_LINE = re.compile(r"^(.*)_(\d+)([MF]?)$")
_NON_SPEAKERS = {"选项", "玩家选项", "旁白", "玩家"}


def street_source(key: str) -> tuple[str, str, int, str | None] | None:
    prefix = next((p for p in STREET_DIALOGUE_PREFIXES if key.startswith(p)), None)
    if prefix is None:
        return None
    if _METADATA.search(key):
        return None
    match = _LINE.fullmatch(key[len(prefix):])
    if match is None:
        rest = key[len(prefix):]
        if rest.isdigit():
            return prefix.rstrip("_"), "source:" + rest, 0, None
        return None
    return prefix.rstrip("_"), match[1], int(match[2]), match[3] or None


def extract_street(text_map, directory: Path, *, speaker_index=None,
                   accuracy_first: bool = False) -> dict[str, int]:
    """Retain short lines, both source variants, and repeated distinct keys.

    Scene name tables are candidates, never per-line speaker bindings. Only
    mutually verified resource gender peers can move into removal audit.
    """
    directory.mkdir(parents=True, exist_ok=True)
    names = defaultdict(list)
    rows = []
    metadata = []
    for key, raw in text_map.items():
        prefix = next((p for p in STREET_DIALOGUE_PREFIXES if key.startswith(p)), None)
        if prefix is None:
            continue
        if _METADATA.search(key):
            metadata.append({"source_key": key, "raw_text": raw, "text": clean_text(raw).text,
                             "record_kind": "name_or_title_metadata"})
        name_match = _NAME.fullmatch(key[len(prefix):])
        if name_match:
            name = clean_text(raw).text
            if name and name not in _NON_SPEAKERS:
                names[(prefix.rstrip("_"), name_match[1])].append(name)
            continue
        parsed = street_source(key)
        if parsed is None:
            continue
        family, scene, line_no, variant = parsed
        cleaned = clean_text(raw, variant or "M")
        info = speaker_index.lookup(key) if speaker_index else None
        speaker = clean_text(info.speaker, variant or "M").text if info and info.speaker else None
        is_option = speaker in {"选项", "玩家选项"} or bool(speaker_index and speaker_index.is_option(key))
        if speaker in _NON_SPEAKERS:
            speaker = None
        row = {
            "source_key": key, "raw_text": raw, "text": cleaned.text,
            "text_variants": cleaned.variants, "family": family, "scene": scene,
            "chapter": "street", "line_no": line_no, "variant": variant,
            "speaker": speaker, "speaker_alias": info.alias if info else None,
            "speaker_source": info.source if info else "none",
            "speaker_confidence": info.confidence if info else 0.0,
            "has_voice": bool(info and info.has_voice),
            "line_type": "option" if is_option else ("dialogue" if speaker else "unknown"),
            "perform": info.perform if info else None,
            "timeline": info.timeline if info else None,
            "retained": bool(cleaned.text), "reason": None if cleaned.text else "empty_text",
            "paired_source_key": None, "chronology_status": "unknown",
        }
        rows.append(row)
    annotate_attribution(rows)
    annotate_local_order(rows)
    by_key = {row["source_key"]: row for row in rows}
    if not accuracy_first:
        for row in rows:
            link = row.get("perform") or {}
            peer = by_key.get(link.get("paired_key"))
            peer_link = (peer or {}).get("perform") or {}
            if (row["retained"] and link.get("explicit_gender") and link.get("sides") == ["F"]
                    and peer and peer["retained"] and peer_link.get("explicit_gender")
                    and peer_link.get("sides") == ["M"] and peer_link.get("paired_key") == row["source_key"]
                    and (peer["family"], peer["scene"]) == (row["family"], row["scene"])):
                row.update(retained=False, reason="perform_gender_route", paired_source_key=peer["source_key"])
    rows.sort(key=lambda r: (r["family"], r["scene"], r.get("_local_order", (r["line_no"],)), r["source_key"]))
    groups = defaultdict(list)
    for row in rows:
        row.pop("_local_order", None)
        row["scene_name_candidates"] = list(dict.fromkeys(names[(row["family"], row["scene"])]))
        if row["retained"]:
            groups[(row["family"], row["scene"])].append(row)
    write_jsonl(rows, directory / "dialogue-audit.jsonl")
    write_jsonl(metadata, directory / "metadata-audit.jsonl")
    lines = ["# 街头闲聊与环境气泡", "",
             "> 按来源场景整理；姓名表仅为候选。未核实的分支、角色与跨场景播放顺序保留未知标记。", ""]
    for (family, scene), group in groups.items():
        lines.extend([f"## {family} · {scene}", ""])
        candidates = group[0]["scene_name_candidates"]
        if candidates:
            lines.extend(["姓名表候选：" + "、".join(candidates), ""])
        for row in group:
            lines.append(f"{_record_line(row)} (`{row['source_key']}`)")
        lines.append("")
    (directory / "01_街区路人与市井闲聊.md").write_text("\n".join(lines), encoding="utf-8")
    return {
        "lore_street_lines": sum(row["retained"] for row in rows),
        "lore_street_candidates": len(rows),
        "lore_street_metadata": len(metadata),
        "lore_street_removed": sum(not row["retained"] for row in rows),
        "lore_street_speaker_lines": sum(row["retained"] and bool(row["speaker"]) for row in rows),
        "lore_street_unresolved": Counter(row["speaker_status"] for row in rows if row["retained"])["unresolved"],
    }
