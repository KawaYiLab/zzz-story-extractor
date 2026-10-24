import json

import pytest

from zzz_story.lore import _extract_interknot
from zzz_story.message_config import message_metadata, source_identity
from zzz_story.textmap import TextMap


def _config(key, first=10001, second=10001, ident=100301, thread=1003, **extra):
    return {"PFOAJKNPCHL": ident, "EGBBBFIINLO": thread, "LDHNMACDKLH": key,
            "NMIFFJEFBJI": first, "HPKJODNLJOA": second, "HBPLELJNAEA": 1, **extra}


def test_exact_source_sender_and_contact_do_not_depend_on_text_or_id_prefix():
    tm = TextMap({"Message_Unexpected_01": "{M#哥哥}{F#妹妹}，下午好", "Npc": "安比", "Group": "团购群"}, "CHS")
    metadata = message_metadata([_config("Message_Unexpected_01")],
                                [{"EGBBBFIINLO": 1003, "GJMPCHPFOMM": 20001}],
                                [{"PFOAJKNPCHL": 10001, "HAKHHHCAENA": "Npc"},
                                 {"PFOAJKNPCHL": 20001, "HAKHHHCAENA": "Group"}], [], tm)
    identity = source_identity(metadata, "Message_Unexpected_01")
    assert identity["sender"] == "安比" and identity["thread_id"] == "1003"
    assert metadata["contacts"]["1003"]["contact"] == "团购群"


def test_zero_conflicting_or_missing_sender_ids_remain_unresolved():
    tm = TextMap({"a": "甲", "b": "乙", "Message_1": "台词", "Message_2": "台词", "Message_3": "台词"}, "CHS")
    metadata = message_metadata([_config("Message_1", 0, 0), _config("Message_2", 1, 2), _config("Message_3", 3, 3)], [],
                                [{"PFOAJKNPCHL": 1, "HAKHHHCAENA": "a"}, {"PFOAJKNPCHL": 2, "HAKHHHCAENA": "b"}], [], tm)
    assert all(source_identity(metadata, key)["sender"] is None for key in ["Message_1", "Message_2", "Message_3"])
    assert [item["name"] for item in metadata["events"][1]["sender_candidates"]] == ["甲", "乙"]


def test_reused_source_with_conflicting_occurrences_does_not_pick_one_sender():
    tm = TextMap({"a": "甲", "b": "乙", "Message_1": "重复文本"}, "CHS")
    metadata = message_metadata([_config("Message_1", 1, 1), _config("Message_1", 2, 2, thread=1004)], [],
                                [{"PFOAJKNPCHL": 1, "HAKHHHCAENA": "a"}, {"PFOAJKNPCHL": 2, "HAKHHHCAENA": "b"}], [], tm)
    identity = source_identity(metadata, "Message_1")
    assert identity["sender"] is None and identity["thread_id"] is None
    assert len(identity["references"]) == 2


@pytest.mark.parametrize("key,text,name,sender_id,message_id,choice_id,message_thread,choice_thread", [
    ("Message_1010212", "报酬五五分的那个", "猫又", 10005, 1010212, 302001201, 10102, 3020012),
    ("Message_20011308", "我就知道你也这么想！", "妮可", 10006, 20011307, 20011306, 200113, 200113),
])
def test_message_source_reused_as_choice_preserves_occurrence_identity(
    key, text, name, sender_id, message_id, choice_id, message_thread, choice_thread, tmp_path,
):
    tm = TextMap({key: text, "Name": name}, "CHS")
    metadata = message_metadata(
        [_config(key, sender_id, sender_id, ident=message_id, thread=message_thread),
         _config("", 0, 0, ident=choice_id, thread=choice_thread, GGHOAADLHCF=key)], [],
        [{"PFOAJKNPCHL": sender_id, "HAKHHHCAENA": "Name"}], [], tm,
    )
    identity = source_identity(metadata, key)
    assert identity["sender"] is None and identity["sender_status"] == "unresolved"
    assert identity["sender_source"] == "none"
    assert identity["thread_id"] == (str(message_thread) if message_thread == choice_thread else None)
    assert {ref["role"] for ref in identity["references"]} == {"message", "option_2"}
    message_ref = next(ref for ref in identity["references"] if ref["role"] == "message")
    assert message_ref["sender"] == name
    assert metadata["events"][0]["sender"] == name
    assert metadata["events"][0]["sender_status"] == "resolved"
    _extract_interknot(tm, tmp_path, message_metadata=metadata)
    source = json.loads((tmp_path / "message-audit.jsonl").read_text(encoding="utf-8"))
    assert source["sender"] is None and source["sender_status"] == "unresolved"
    assert source["text"] == text


