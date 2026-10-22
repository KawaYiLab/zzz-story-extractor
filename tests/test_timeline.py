import csv
import json
import struct
from types import SimpleNamespace

import pytest

from zzz_story.extract import _filter_timeline_copies, _write_csv, extract
from zzz_story.fetch import REQUIRED_FILES
from zzz_story.speakers import SpeakerIndex, SpeakerInfo, SpeakerStats
from zzz_story.textmap import TextMap
from zzz_story.timeline import (
    TimelineClip,
    clip_from_raw,
    clips_from_cab,
    link_main_copies,
    timeline_asset_paths,
)


def unity_string(value):
    raw = value.encode("utf-8")
    result = struct.pack("<I", len(raw)) + raw
    return result + b"\0" * (-len(result) % 4)


def clip_raw(name="ChatPlusDialogClip", script=123):
    return (b"\0" * 12 + struct.pack("<iiq", 1, 0, script) + unity_string(name)
            + unity_string("Avatar_Male_Size01_Wise")
            + unity_string("TL_C30_ChatPlus_03_63")
            + unity_string("ChatPlusTimeline_Chapter210_Wise_1721000030_019"))


@pytest.mark.parametrize("name", ["ChatPlusDialogClip", "ChatPlusDialogClip(Clone)(Clone)"])
def test_unity_clip_strings_include_clones(name):
    clip = clip_from_raw(clip_raw(name))
    assert clip.text_key == "TL_C30_ChatPlus_03_63"
    assert clip.avatar == "Avatar_Male_Size01_Wise"
    assert clip_from_raw(clip_raw(name)[:-3]) is None


def test_cab_requires_script_identity_and_keeps_timeline_name(monkeypatch):
    objects = [
        SimpleNamespace(class_id=115, path_id=123, read=lambda: SimpleNamespace(m_ClassName="ChatPlusDialogClip")),
        SimpleNamespace(class_id=115, path_id=124, read=lambda: SimpleNamespace(m_ClassName="TimelineAsset")),
        SimpleNamespace(class_id=114, get_raw_data=lambda: clip_raw("ChatPlusDialogClip(Clone)")),
        SimpleNamespace(class_id=114, get_raw_data=lambda: clip_raw(script=999)),
        SimpleNamespace(class_id=114, get_raw_data=lambda: b"\0" * 12 + struct.pack("<iiq", 1, 0, 124)
                        + unity_string("TL_C30_ChatPlus_03B_Timeline")),
    ]
    monkeypatch.setattr("UnityPy.load", lambda _: SimpleNamespace(objects=objects))
    clips = clips_from_cab(b"fixture")
    assert len(clips) == 1
    assert clips[0].timeline == "TL_C30_ChatPlus_03B"


def timeline_fixture():
    prefix = "Main_GalGame_Chapter210_1721000030_"
    values = {prefix + f"{n:03}": f"line-{(n + 1) // 2}" for n in range(1, 84)}
    copies = (16, 20, 24, 26, 28, 30, 32, 39, 43, 45, 47, 51)
    for n in copies:
        values[prefix + f"{n:03}"] = values[prefix + f"{n - 1:03}"]
    clips = []
    for n in range(1, 84):
        text_key = f"TL_C30_ChatPlus_03_{n:02}"
        values[text_key] = values[prefix + f"{n:03}"]
        # A shared NPC clip is used in both timelines, followed by an unused
        # identical main-text copy. The common Billy line has no duplicate.
        if n in copies:
            continue
        sides = "MF" if n in (15, 19, 23, 25, 27, 29, 31, 37, 38, 42, 44, 46, 50) else ("F" if n % 2 else "M")
        if n >= 48 and n != 50:
            sides = "M" if n % 2 else "F"
        for side in sides:
            alias = "Wise" if side == "M" else "Belle"
            clips.append(TimelineClip("Name_NPC", text_key,
                         f"ChatPlusTimeline_Chapter210_{alias}_1721000030_{n:03}",
                         "TL_C30_ChatPlus_03" + ("B" if side == "M" else "G")))
    perform = {"IAEFFFFLKNB": [{"PFOAJKNPCHL": 1721000030,
               "BCKKFAEFDPP": "TL_C30_ChatPlus_03B", "LGJCAHIEBBK": "TL_C30_ChatPlus_03G"}]}
    return prefix, TextMap(values, "CHS"), clips, perform


