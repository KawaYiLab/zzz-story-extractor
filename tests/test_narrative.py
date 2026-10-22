import struct

from test_perform_graph import encode_node, list_node, node

from zzz_story.extract import NAME_IGNORE, _line_sort_key, _mark_unattributed_scenes
from zzz_story.narrative import annotate_attribution, annotate_local_order
from zzz_story.odin import Entry
from zzz_story.perform_graph import configured_routes, graph_from_raw, graph_links
from zzz_story.speakers import SpeakerInfo, alias_from_source, structured_speaker
from zzz_story.textmap import TextMap


def raw_sections(sections):
    payload = encode_node(list_node([list_node(section) for section in sections]), "storySections")
    name = b"fixture"
    header = b"\0" * 28 + struct.pack("<i", len(name)) + name
    header += b"\0" * (-len(header) % 4)
    return header + struct.pack("<ii", 0, len(payload)) + payload


def test_chat_array_addresses_and_exact_names():
    first = node("MainCityChatPlayStoryNode", 0, 0, dialogueKey="chat", avatarName="NPC")
    first.entries = [e for e in first.entries if e.name not in {"sectionIdx", "subSectionIdx"}]
    graph = graph_from_raw(raw_sections([[first]]))
    link = graph_links({"chat.asset": graph}, {"chat.asset": {"M", "F"}})["chat"]
    assert link["occurrences"][0]["section"] == 0
    assert structured_speaker(link, TextMap({"NPC": "咨询"}, "CHS"), {}).speaker == "咨询"
    assert {"咨询", "购买", "找零"}.isdisjoint(NAME_IGNORE)


def test_unknown_actor_slot_and_timing_use_uppercase_fields():
    graph = graph_from_raw(raw_sections([[
        node("GalBubbleStoryNode", 0, 0, Text="third", Speaker="A", StartTime=3000, EndTime=6000),
        node("GalBubbleStoryNode", 0, 1, Text="first", Speaker="B", StartTime=0, EndTime=3000,
             Voice="GalGame_Chapter02_Belle_001"),
    ]]))
    links = graph_links({"bubble.asset": graph}, {"bubble.asset": {"M", "F"}})
    assert graph.keys == {"third", "first"}
    assert structured_speaker(links["first"], TextMap({}, "CHS"), {"belle": "铃"}).speaker == "铃"
    records = [{"chapter": "Chapter02", "family": "Bubble", "scene": "1", "line_no": n,
                "sub_no": None, "variant": None, "source_key": key, "perform": links[key],
                "line_type": "unknown", "speaker": None} for n, key in [(1, "third"), (3, "first")]]
    annotate_attribution(records)
    annotate_local_order(records)
    records.sort(key=lambda row: _line_sort_key(row, {}))
    assert [row["source_key"] for row in records] == ["first", "third"]
    assert records[0]["line_order_status"] == "within_section"
    assert records[1]["speaker_slot"] == "A"
    assert records[1]["speaker_gap_reason"] == "unbound_actor_slot"


def test_reused_text_keys_keep_distinct_occurrences_and_do_not_guess_order():
    graph = graph_from_raw(raw_sections([[
        node("GalBubbleStoryNode", 0, 0, Text="same", Speaker="A", StartTime=0),
        node("GalBubbleStoryNode", 0, 1, Text="same", Speaker="B", StartTime=3000),
    ]]))
    link = graph_links({"bubble.asset": graph}, {"bubble.asset": {"M"}})["same"]
    assert len(link["occurrences"]) == 2
    record = {"chapter": "Chapter02", "family": "Bubble", "scene": "1", "perform": link}
    annotate_local_order([record])
    assert record["line_order_source"] == "source_key"
    assert record["line_order_status"] == "unknown"


def test_typed_narrator_does_not_inherit_legacy_speaker():
    graph = graph_from_raw(raw_sections([[node("GalSwitchSceneNode", 0, 0, dialogueKey="screen")]]))
    link = graph_links({"screen.asset": graph}, {"screen.asset": {"M"}})["screen"]
    info = structured_speaker(link, TextMap({}, "CHS"), {}, SpeakerInfo("错配角色", "NPC", .95, "avatar"))
    assert info.speaker is None
    record = {"chapter": "Chapter02", "family": "GalGame", "scene": "1", "speaker": None,
              "line_type": "narration", "perform": link}
    _mark_unattributed_scenes([record])
    assert record["line_type"] == "unknown"
    annotate_attribution([record])
    assert record["line_type"] == "narration"
    assert record["speaker_status"] == "not_applicable"


