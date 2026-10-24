import json

import pytest

from zzz_story.lore import _extract_agents, _extract_interknot
from zzz_story.partner_dialogue import parse_partner_dialogue
from zzz_story.speakers import SpeakerIndex, SpeakerInfo, SpeakerStats
from zzz_story.textmap import TextMap


@pytest.mark.parametrize("key,event,variant", [
    ("PartnerTalkChat_Chapter1000_0001_01", "0001", None),
    ("PartnerTalk_Chat_PartnerSeed_330460501_05_F", "330460501", "F"),
    ("PartnerTalk_Chat_PartnerAnbi_1205290704_Chat010_001", "1205290704_Chat010", None),
    ("PartnerTalkChat_Chapter1000_Niko2_2_NPC01", "Niko2_2", None),
    ("PartnerTalk_Chat_PartnerAstra_1205290704_Bubble01", "1205290704", None),
    ("PartnerTalk_GalGame_PartnerAnbi_1001_003_01", "1001", None),
])
def test_partner_event_identity(key, event, variant):
    parsed = parse_partner_dialogue(key)
    assert parsed is not None and parsed.event == event and parsed.variant == variant


@pytest.mark.parametrize("key", [
    "PartnerTalk_Chat_PartnerAnbi_1001_Name_01",
    "PartnerTalkChat_Name_01", "PartnerTalk_Chat_PartnerAnbi_1001_Nametag01",
    "PartnerTalk_Chat_PartnerAnbi_1001_Name01F", "Side_Chat_1001_01",
])
def test_names_and_other_scopes_are_not_partner_dialogue(key):
    assert parse_partner_dialogue(key) is None


def _avatar(aid, code="anbi", name="AvatarAnbi"):
    return {"PFOAJKNPCHL": aid, "HAKHHHCAENA": name,
            "FEKFJBFGANO": code, "OOOHMBMDLBI": 1}


def _rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_every_partner_layout_is_audited_without_guessing_agent_or_actor(tmp_path):
    keys = [
        "PartnerTalk_Bubble_PartnerAnbi_1001_01",
        "PartnerTalk_ChatAudio_PartnerAnbi_1001_01",
        "PartnerTalk_ChatPlus_PartnerAnbi_1001_01",
        "PartnerTalk_OngoingMainCity_PartnerAnbi_1001_01",
        "PartnerTalk_OngoingMainCityPartner_PartnerAnbi_1001_01",
        "PartnerTalk_OngoingLevel_PartnerAnbi_1001_01",
        "PartnerDate_Chat_PartnerAnbi_1001_01",
        "PartnerTalkChat_Partner1011_1001_01",
        "PartnerTalkBubble_Partner1011_1001_01",
        "PartnerTalkChat_Chapter1000_1001_01",
        "PartnerTalk_Bubble_330010001_01",
        "PartnerTalk_GalGame_PartnerUnregistered_1001_01",
    ]
    values = {key: "相同原文" for key in keys}
    values.update({"AvatarAnbi": "安比", "PartnerTalkChat_Chapter1000_1001_Name01": "安比"})
    stats = _extract_agents(TextMap(values, "CHS"), [_avatar(1011)], tmp_path)
    rows = _rows(tmp_path / "dialogue-audit.jsonl")
    assert {row["source_key"] for row in rows} == set(keys)
    assert stats["lore_dialogue_candidates"] == len(keys)
    assert all(row["retained"] and row["speaker"] is None for row in rows)
    assert len({(row["scope"], row["family"], row["event_id"], row["event_tag"]) for row in rows}) == len(keys)
    unresolved = _rows(tmp_path / "unassigned-dialogue.jsonl")
    assert {row["source_key"] for row in unresolved} == set(keys[-3:])
    assert all(row["agent_id"] == "1011" for row in rows if row not in unresolved)
    doc = (tmp_path / "13_未关联代理人互动.md").read_text(encoding="utf-8")
    assert all(row["source_key"] in doc for row in unresolved)


def test_same_name_skin_cannot_hide_entire_agent_dialogue(tmp_path):
    key = "PartnerTalk_GalGame_PartnerClaret_1001_01"
    values = {"AvatarClaret": "克拉蕾", key: "皮肤和基础代理人共享代号的互动"}
    avatar = [_avatar(1611, "claret", "AvatarClaret"), _avatar(2131, "claret", "AvatarClaret")]
    stats = _extract_agents(TextMap(values, "CHS"), avatar, tmp_path)
    row = _rows(tmp_path / "dialogue-audit.jsonl")[0]
    assert stats["lore_agents"] == 1 and row["agent_id"] == "1611"
    assert key in (tmp_path / "01_狡兔屋.md").read_text(encoding="utf-8")


