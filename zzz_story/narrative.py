"""Keep attribution gaps and local ordering evidence separate from chronology."""

import hashlib
from collections import Counter

# Reviewed source values, not keyword heuristics. A changed text must be
# reviewed again; an ordinary line mentioning Anby or "the protagonist" is
# not evidence of a placeholder. Resource fields alone do not prove playback.
_REVIEWED_OUTLINES = {
    "Main_GalGame_Chapter240_124000032_001": "b2e9619fba0ad5d8dba38c8500264bda94cac8f9d888c5b9d98ea64b91900e62",
    "Main_GalGame_Chapter240_124000032_002": "7d7882ce840ab9438426ec96a7674cf7847323067554360813866318c6515d06",
    "Main_GalGame_Chapter240_124000032_003": "7614d2d339ed8fc580e8ff80def6d5d9dd9ffbebd58eca3f5072f8f754a9e2cd",
    "Main_GalGame_Chapter240_124000033_001": "55419b264c4b3a54c85a5baaa10e9b87ea8ab52f68e22475d6c9821d3f2b903c",
    "Main_GalGame_Chapter240_124000034_001": "bbd18022035d68099fa4b781df9db92e0e43da146bb2e81ce6a990218591e80c",
}


def reviewed_outline(record: dict) -> bool:
    expected = _REVIEWED_OUTLINES.get(record.get("source_key"))
    raw = record.get("raw_text") if record.get("raw_text") is not None else record.get("text")
    return expected is not None and isinstance(raw, str) and hashlib.sha256(raw.encode("utf-8")).hexdigest() == expected


def annotate_content(records: list[dict]) -> None:
    """Separate reviewed scene outlines from actual speaker attribution.

    Keep the original name, voice linkage and text as evidence. This does
    not assert that the asset is unreachable or identify a replacement actor.
    """
    for record in records:
        if not reviewed_outline(record):
            continue
        record.setdefault("source_attribution", {
            field: record.get(field) for field in (
                "speaker", "speaker_id", "speaker_form", "speaker_alias",
                "speaker_source", "speaker_confidence", "scene_speakers", "line_type",
            )
        })
        record["content_status"] = "reviewed_placeholder"
        record["content_evidence"] = {
            "kind": "manual_source_review", "reason": "scene_outline_in_dialogue_node",
            "text_sha256": _REVIEWED_OUTLINES[record["source_key"]],
            "playback_status": "unverified",
        }
        record.update(speaker=None, speaker_id=None, speaker_form=None, speaker_alias=None,
                      speaker_source="none", speaker_confidence=0.0, scene_speakers=[],
                      line_type="placeholder", speaker_status="not_applicable",
                      speaker_gap_reason=None)


def annotate_attribution(records: list[dict]) -> None:
    for record in records:
        link = record.get("perform") or {}
        occurrences = link.get("occurrences") or []
        slots = sorted({item["speaker_slot"] for item in occurrences if item.get("speaker_slot")})
        record["speaker_slot"] = slots[0] if len(slots) == 1 else None
        # Narrator/screen nodes describe presentation even when the voice bank
        # is a composite cast. Do not turn them into missing-character errors.
        unnamed_display = occurrences and all(
            item.get("is_narration") or (
                item.get("hide_name") and not item.get("avatar")
                and not item.get("actor_id") and not item.get("voice_keys")
                and not any((item.get("speaker_binding") or {}).values())
            ) for item in occurrences
        )
        if not record.get("speaker") and record.get("line_type") != "option" and unnamed_display:
            record["line_type"] = "narration"
        if record.get("line_type") == "option":
            status, reason = "not_applicable", None
        elif record.get("speaker"):
            status = "inferred" if record.get("speaker_source") in {"scene_name", "scene_alias"} else "resolved"
            reason = None
        elif record.get("line_type") == "narration":
            status, reason = "not_applicable", None
        elif record.get("speaker_slot"):
            status, reason = "unresolved", "unbound_actor_slot"
        elif len(link.get("avatars", [])) > 1:
            status, reason = "unresolved", "conflicting_display_names"
        elif link.get("avatars"):
            status, reason = "unresolved", "display_name_unresolved"
        elif record.get("has_voice"):
            status, reason = "unresolved", "voice_alias_unresolved"
        elif occurrences:
            status, reason = "unresolved", "node_without_display_name"
        else:
            status, reason = "unresolved", "no_structured_reference"
        record["speaker_status"], record["speaker_gap_reason"] = status, reason


def annotate_local_order(records: list[dict]) -> None:
    """Use bubble timing only for fully covered, unambiguous single sections.

    Array position is source evidence, not execution order. Other scenes keep
    their existing catalog order until jump/choice execution is understood.
    """
    scenes = {}
    for record in records:
        record["line_order_source"] = "source_key"
        record["line_order_status"] = "unknown"
        scenes.setdefault((record["chapter"], record["family"], record["scene"]), []).append(record)
    for group in scenes.values():
        items = []
        for record in group:
            occurrences = (record.get("perform") or {}).get("occurrences", [])
            if len(occurrences) != 1:
                break
            item = occurrences[0]
            if item["node_type"] != "GalBubbleStoryNode" or not isinstance(item.get("start_time"), (int, float)):
                break
            items.append(item)
        if len(items) != len(group) or len({(item["asset"], item["section"]) for item in items}) != 1:
            continue
        for record, item in zip(group, items):
            record["line_order_source"] = "perform_time"
            record["line_order_status"] = "within_section"
            record["_local_order"] = (item["start_time"], item["node"])


def attribution_summary(records: list[dict]) -> dict:
    return {
        "by_status": dict(Counter(record.get("speaker_status", "unresolved") for record in records)),
        "unresolved_by_reason": dict(Counter(record["speaker_gap_reason"] for record in records if record.get("speaker_gap_reason"))),
        "unresolved_by_family": dict(Counter(record["family"] for record in records if record.get("speaker_status") == "unresolved")),
    }
