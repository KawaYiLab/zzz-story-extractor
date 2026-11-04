from zzz_story.dedupe import (
    _filter_perform_routes,
    _filter_timeline_copies,
    resolve_discard_pairs,
)


def row(key, **changes):
    return {"source_key": key, "chapter": "activity.Fest", "family": "Chat", "scene": "1",
            "text": "相同的台词", "line_type": "dialogue", "line_no": 1, **changes}


def test_copies_cannot_cross_scene_or_option_boundaries():
    peer = row("kept")
    for change in ({"scene": "2"}, {"line_type": "option"}, {"text_variants": {"F": "另一句话"}}, {"text": "不同"}):
        for field, filter_records in (("perform", _filter_perform_routes), ("timeline", _filter_timeline_copies)):
            candidate = row("copy", **change, **{field: {"copy_of": "kept"}})
            assert filter_records([peer, candidate])[1] == 0


def test_self_referential_copy_does_not_delete_its_only_record():
    candidate = row("only", perform={"copy_of": "only"})
    assert _filter_perform_routes([candidate])[1] == 0


def test_discard_chain_resolves_to_retained_source_and_keeps_evidence():
    removed = [{"source_key": "female", "paired_source_key": "copy"},
               {"source_key": "copy", "paired_source_key": "original"}]
    resolve_discard_pairs([row("original")], removed)
    assert removed[0]["paired_source_key"] == "original"
    assert removed[0]["paired_source_chain"] == ["copy", "original"]
    assert removed[1]["paired_source_key"] == "original"


def test_cyclic_discard_chain_does_not_invent_retained_evidence():
    removed = [{"source_key": "a", "paired_source_key": "b"},
               {"source_key": "b", "paired_source_key": "a"}]
    resolve_discard_pairs([], removed)
    assert removed[0]["paired_source_key"] == "b"
    assert "paired_source_chain" not in removed[0]