def test_duplicate_npc_id_with_unresolved_name_cannot_claim_success():
    tm = TextMap({"name": "甲", "Message_1": "原文"}, "CHS")
    metadata = message_metadata([_config("Message_1", 1, 1)], [{"EGBBBFIINLO": 1003, "GJMPCHPFOMM": 1}],
                                [{"PFOAJKNPCHL": 1, "HAKHHHCAENA": "name"},
                                 {"PFOAJKNPCHL": 1, "HAKHHHCAENA": "missing"}], [], tm)
    assert source_identity(metadata, "Message_1")["sender"] is None
    assert metadata["contacts"]["1003"]["contact"] is None


def test_sms_source_audit_retains_placeholder_word_and_empty_values(tmp_path):
    tm = TextMap({"Message_1234501": "帮我在影院占位，谢谢！", "Message_1234502": "",
                  "Message_NPC01": "姓名", "Message_Unusual": "未采用数字格式的正文"}, "CHS")
    stats = _extract_interknot(tm, tmp_path)
    rows = {row["source_key"]: row for row in [json.loads(line) for line in
            (tmp_path / "message-audit.jsonl").read_text(encoding="utf-8").splitlines()]}
    assert set(rows) == {"Message_1234501", "Message_1234502", "Message_Unusual"}
    assert rows["Message_1234501"]["retained"]
    assert not rows["Message_1234502"]["retained"] and rows["Message_1234502"]["reason"] == "empty_text"
    assert stats["lore_messages"] == 2


def test_sms_config_adds_missing_reply_options_and_attachment_sources(tmp_path):
    tm = TextMap({"Message_Arbitrary_01": "{M#哲}{F#铃}，晚上来吗？", "Npc": "安比",
                  "Option01_100302": "马上来", "OptionLong01_100302": "我先把店里的事情处理完，再过去找你。",
                  "ItemTitle": "影像资料", "ItemBody": "附件里的完整文字"}, "CHS")
    metadata = message_metadata(
        [_config("Message_Arbitrary_01"), _config("", 0, 0, ident=100302,
          FNOKFPDDECI="Option01_100302", NAPGHEGEOOC="OptionLong01_100302", GGHOAADLHCF="UI/emoji.png")],
        [{"EGBBBFIINLO": 1003, "GJMPCHPFOMM": 10001}],
        [{"PFOAJKNPCHL": 10001, "HAKHHHCAENA": "Npc"}],
        [{"HJOEBMMFOMB": 1, "AJEGPOBMPCG": "ItemTitle", "DOPCCNPLNAF": "ItemBody"}], tm)
    stats = _extract_interknot(tm, tmp_path, message_metadata=metadata)
    rows = [json.loads(line) for line in (tmp_path / "message-audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["sender"] == "安比" and rows[0]["thread_id"] == "1003"
    assert rows[0]["contact_candidate"] == "安比" and rows[0]["contact_source"] == "message_group_config"
    assert stats["lore_message_extra_sources"] == 2
    assert stats["lore_message_item_sources"] == 2
    doc = (tmp_path / "02_绳网私信与手机短信.md").read_text(encoding="utf-8")
    assert "[100301] 安比" in doc and "男主路线：「哲，晚上来吗？」" in doc
    assert "马上来" in doc and "附件里的完整文字" in doc
    assert "UI/emoji.png" not in doc
    events = [json.loads(line) for line in (tmp_path / "message-config-audit.jsonl").read_text(encoding="utf-8").splitlines()]
    emoji = next(ref for ref in events[1]["references"] if ref["source_key"] == "UI/emoji.png")
    assert emoji["status"] == "nontext_or_missing"
