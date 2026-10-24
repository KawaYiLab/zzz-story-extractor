import json
from types import SimpleNamespace

import pytest
from test_perform_graph import list_node, node

from zzz_story.narrative import annotate_attribution
from zzz_story.odin import Entry, OdinError
from zzz_story.perform_graph import (
    asset_hash,
    graph_from_raw,
    graph_links,
    graphs_from_cab,
)
from zzz_story.speakers import (
    SpeakerInfo,
    build_speaker_index,
    ongoing_tips_speakers,
    ongoing_voice_names,
    resolve_ongoing_voice_names,
    structured_speaker,
)
from zzz_story.textmap import TextMap


def tips_file(tmp_path, rows):
    path = tmp_path / "tips.json"
    path.write_text(json.dumps({"IAEFFFFLKNB": rows}), encoding="utf-8")
    return {"FileCfg/OngoingTipsConfigTemplateTb.json": path}


def test_ongoing_tips_cover_partner_sources_and_reject_conflicts(tmp_path):
    key = "PartnerTalk_OngoingLevel_PartnerAnbi_1_01"
    rows = [{"FGAHJLHNEDB": key, "BLOGJEGIBOH": "Anby"},
            {"FGAHJLHNEDB": "missing", "BLOGJEGIBOH": "Anby"}]
    tm = TextMap({key: "台词", "Anby": "安比", "Billy": "比利"}, "CHS")
    assert ongoing_tips_speakers(tips_file(tmp_path, rows), tm, {}) == {key: ("安比", None)}
    rows.append({"FGAHJLHNEDB": key, "BLOGJEGIBOH": "Billy"})
    assert ongoing_tips_speakers(tips_file(tmp_path, rows), tm, {}) == {}


def test_exact_voice_names_keep_hidden_names_conflicts_and_text_differences(tmp_path):
    rows = [{"IDGNMKGGEGK": 1, "FGAHJLHNEDB": "ongoing", "BLOGJEGIBOH": "Captain",
             "PFOBGIIIICG": "OngoingLevel_Chapter140_LuciasFather_111101106_001"}]
    voice = rows[0]["PFOBGIIIICG"]
    tm = TextMap({"ongoing": "没关系，继续前进。", "bubble": "提高警惕，继续前进。",
                  "Captain": "警惕的队长", "Weakened": "虚弱的队长"}, "CHS")
    evidence = ongoing_voice_names(tips_file(tmp_path, rows), tm)
    link = {"avatars": [], "voice_keys": [voice], "occurrences": [{"voice_keys": [voice]}]}
    info = SpeakerInfo(None, "LuciasFather", 0, "perform", True, perform=link)
    assert resolve_ongoing_voice_names({"bubble": info}, evidence, tm) == 1
    assert info.speaker == "警惕的队长"
    assert info.perform["speaker_evidence"]["text_difference"] is True
    assert info.perform["speaker_evidence"]["references"][0]["name_key"] == "Captain"

    hidden = SpeakerInfo(None, "HiddenName", 0, "perform", True,
                         perform={**link, "avatars": ["HiddenName"]})
    mixed = SpeakerInfo(None, None, 0, "perform", True,
                        perform={**link, "occurrences": [{"voice_keys": [voice]}, {"voice_keys": []}]})
    assert resolve_ongoing_voice_names({"hidden": hidden, "mixed": mixed}, evidence, tm) == 0
    rows.append({**rows[0], "BLOGJEGIBOH": "Weakened"})
    assert ongoing_voice_names(tips_file(tmp_path, rows), tm) == {}


def test_tips_fallback_retains_occurrences_and_cannot_replace_hidden_display(tmp_path, monkeypatch):
    key = "PartnerTalk_OngoingLevel_PartnerAnbi_1_01"
    paths = tips_file(tmp_path, [{"FGAHJLHNEDB": key, "BLOGJEGIBOH": "Anby"}])
    avatar = tmp_path / "avatar.json"
    avatar.write_text("{}", encoding="utf-8")
    perform = tmp_path / "perform.json"
    perform.write_text("{}", encoding="utf-8")
    paths.update({"FileCfg/AvatarBaseTemplateTb.json": avatar, "FileCfg/PerformTemplateTb.json": perform,
                  "Data/_unsorted/VoiceData.json": avatar})
    link = {"avatars": [], "voice_keys": [], "occurrences": [{"speaker_slot": "A"}]}
    info = SpeakerInfo(None, None, 0, "perform", perform=link, timeline={"source": "timeline"})
    monkeypatch.setattr("zzz_story.speakers._perform_speakers", lambda *args: ({key: info}, set()))
    tm = TextMap({key: "台词", "Anby": "安比"}, "CHS")
    index, _ = build_speaker_index(text_map=tm, text_keys={key}, data_paths=paths, game_dir=tmp_path,
                                   cache_path=tmp_path / "cache.json")
    assert index.lookup(key).speaker == "安比"
    assert index.lookup(key).perform is link
    assert index.lookup(key).timeline == {"source": "timeline"}
    link["avatars"] = ["MissingHiddenName"]
    index, _ = build_speaker_index(text_map=tm, text_keys={key}, data_paths=paths, game_dir=tmp_path,
                                   cache_path=tmp_path / "cache.json")
    assert index.lookup(key).speaker is None


