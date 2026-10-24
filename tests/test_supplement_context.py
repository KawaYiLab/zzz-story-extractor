import struct
from types import SimpleNamespace

import pytest

from zzz_story.perform_graph import asset_hash
from zzz_story.supplement_context import (
    _owned_markers,
    annotate_supplement_context,
    comic_bubbles_from_raw,
    comic_config_from_raw,
    comic_links_from_files,
)


def string(value):
    data = value.encode("utf-8")
    raw = struct.pack("<I", len(data)) + data
    return raw + bytes(-len(raw) % 4)


def marker(guid="a" * 32, display="妮可", time=3.5):
    reference = 456
    raw = bytes(28) + string("") + struct.pack("<dii", time, 0, 1)
    raw += string("EventTriggerMarkerInfo") + string("UnityEngine.Timeline") + string("Unity.Timeline")
    raw += struct.pack("<iq", 0, reference) + string("C00_01_01_02_10")
    raw += bytes(24)
    raw += string("BubbleEvent") + string("UnityEngine.Timeline") + string("Unity.Timeline")
    raw += struct.pack("<iqiii", 0, reference, 0, 0, 0) + string(guid)
    raw += struct.pack("<id", 4, 0) + bytes(56)
    raw += struct.pack("<7i", 6, 1, 0, 1, 0, 0, 1) + string(display)
    return raw + string("Terminus") + string("UnityEngine.DMAT") + string("FAKE_ASM")


def test_comic_marker_reads_same_event_uuid_speaker_and_time():
    rows = comic_bubbles_from_raw(marker())
    assert len(rows) == 1
    assert rows[0]["text_key"] == "Comic_" + "a" * 32
    assert rows[0]["display_name"] == "妮可"
    assert rows[0]["marker_time"] == 3.5
    assert rows[0]["marker_name"] == "C00_01_01_02_10"


def test_comic_marker_does_not_use_other_event_guid_or_truncated_footer():
    raw = marker().replace(b"BubbleEvent", b"OtherXEvent")
    assert comic_bubbles_from_raw(raw) == []
    assert comic_bubbles_from_raw(marker()[:-4]) == []
    assert comic_bubbles_from_raw(marker(guid="not-a-valid-guid")) == []
    with pytest.raises(ValueError, match="marker time"):
        comic_bubbles_from_raw(marker(time=float("nan")))


def test_animation_easing_after_empty_display_is_not_a_speaker():
    raw = marker(display="")
    footer = string("Terminus") + string("UnityEngine.DMAT") + string("FAKE_ASM")
    animation = string("TwoPointAnim") + string("MoleMole.Comic") + string("Unity.Timeline")
    animation += bytes(20) + string("QuadEaseOut")
    raw = raw[:-len(footer)] + animation + footer
    rows = comic_bubbles_from_raw(raw)
    assert len(rows) == 1 and rows[0]["display_name"] is None
    named = marker(display="妮可")
    named = named[:-len(footer)] + animation + footer
    assert comic_bubbles_from_raw(named)[0]["display_name"] == "妮可"


def test_comic_config_list_bounds_and_null_references():
    pointers = [(1, 999)] + [(0, 0)] * 10
    raw = bytes(28) + string("C00_01") + bytes(40)
    raw += b"".join(struct.pack("<iq", *pointer) for pointer in pointers)
    raw += string("Gen_1_3") + struct.pack("<II", 1, 1) + string("Play_Intro")
    assert comic_config_from_raw(raw) == ("C00_01", [(1, 999)])
    with pytest.raises(ValueError):
        comic_config_from_raw(raw[:-4])


def fake_object(path_id, kind, data, file):
    script_id = 1000 + path_id
    raw = bytearray(data)
    struct.pack_into("<q", raw, 20, script_id)
    file.objects[script_id] = SimpleNamespace(class_id=115, read=lambda: SimpleNamespace(m_ClassName=kind))
    obj = SimpleNamespace(class_id=114, path_id=path_id, assets_file=file, get_raw_data=lambda: bytes(raw))
    file.objects[path_id] = obj
    return obj


def track_header(parent, children=()):
    raw = bytes(28) + string("track") + bytes(40) + struct.pack("<iqI", 0, parent, len(children))
    return raw + b"".join(struct.pack("<iq", 0, pid) for pid in children)


def test_owned_markers_follow_track_parents_and_ignore_unowned_markers():
    file = SimpleNamespace(objects={})
    timeline_raw = bytes(28) + string("C00_01") + struct.pack("<IIiq", 0, 1, 0, 2)
    timeline = fake_object(1, "TimelineAsset", timeline_raw, file)
    track_raw = track_header(1) + struct.pack("<Iiqiq", 1, 0, 3, 0, 1)
    fake_object(2, "EventTriggerTrack", track_raw, file)
    owned = fake_object(3, "EventTriggerMarker", marker(), file)
    fake_object(4, "EventTriggerMarker", marker(guid="b" * 32), file)
    assert _owned_markers(timeline) == [owned]
    bad_raw = track_header(99) + struct.pack("<Iiqiq", 1, 0, 3, 0, 99)
    fake_object(2, "EventTriggerTrack", bad_raw, file)
    with pytest.raises(ValueError, match="parent"):
        _owned_markers(timeline)