def test_black_screen_lists_and_chatplus_names_are_read(monkeypatch):
    sections = [[
        node("MainCityChatBlackScreenNode", 0, 0, dialogueKeys=list_node(["one", "two"])),
        node("PlayChatPlusStoryNode", 0, 1, DialogueKey="chatplus", NpcName="NPC", ExternalVoiceKey="voice"),
    ]]
    monkeypatch.setattr("zzz_story.perform_graph.perform_entries", lambda _: (
        "fixture", [Entry("storySections", list_node([list_node(section) for section in sections]))]))
    graph = graph_from_raw(b"fixture")
    assert graph.keys == {"one", "two", "chatplus"}
    assert graph.avatars["chatplus"] == {"NPC"}
    assert graph.voices["chatplus"] == {"voice"}


def test_configured_routes_include_chat_and_bubbles():
    paths = [f"Data/ScriptConfig/Perform/Data/{family}/Chapter02/main.asset" for family in ("GalGame", "Chat", "Bubble")]
    routes = configured_routes({"IAEFFFFLKNB": [{"BCKKFAEFDPP": p, "LGJCAHIEBBK": p} for p in paths]})
    assert set(routes) == set(paths)


def test_csr_voice_alias_is_the_character_segment():
    assert alias_from_source("Timeline_Csr_C26_Yeshunguang_Auditory_YeShunguang_001") == "YeShunguang"
    assert alias_from_source("Timeline_Csr_C26_Yeshunguang_Stretching_03_Wise_002") == "Wise"
    assert alias_from_source("Timeline_Csr_C26_Yeshunguang_Ambush_SarasWhispercroon_001") == "SarasWhispercroon"
    assert alias_from_source("OngoingLevel_Chapter160_YeShunguang_111632038_001") == "YeShunguang"
    assert alias_from_source("ChatPlus_Chapter170_Ariaidol_817014093_001") == "Ariaidol"
    assert alias_from_source("BubbleStory_Bubmale_Chapter230_32GuardVoicelineA_423000015_001") == "32GuardVoicelineA"


def test_hidden_identity_does_not_fall_back_to_voice_when_display_is_unresolved():
    link = {"avatars": ["HiddenName"], "voice_keys": ["GalGame_Chapter01_Belle_001"],
            "occurrences": [{"avatar": "HiddenName"}]}
    assert structured_speaker(link, TextMap({}, "CHS"), {"belle": "铃"}).speaker is None


def test_multiple_display_keys_for_same_character_are_not_a_conflict():
    link = {"avatars": ["AvatarAria", "SceneAria"], "voice_keys": [], "occurrences": [{}]}
    info = structured_speaker(link, TextMap({"AvatarAria": "爱芮", "SceneAria": "爱芮"}, "CHS"), {})
    assert info.speaker == "爱芮"


def test_sound_event_in_voice_field_does_not_count_as_voiced_dialogue():
    graph = graph_from_raw(raw_sections([[node("GalSwitchSceneNode", 0, 0, dialogueKey="screen",
                                            voiceKey="Play_GalGame_Chapter070_340_SFX_001")]]))
    assert not graph.voices["screen"]


def test_hidden_actor_binding_is_not_narration():
    record = {"line_type": "unknown", "perform": {"occurrences": [{"hide_name": True,
              "speaker_binding": {"SpeakerSubID": 100172041}}]}}
    annotate_attribution([record])
    assert record["line_type"] == "unknown"
    assert record["speaker_gap_reason"] == "node_without_display_name"


def test_reversed_archive_neighbours_do_not_reverse_numeric_fallback():
    from zzz_story.extract import _galgame_scene_positions
    positions = _galgame_scene_positions(["10", "11", "12", "13"], {"10": (2, 0), "13": (1, 0)})
    assert positions["13"] < positions["10"] < positions["11"] < positions["12"]