def test_nested_transition_dialogue_is_narration_and_keeps_parent_type(monkeypatch):
    cfg = node("TransitionWithActionsCfg", 0, 0, DialogueKey="screen", avatarId=0)
    transition = node("MainCityChatTransitionWithActionsNode", 0, 0, Cfg=cfg)
    monkeypatch.setattr("zzz_story.perform_graph.perform_entries", lambda _: (
        "fixture", [Entry("storySections", list_node([list_node([transition])]))]))
    graph = graph_from_raw(b"fixture")
    link = graph_links({"screen.asset": graph}, {})["screen"]
    item = link["occurrences"][0]
    assert item["node_type"] == "TransitionWithActionsCfg"
    assert item["parent_node_type"] == "MainCityChatTransitionWithActionsNode"
    assert link["is_narration"]
    info = structured_speaker(link, TextMap({}, "CHS"), {}, SpeakerInfo("错误角色", None, 1, "avatar"))
    assert info.speaker is None
    record = {"line_type": "unknown", "speaker": None, "perform": link}
    annotate_attribution([record])
    assert record["line_type"] == "narration"
    assert record["speaker_status"] == "not_applicable"


def test_unknown_config_dialogue_is_not_automatically_narration(monkeypatch):
    cfg = node("UnknownCfg", 0, 0, DialogueKey="text")
    parent = node("UnknownNode", 0, 0, Cfg=cfg)
    monkeypatch.setattr("zzz_story.perform_graph.perform_entries", lambda _: (
        "fixture", [Entry("storySections", list_node([list_node([parent])]))]))
    graph = graph_from_raw(b"fixture")
    assert not graph.occurrences["text"][0]["is_narration"]


def test_null_stub_and_sparse_nodes_keep_status_and_array_address(monkeypatch):
    monkeypatch.setattr("zzz_story.perform_graph.perform_entries", lambda _: ("stub", [Entry("storySections", None)]))
    graph = graph_from_raw(b"stub")
    assert graph.status == "empty" and not graph.keys
    bubble = node("GalBubbleStoryNode", 0, 2, Text="bubble", Speaker="A", StartTime=0, EndTime=3000)
    monkeypatch.setattr("zzz_story.perform_graph.perform_entries", lambda _: (
        "partial", [Entry("storySections", list_node([list_node([None, None, bubble, None])]))]))
    graph = graph_from_raw(b"partial")
    assert graph.status == "partial"
    assert graph.null_nodes == [(0, 0), (0, 1), (0, 3)]
    assert graph.keys == {"bubble"}
    assert graph.occurrences["bubble"][0]["node"] == 2


def test_bad_configured_asset_does_not_discard_other_assets_in_cab(monkeypatch):
    paths = ["good.asset", "bad.asset"]
    good = SimpleNamespace(class_id=114, path_id=1, get_raw_data=lambda: b"good")
    bad = SimpleNamespace(class_id=114, path_id=2, get_raw_data=lambda: b"bad")
    entries = [(asset_hash(path), SimpleNamespace(asset=SimpleNamespace(m_FileID=0, m_PathID=index + 1)))
               for index, path in enumerate(paths)]
    bundle = SimpleNamespace(class_id=142, path_id=3, read=lambda: SimpleNamespace(m_Container=entries))
    monkeypatch.setattr("UnityPy.load", lambda _: SimpleNamespace(objects=[bundle, good, bad]))
    def read(raw):
        if raw == b"bad":
            raise OdinError("invalid graph")
        return graph_from_raw(raw)
    monkeypatch.setattr("zzz_story.perform_graph.perform_entries", lambda _: (
        "good", [Entry("storySections", list_node([list_node([node("GalPlayStoryNode", 0, 0, dialogueKey="line")])]))]))
    monkeypatch.setattr("zzz_story.perform_graph.graph_from_raw", read)
    errors = {}
    graphs = graphs_from_cab(b"cab", {asset_hash(path): path for path in paths}, errors=errors)
    assert set(graphs) == {"good.asset"}
    assert errors == {"bad.asset": "invalid graph"}
    with pytest.raises(OdinError, match="invalid graph"):
        graphs_from_cab(b"cab", {asset_hash(path): path for path in paths})
