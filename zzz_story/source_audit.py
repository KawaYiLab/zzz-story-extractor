"""Preserve auxiliary and empty source values without inventing utterances."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .clean import clean_text
from .keys import parse_key


def collect_source_variants(text_map, keys: Iterable[str] | None = None) -> list[dict]:
    """Audit known auxiliary layouts and compare both protagonist values.

    A matching base is text equivalence evidence only. It does not establish
    which key the runtime selects or whether either source is played.
    """
    result = []
    for key in sorted(text_map.keys() if keys is None else keys):
        parsed = parse_key(key)
        if parsed is None or parsed.kind != "source_variant":
            continue
        raw = text_map.get(key)
        base = key[:-len("_Gender")]
        base_raw = text_map.get(base) if base in text_map else None
        values = {side: clean_text(raw, side).text for side in ("M", "F")}
        base_values = ({side: clean_text(base_raw, side).text for side in ("M", "F")}
                       if base_raw is not None else None)
        if not raw:
            status = "empty_source"
        elif base_values is None:
            status = "base_missing"
        elif values == base_values:
            status = "equivalent_source_variant"
        else:
            status = "distinct_source_variant"
        result.append({
            "source_key": key, "record_kind": "source_variant",
            "chapter": parsed.chapter_token, "family": parsed.family,
            "scene": parsed.scene, "line_no": parsed.line_no, "sub_no": parsed.sub_no,
            "variant": parsed.variant, "raw_text": raw, "text_variants": values,
            "base_source_key": base, "base_raw_text": base_raw,
            "base_text_variants": base_values, "status": status,
            "playback_status": "unverified",
        })
    return result


def annotate_source_variants(records: list[dict], variants: list[dict]) -> None:
    """Attach source evidence to the base record without altering stable IDs."""
    by_key = {record["source_key"]: record for record in records}
    for variant in variants:
        base = by_key.get(variant["base_source_key"])
        if base is not None:
            base.setdefault("source_variants", []).append(variant)


def collect_empty_sources(
    text_map, english_map: Mapping[str, str], keys: Iterable[str] | None = None,
) -> list[dict]:
    """Record missing original text and whether a separate EN value exists."""
    result = []
    for key in sorted(text_map.keys() if keys is None else keys):
        parsed = parse_key(key)
        if parsed is None or parsed.kind != "line" or not key.startswith(("Main_", "MainChat_")):
            continue
        if text_map.get(key):
            continue
        english = english_map.get(key)
        result.append({
            "source_key": key, "record_kind": "empty_source",
            "chapter": parsed.chapter_token, "family": parsed.family,
            "scene": parsed.scene, "line_no": parsed.line_no, "sub_no": parsed.sub_no,
            "raw_text": text_map.get(key), "language": text_map.language,
            "status": "source_text_missing", "english_raw_text": english,
            "english_status": "available" if english else "empty" if english == "" else "absent",
            "playback_status": "unverified",
        })
    return result
