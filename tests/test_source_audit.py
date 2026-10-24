from zzz_story.source_audit import (
    annotate_source_variants,
    collect_empty_sources,
    collect_source_variants,
)
from zzz_story.textmap import TextMap

BASE = "Main_BubbleStory_Chapter170_417001009_01"


def test_gender_source_equivalence_preserves_raw_values_and_base_id():
    tm = TextMap({BASE: "{M#哲}{F#铃}", BASE + "_Gender": "{F#铃}{M#哲}"}, "CHS")
    variants = collect_source_variants(tm)
    assert len(variants) == 1
    assert variants[0]["status"] == "equivalent_source_variant"
    assert variants[0]["raw_text"] == tm.get(BASE + "_Gender")
    assert variants[0]["base_raw_text"] == tm.get(BASE)
    assert variants[0]["text_variants"] == {"M": "哲", "F": "铃"}
    records = [{"source_key": BASE, "line_id": "stable", "text": "哲"}]
    annotate_source_variants(records, variants)
    assert len(records) == 1 and records[0]["line_id"] == "stable"
    assert records[0]["source_variants"] == variants


def test_distinct_or_orphan_source_variants_are_retained_without_merging():
    tm = TextMap({BASE: "{M#哲}{F#铃}", BASE + "_Gender": "{M#哲}{F#不同回答}"}, "CHS")
    assert collect_source_variants(tm)[0]["status"] == "distinct_source_variant"
    orphan = TextMap({BASE + "_Gender": "独立候选"}, "CHS")
    rows = collect_source_variants(orphan)
    assert rows[0]["status"] == "base_missing" and rows[0]["base_raw_text"] is None
    assert rows[0]["raw_text"] == "独立候选"


def test_empty_source_audit_does_not_substitute_english_or_name_metadata():
    key = "Main_Chat_Chapter02_30200076_08"
    other = "Main_Chat_Chapter02_30200076_09"
    tm = TextMap({key: "", other: "", key + "_Name": "", BASE: "正文"}, "CHS")
    rows = collect_empty_sources(tm, {key: "English original"})
    assert len(rows) == 2
    assert rows[0]["raw_text"] == "" and rows[0]["english_status"] == "available"
    assert rows[1]["english_status"] == "absent"
    assert collect_empty_sources(tm, {}, keys=[key]) == [{**rows[0], "english_raw_text": None, "english_status": "absent"}]
