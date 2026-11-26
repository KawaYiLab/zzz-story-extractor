import gzip
import json

import pytest

from zzz_story.cli import main
from zzz_story.extract import extract
from zzz_story.extras import extract_extras
from zzz_story.fetch import REQUIRED_FILES
from zzz_story.speakers import SpeakerIndex, SpeakerInfo, SpeakerStats
from zzz_story.textmap import TextMap


def test_one_click_contains_both_protagonists(tmp_path, monkeypatch):
    prefix = "Main_GalGame_Chapter00_10000002_"
    choice = "GalGame_Chapter01_24_09_Option1_02"
    side = "SideChat_Chapter03_0002"
    inline = "{M#哲}{F#铃}"
    values = {
        "GalNPCWise": "哲", "GalNPCBelle": "铃",
        prefix + "01": inline, prefix + "02": "哲的回答", prefix + "02F": "铃的回答",
        prefix + "Name01": "妹妹", prefix + "Name01F": "哥哥",
        prefix + "04": "共用台词", prefix + "03M": "单独的来源", prefix + "03F": "<b></b>",
        choice + "F_Main": "女主回答", choice + "_Main": inline,
        "MainChat_Chapter00_0059_01": "男主场景", "MainChat_Chapter00_0059F_01": "女主场景",
        side + "_01": "男主支线", side + "F_01": "女主支线",
        side + "_00": "男主场景名", side + "F_00": "女主场景名",
        "CS_00_01_010": inline, "Intro_1": inline + "和同伴一起出门。",
        "Message_400101_01": inline + "，你收到消息了吗？",
    }
    tables = {
        "TextMap/TextMapTemplateTb.json": values,
        "FileCfg/PerformTemplateTb.json": {"IAEFFFFLKNB": [
            {"BCKKFAEFDPP": "Data/GalGame/Chapter00/Main_GalGame_Chapter00_10000002.asset",
             "BCGIEODKGDG": "Intro_1"}]},
        "FileCfg/OngoingTipsConfigTemplateTb.json": {"IAEFFFFLKNB": [
            {"FGAHJLHNEDB": prefix + "01", "CIBKAFBOGCI": "OngoingLevel_Chapter00_Wise_1_01",
             "PFOBGIIIICG": "OngoingLevel_Chapter00_Belle_1_01"}]},
    }
    data = tmp_path / "data"
    for rel in REQUIRED_FILES:
        path = data / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(tables.get(rel, {})), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("zzz_story.cli.extract",
                        lambda *, out_dir: extract(out_dir=out_dir, data_dir=data, game_dir=tmp_path / "no-game"))
    assert main([]) == 0
    bundle_path = tmp_path / "out/story-corpus.json.gz"
    with gzip.open(bundle_path, "rt", encoding="utf-8") as handle:
        bundle = json.load(handle)
    assert set(bundle) == {"format", "manifest", "story", "extra", "supplement", "lore"}
    assert bundle["format"] == 1 and bundle["manifest"]["protagonist"] == "mixed"
    assert bundle["manifest"]["accuracy_first"] is True
    assert bundle["manifest"]["validation"]["errors"] == 0
    def lines(member):
        return [json.loads(line) for line in bundle[member].splitlines()]
    story = lines("story")
    both = [row for row in story if row["source_key"] == prefix + "01"]
    assert [(row["text"], row["speaker"], row["selected_variant"]) for row in both] == [
        ("哲", "哲", "M"), ("铃", "铃", "F")]
    assert all(row["scene_speakers"] == ["妹妹", "哥哥"] for row in both)
    assert all("哲和同伴一起出门。" in row["scene_intro"] and "铃和同伴一起出门。" in row["scene_intro"] for row in both)
    assert both[1]["line_id"] == both[0]["line_id"] + ":F"
    keys = [row["source_key"] for row in story]
    assert keys.count(prefix + "04") == 1 and prefix + "03M" in keys and prefix + "03F" not in keys
    assert {prefix + "02", prefix + "02F", choice + "_Main", choice + "F_Main"} <= set(keys)
    assert any(row["line_id"] == "CH00_MainChat_0059F_0001" for row in story)
    assert {row["text"] for row in lines("extra")} == {"男主支线", "女主支线"}
    assert [row["text"] for row in lines("supplement")] == ["哲", "铃"]
    messages = list(map(json.loads, bundle["lore"]["interknot/message-audit.jsonl"].splitlines()))
    assert messages[0]["text_variants"] == {"M": "哲，你收到消息了吗？", "F": "铃，你收到消息了吗？"}
    assert list(bundle_path.parent.iterdir()) == [bundle_path]


def test_opposed_resource_routes_override_suffix_and_shared_sources_keep_both_readings():
    key = "ActivityChat_BangbooActivity_0100_08"
    shared = "ActivityChat_BangbooActivity_0100_10"
    values = {k: "{M#哲}{F#铃}" for k in (key, key + "F", shared, shared + "F")}
    index = SpeakerIndex({k: SpeakerInfo("店员", None, 1, "perform", perform={"sides": sides})
                          for k, sides in ((key, ["F"]), (key + "F", ["M"]),
                                           (shared, ["F", "M"]), (shared + "F", ["F"]))}, SpeakerStats())
    rows, _ = extract_extras(TextMap(values, "CHS"), speaker_index=index)
    assert [(r["source_key"], r["text"]) for r in rows] == [
        (key, "铃"), (key + "F", "哲"), (shared, "哲"), (shared, "铃"), (shared + "F", "铃")]


def test_rerun_only_replaces_bundle_after_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def fixture(*, out_dir):
        (out_dir / "story.jsonl").write_text('{"text":"第一版"}\n', encoding="utf-8")
        (out_dir / "manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("zzz_story.cli.extract", fixture)
    assert main([]) == 0
    final = tmp_path / "out/story-corpus.json.gz"
    first = final.read_bytes()
    def fail(corpus, destination):
        destination.write_bytes(b"partial")
        raise OSError("disk full")
    with monkeypatch.context() as patch:
        patch.setattr("zzz_story.cli.write_bundle", fail)
        assert main([]) == 1
    assert final.read_bytes() == first
    def replacement(*, out_dir):
        fixture(out_dir=out_dir)
        (out_dir / "story.jsonl").write_text('{"text":"第二版"}\n', encoding="utf-8")
    monkeypatch.setattr("zzz_story.cli.extract", replacement)
    assert main([]) == 0
    assert "第二版" in json.loads(gzip.decompress(final.read_bytes()))["story"]
    assert list(final.parent.iterdir()) == [final]


@pytest.mark.parametrize("args", [["--protagonist", "F"], ["--only-chapter", "01"]])
def test_removed_commands_cannot_start_an_extraction(args, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match="2"):
        main(args)
    assert not (tmp_path / "out").exists()