def test_context_preserves_id_and_conflicting_display_names():
    rows = [{"source_key": "Comic_a", "family": "Comic", "line_id": "SUP_Comic_a", "scene": "a"},
            {"source_key": "Comic_b", "family": "Comic", "line_id": "SUP_Comic_b", "scene": "b"}]
    occurrence = {"comic": "C00_01", "asset": "asset", "timeline_path_id": 1,
                  "display_name": "妮可", "marker_time": 3.5}
    context = {"links": {"Comic_a": [occurrence],
                         "Comic_b": [occurrence, {**occurrence, "display_name": "比利"}]}}
    stats = annotate_supplement_context(rows, context)
    assert stats == {"comic_linked": 2, "comic_named": 1, "comic_conflicting_names": 1}
    assert rows[0]["speaker"] == "妮可" and rows[0]["line_id"] == "SUP_Comic_a"
    assert rows[0]["speaker_status"] == "resolved" and rows[0]["speaker_gap_reason"] is None
    assert rows[0]["scene"] == "a" and rows[0]["context_status"] == "resource_linked"
    assert "speaker" not in rows[1] and rows[1]["speaker_gap_reason"] == "conflicting_comic_display_names"


def test_reannotation_retracts_old_comic_name_when_evidence_conflicts_or_disappears():
    occurrence = {"comic": "C00_01", "asset": "asset", "timeline_path_id": 1,
                  "display_name": "妮可", "marker_time": 3.5}
    row = {"source_key": "Comic_a", "family": "Comic", "line_id": "SUP_Comic_a", "scene": "a"}
    annotate_supplement_context([row], {"links": {"Comic_a": [occurrence]}})
    assert row["speaker_status"] == "resolved" and row["speaker_gap_reason"] is None
    conflict = {"links": {"Comic_a": [occurrence, {**occurrence, "display_name": "比利"}]}}
    annotate_supplement_context([row], conflict)
    assert "speaker" not in row and "speaker_source" not in row
    assert row["speaker_status"] == "unresolved" and row["speaker_gap_reason"] == "conflicting_comic_display_names"
    annotate_supplement_context([row], {"links": {"Comic_a": [occurrence]}})
    assert row["speaker"] == "妮可" and row["speaker_gap_reason"] is None
    annotate_supplement_context([row], {"links": {}})
    assert "speaker" not in row and "speaker_source" not in row
    assert row["speaker_status"] == "unresolved" and row["speaker_gap_reason"] == "comic_reference_missing"
    assert row["context_status"] == "unlinked"
    assert all(field not in row for field in ("comic_context", "comic_scenes", "context_chronology_status"))
    assert row["line_id"] == "SUP_Comic_a" and row["scene"] == "a"


def test_reannotation_clears_name_if_current_node_has_no_display_name():
    row = {"source_key": "Comic_a", "family": "Comic", "speaker": "旧名字",
           "speaker_source": "comic_bubble", "speaker_status": "resolved", "speaker_confidence": 1.0}
    occurrence = {"comic": "C00_01", "asset": "asset", "timeline_path_id": 1, "display_name": None}
    annotate_supplement_context([row], {"links": {"Comic_a": [occurrence]}})
    assert "speaker" not in row and "speaker_confidence" not in row
    assert row["speaker_status"] == "unresolved" and row["speaker_gap_reason"] == "comic_display_name_missing"


def test_external_cab_identity_is_required_even_when_path_id_matches(monkeypatch):
    import UnityPy

    path = "Data/ScriptConfig/Comic/C00_01.asset"
    config_file = SimpleNamespace(objects={}, externals=[SimpleNamespace(path="archive:/CAB-correct/CAB-correct")])
    pointers = [(1, 10)] + [(0, 0)] * 10
    config_raw = bytes(28) + string("C00_01") + bytes(40)
    config_raw += b"".join(struct.pack("<iq", *pointer) for pointer in pointers)
    config_raw += string("") + struct.pack("<I", 0)
    fake_object(1, "ComicConfig", config_raw, config_file)
    bundle_value = SimpleNamespace(m_Container=[(asset_hash(path), SimpleNamespace(asset=SimpleNamespace(m_FileID=0, m_PathID=1)))],
                                   m_Dependencies=["10.bundle"])
    bundle = SimpleNamespace(class_id=142, assets_file=config_file, read=lambda: bundle_value)
    config_file.objects[100] = bundle
    target_file = SimpleNamespace(objects={}, assetbundle=SimpleNamespace(m_Name="10.bundle"))
    target = fake_object(10, "TimelineAsset", bytes(28) + string("C00_01"), target_file)
    marker_object = fake_object(30, "EventTriggerMarker", marker(), target_file)
    config_env = SimpleNamespace(files={"resource": config_file}, objects=list(config_file.objects.values()))
    target_env = SimpleNamespace(files={"resource": target_file}, objects=list(target_file.objects.values()))
    monkeypatch.setattr(UnityPy, "load", lambda raw: config_env if raw == b"ComicConfig" else target_env)
    monkeypatch.setattr("zzz_story.supplement_context._owned_markers", lambda timeline: [marker_object] if timeline is target else [])
    wrong, errors = comic_links_from_files([("CAB-config", b"ComicConfig"), ("CAB-wrong", b"TimelineAsset")], {path})
    assert not wrong and path in errors
    right, errors = comic_links_from_files([("CAB-config", b"ComicConfig"), ("CAB-correct", b"TimelineAsset")], {path})
    assert not errors and len(right) == 1
    assert next(iter(right.values()))[0]["pointer_resolution"] == "external_cab_name_and_path_id"