def test_numbered_copies_are_backed_by_routes_not_speaker_or_text_guessing():
    prefix, text_map, clips, perform = timeline_fixture()
    links = link_main_copies(clips, text_map, perform)
    assert len(links) == 83
    assert links[prefix + "015"]["sides"] == ["F", "M"]
    assert links[prefix + "016"]["copy_of"] == prefix + "015"
    assert links[prefix + "037"]["sides"] == ["F", "M"]
    # Explicit routing does not require identical wording in the two branches.
    text_map._mapping[prefix + "078"] = text_map._mapping["TL_C30_ChatPlus_03_78"] = "my brother"
    text_map._mapping[prefix + "079"] = text_map._mapping["TL_C30_ChatPlus_03_79"] = "my sister"
    links = link_main_copies(clips, text_map, perform)
    records = [{"source_key": prefix + f"{n:03}", "chapter": "Chapter210", "scene": "1721000030",
                "family": "GalGame", "line_no": n, "text": text_map.get(prefix + f"{n:03}"),
                "speaker": None, "timeline": links[prefix + f"{n:03}"]} for n in range(1, 84)]
    # Unlinked identical NPC pauses are real candidates, not generic duplicates.
    records += [{**records[0], "source_key": "pause-a", "timeline": {}, "text": "..."},
                {**records[0], "source_key": "pause-b", "timeline": {}, "text": "..."}]
    kept, dropped = _filter_timeline_copies(records)
    keys = {row["source_key"] for row in kept}
    assert prefix + "078" not in keys and prefix + "079" in keys
    assert prefix + "037" in keys
    assert {"pause-a", "pause-b"} <= keys
    assert dropped == 41
    assert all(row.get("_discard_reason") in {"timeline_gender_route", "timeline_unused_copy"}
               for row in records if row["source_key"] not in keys)


def test_namespace_alignment_and_config_routes_are_required():
    prefix, text_map, clips, perform = timeline_fixture()
    assert not link_main_copies(clips, text_map, {})
    assert not link_main_copies([c for c in clips if c.timeline.endswith("B")], text_map, perform)
    for n in range(1, 20):
        text_map._mapping[prefix + f"{n:03}"] = "unrelated text"
    assert not link_main_copies(clips, text_map, perform)


def test_csv_preserves_timeline_metadata(tmp_path):
    path = tmp_path / "story.csv"
    metadata = {"text_key": "TL_fixture_01", "sides": ["M"], "voice_keys": ["voice"]}
    _write_csv([{"text_variants": None, "scene_speakers": [], "timeline": metadata}], path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert json.loads(row["timeline"]) == metadata


def test_asset_paths_use_configured_prefabs_only():
    _, _, _, perform = timeline_fixture()
    path = "Assets/NapResources/CutScene_Runtime/ChatPlusTimeline/3.0/TL_C30_ChatPlus_03B/TL_C30_ChatPlus_03B.prefab"
    cab = ("MoleMole.ChatPlusTimelineData\0" + path + "\0" + path.replace("03B", "99B")).encode("utf-16le")
    assert timeline_asset_paths(perform, [cab]) == {path[len("Assets/NapResources/"):]}


def test_extract_timeline_routes_with_full_audit_and_csv(tmp_path, monkeypatch):
    prefix, text_map, clips, perform = timeline_fixture()
    links = link_main_copies(clips, text_map, perform)
    data = tmp_path / "data"
    for rel in REQUIRED_FILES:
        path = data / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = text_map._mapping if rel == "TextMap/TextMapTemplateTb.json" else {}
        path.write_text(json.dumps(payload), encoding="utf-8")
    infos = {key: SpeakerInfo("NPC", None, 0.95, "timeline", True, link) for key, link in links.items()}
    monkeypatch.setattr("zzz_story.extract.build_speaker_index",
                        lambda **kwargs: (SpeakerIndex(infos, SpeakerStats()), SpeakerStats()))
    outputs = []
    for accurate in (False, True):
        out = tmp_path / ("audit" if accurate else "default")
        extract(out_dir=out, data_dir=data, game_dir=tmp_path / "nogame", formats="jsonl,txt,csv",
                include_lore=False, include_supplement=False, accuracy_first=accurate)
        outputs.append(out)
    def read(path):
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    kept = read(outputs[0] / "story.jsonl")
    candidates = read(outputs[1] / "story.jsonl")
    discarded = read(outputs[0] / "discarded.jsonl")
    assert len(kept) == 42 and len(candidates) == 83 and len(discarded) == 41
    originals = {row["source_key"]: row for row in candidates}
    assert all(row["line_id"] == originals[row["source_key"]]["line_id"] for row in kept)
    assert {row["source_key"] for row in kept + discarded} == set(originals)
    assert all(row["timeline"] for row in kept + discarded)
    assert all(row["raw_text"] == originals[row["source_key"]]["raw_text"] for row in discarded)
    assert not read(outputs[1] / "discarded.jsonl")
