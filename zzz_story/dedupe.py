"""Evidence-based route/copy filtering shared by all narrative domains."""

from __future__ import annotations


def same_scope(first: dict, second: dict) -> bool:
    return all(first.get(key) == second.get(key) for key in ("chapter", "scene", "family"))


def same_content(first: dict, second: dict) -> bool:
    """Do not merge options, responses, or distinct unselected variants."""
    return (first.get("text") == second.get("text")
            and first.get("line_type") == second.get("line_type")
            and first.get("text_variants") == second.get("text_variants"))


def shared_route(record: dict) -> bool:
    """A positively referenced common line is not a protagonist alternative."""
    return any(set(link.get("sides", [])) == {"M", "F"} and not link.get("copy_of")
               for link in (record.get("perform") or {}, record.get("timeline") or {}))


def _filter_timeline_copies(records: list[dict], *, copies: bool = True) -> tuple[list[dict], int]:
    """Filter only copies/routes verified by the ChatPlus timeline objects."""
    by_key = {record["source_key"]: record for record in records}
    male_by_scene: dict[tuple[str, str, str], list[dict]] = {}
    for record in records:
        link = record.get("timeline") or {}
        if "M" in link.get("sides", []) and not link.get("copy_of"):
            male_by_scene.setdefault((record["chapter"], record["scene"], record["family"]), []).append(record)
    drop: set[int] = set()
    for record in records:
        link = record.get("timeline") or {}
        copied = by_key.get(link.get("copy_of"))
        if copies and copied and copied is not record and same_scope(record, copied) and same_content(record, copied):
            _mark_discard(record, "timeline_unused_copy", copied)
            drop.add(id(record))
            continue
        if link.get("sides") != ["F"]:
            continue
        candidates = [candidate for candidate in male_by_scene.get(
            (record["chapter"], record["scene"], record["family"]), [])
            if (candidate.get("timeline") or {}).get("sides") == ["M"]]
        if not candidates:
            continue
        paired = min(candidates, key=lambda other: abs(other["line_no"] - record["line_no"]))
        _mark_discard(record, "timeline_gender_route", paired)
        drop.add(id(record))
    return [record for record in records if id(record) not in drop], len(drop)


def _filter_perform_routes(records: list[dict], *, copies: bool = True) -> tuple[list[dict], int]:
    """Remove only explicit, rejoining gender alternatives with a kept peer."""
    by_key = {record["source_key"]: record for record in records}
    drop = set()
    for record in records:
        link = record.get("perform") or {}
        copied = by_key.get(link.get("copy_of"))
        if (copies and copied and copied is not record and same_scope(record, copied) and same_content(record, copied)
                and (record.get("raw_text") or record["text"]) == (copied.get("raw_text") or copied["text"])):
            _mark_discard(record, "perform_unused_copy", copied)
            drop.add(id(record))
            continue
        if not link.get("explicit_gender") or link.get("sides") != ["F"]:
            continue
        paired = by_key.get(link.get("paired_key"))
        peer = paired.get("perform") or {} if paired else {}
        if not paired or not peer.get("explicit_gender") or peer.get("sides") != ["M"] or peer.get("paired_key") != record["source_key"]:
            continue
        if not same_scope(record, paired):
            continue
        _mark_discard(record, "perform_gender_route", paired)
        drop.add(id(record))
    return [record for record in records if id(record) not in drop], len(drop)


def _mark_discard(record: dict, reason: str, paired: dict, similarity: float | None = None) -> None:
    record["_discard_reason"] = reason
    record["_paired_source_key"] = paired.get("source_key")
    if similarity is not None:
        record["_discard_similarity"] = round(similarity, 4)


def _discarded_record(record: dict) -> dict:
    """Return the reviewable subset of a line removed by a heuristic."""
    return {
        "source_key": record.get("source_key"),
        "record_kind": "line",
        "chapter": record.get("chapter"),
        "scene": record.get("scene"),
        "family": record.get("family"),
        "line_no": record.get("line_no"),
        "sub_no": record.get("sub_no"),
        "variant": record.get("variant"),
        "speaker": record.get("speaker"),
        "speaker_alias": record.get("speaker_alias"),
        "text": record.get("text"),
        "raw_text": record.get("raw_text") or record.get("text"),
        "reason": record.get("_discard_reason"),
        "paired_source_key": record.get("_paired_source_key"),
        "similarity": record.get("_discard_similarity"),
        "line_type": record.get("line_type"),
        "text_variants": record.get("text_variants"),
        **({"domain": record["domain"]} if record.get("domain") else {}),
        **({"timeline": record["timeline"]} if record.get("timeline") else {}),
        **({"perform": record["perform"]} if record.get("perform") else {}),
    }


def resolve_discard_pairs(retained: list[dict], discarded: list[dict]) -> None:
    """Follow successive filters to a retained peer, preserving the original chain.

    Invalid/cyclic links remain visible for the structural validator to report.
    """
    kept = {row["source_key"] for row in retained}
    removed = {row["source_key"]: row for row in discarded if row.get("record_kind") != "name"}
    pairs = {key: row.get("paired_source_key") for key, row in removed.items()}
    for key, row in removed.items():
        peer = pairs[key]
        visited = {key}
        chain = []
        while peer not in kept and peer in pairs and peer not in visited:
            visited.add(peer)
            chain.append(peer)
            peer = pairs[peer]
        if chain and peer in kept:
            row["paired_source_key"] = peer
            row["paired_source_chain"] = chain + [peer]