def test_conflicting_agent_tags_do_not_assign_an_arbitrary_dossier(tmp_path):
    key = "PartnerTalk_Chat_PartnerShared_1001_01"
    values = {"AvatarA": "甲", "AvatarB": "乙", key: "未知归属的互动"}
    avatar = [_avatar(1011, "shared", "AvatarA"), _avatar(1021, "shared", "AvatarB")]
    _extract_agents(TextMap(values, "CHS"), avatar, tmp_path)
    row = _rows(tmp_path / "dialogue-audit.jsonl")[0]
    assert row["agent_id"] is None and row["context_status"] == "unresolved"
    assert key in (tmp_path / "13_未关联代理人互动.md").read_text(encoding="utf-8")


def test_gender_route_filter_uses_peers_within_the_same_source_stream(tmp_path):
    male = "PartnerTalk_Chat_PartnerAnbi_1001_01"
    female = "PartnerTalk_Chat_PartnerAnbi_1001_02_F"
    unrelated = "PartnerTalk_Bubble_PartnerAnbi_1001_01"
    values = {"AvatarAnbi": "安比", male: "男主路线", female: "女主路线", unrelated: "相同编号不同气泡"}
    infos = {
        male: SpeakerInfo("安比", None, .98, "perform", perform={"paired_key": female, "sides": ["M"], "explicit_gender": True}),
        female: SpeakerInfo("安比", None, .98, "perform", perform={"paired_key": male, "sides": ["F"], "explicit_gender": True}),
    }
    index = SpeakerIndex(infos, SpeakerStats())
    for accuracy in (False, True):
        output = tmp_path / str(accuracy)
        _extract_agents(TextMap(values, "CHS"), [_avatar(1011)], output,
                        speaker_index=index, accuracy_first=accuracy)
        rows = {row["source_key"]: row for row in _rows(output / "dialogue-audit.jsonl")}
        assert rows[male]["retained"] and rows[unrelated]["retained"]
        assert rows[female]["retained"] == accuracy
        assert rows[female]["raw_text"] == values[female]


def test_sms_gender_substitution_does_not_identify_sender(tmp_path):
    values = {"Message_400101_01": "{M#哲，今天来买汉堡吗？}{F#铃，今天来买汉堡吗？}",
              "Message_400101_02": "我会稍后过来。", "Message_400101_03": "[回复]好，马上来。"}
    stats = _extract_interknot(TextMap(values, "CHS"), tmp_path)
    rows = {row["source_key"]: row for row in _rows(tmp_path / "message-audit.jsonl")}
    assert stats["lore_messages"] == 3
    assert rows["Message_400101_01"]["sender"] is None
    assert rows["Message_400101_02"]["sender"] is None
    assert rows["Message_400101_03"]["sender_source"] == "explicit_reply_marker"
    assert rows["Message_400101_01"]["raw_text"] == values["Message_400101_01"]
    doc = (tmp_path / "02_绳网私信与手机短信.md").read_text(encoding="utf-8")
    assert "[01] 发送方未关联" in doc
    assert "男主路线：「哲，今天来买汉堡吗？」" in doc
    assert "[01] 法厄同" not in doc


def test_partner_typed_narration_and_options_do_not_become_speaker_gaps(tmp_path):
    narrator = "PartnerTalk_Chat_PartnerAnbi_1001_01"
    option = "PartnerTalk_Chat_PartnerAnbi_1001_02"
    values = {"AvatarAnbi": "安比", narrator: "画面渐渐暗下。", option: "继续等待"}
    link = {"avatars": [], "occurrences": [{"is_narration": True}]}
    infos = {narrator: SpeakerInfo(None, None, 0, "perform", perform=link),
             option: SpeakerInfo("哲", None, .98, "perform")}
    index = SpeakerIndex(infos, SpeakerStats(), {option})
    _extract_agents(TextMap(values, "CHS"), [_avatar(1011)], tmp_path, speaker_index=index)
    rows = {row["source_key"]: row for row in _rows(tmp_path / "dialogue-audit.jsonl")}
    assert rows[narrator]["line_type"] == "narration"
    assert rows[narrator]["speaker_status"] == "not_applicable"
    assert rows[option]["line_type"] == "option" and rows[option]["speaker"] is None
    doc = (tmp_path / "01_狡兔屋.md").read_text(encoding="utf-8")
    assert "> 选项：继续等待" in doc
    assert "（未标注）画面渐渐暗下。" not in doc


@pytest.mark.parametrize("display,line_type,status", [
    ("选项", "option", "not_applicable"),
    ("玩家选项", "option", "not_applicable"),
    ("旁白", "narration", "not_applicable"),
    ("玩家", "unknown", "unresolved"),
])
def test_partner_display_role_is_not_a_character(tmp_path, display, line_type, status):
    key = "PartnerTalk_Chat_330261401_07"
    text = "继续等一会儿。"
    index = SpeakerIndex({key: SpeakerInfo(display, None, .98, "perform")}, SpeakerStats())
    _extract_agents(TextMap({key: text}, "CHS"), [], tmp_path, speaker_index=index)
    row = _rows(tmp_path / "dialogue-audit.jsonl")[0]
    assert row["speaker"] is None and row["line_type"] == line_type
    assert row["source_display_role"] == display and row["speaker_status"] == status
    assert row["retained"] and row["raw_text"] == text
