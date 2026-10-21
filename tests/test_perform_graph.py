import json
import struct
from types import SimpleNamespace

import pytest

from zzz_story.extract import _collapse_gender_pairs, _filter_branch_lines, _filter_perform_routes, _write_csv
from zzz_story.odin import Entry, Node, OdinError, Reference, perform_entries, read_entries
from zzz_story.perform_graph import asset_hash, graph_from_raw, graph_links, graphs_from_cab, link_unused_copies
from zzz_story.textmap import TextMap


def string(value, encoding=1):
    return bytes([encoding]) + struct.pack("<i", len(value)) + value.encode("utf-16le" if encoding else "latin1")


def encode_node(node, name=None):
    result = bytes([1 if name is not None else 2])
    if name is not None:
        result += string(name)
    if node.type_name:
        type_id = encode_node.type_id
        encode_node.type_id += 1
        result += b"\x2f" + struct.pack("<i", type_id) + string(node.type_name)
    else:
        result += b"\x2e"
    result += struct.pack("<i", node.reference_id or 0)
    for entry in node.entries:
        if isinstance(entry.value, Node):
            result += encode_node(entry.value, entry.name)
        elif isinstance(entry.value, list):
            result += b"\x06" + struct.pack("<q", len(entry.value))
            result += b"".join(encode_node(value) for value in entry.value) + b"\x07"
        else:
            tag = 0x17 if isinstance(entry.value, int) else 0x27
            result += bytes([tag]) + string(entry.name)
            result += struct.pack("<i", entry.value) if tag == 0x17 else string(entry.value)
    return result + b"\x05"


encode_node.type_id = 0


def list_node(values):
    return Node(None, 0, [Entry(None, values)])


def node(kind, section, sub, **fields):
    return Node(f"MoleMole.GalGame.{kind}, Logic", 0,
                [Entry("sectionIdx", section), Entry("subSectionIdx", sub)]
                + [Entry(k, v) for k, v in fields.items()])


def raw_fixture(*, rejoin=True, gender=True, shared=False, picture=False):
    branches = list_node([
        Node(None, 0, [Entry("value", 1), Entry("bindSectionIndex", 1), Entry("bindSubSectionIndex", 0)]),
        Node(None, 0, [Entry("value", 2), Entry("bindSectionIndex", 2), Entry("bindSubSectionIndex", 0)]),
    ])
    sections = [
        [node("GalConditionNode", 0, 0, conditionKey="Gender" if gender else "Quest",
              conditionList=branches)],
        [node("GalPlayPictureStoryNode" if picture else "GalPlayStoryNode", 1, 0, dialogueKey="male", avatarName="NPC", externalVoiceKey="voice"),
         node("GalJumpChapterNode", 1, 1, chapterIndex=3, subIndex=0)],
        [node("GalPlayStoryNode", 2, 0, dialogueKey="female", avatarName="NPC"),
         node("GalJumpChapterNode", 2, 1, chapterIndex=3 if rejoin else 99, subIndex=0)],
        [node("GalPlayStoryNode", 3, 0, dialogueKey="female" if shared else "shared")],
    ]
    payload = encode_node(list_node([list_node(s) for s in sections]), "storySections")
    name = b"fixture"
    header = b"\0" * 28 + struct.pack("<i", len(name)) + name
    header += b"\0" * (-len(header) % 4)
    return header + struct.pack("<ii", 0, len(payload)) + payload


def test_entry_types_strings_arrays_and_type_reuse():
    data = (b"\x01" + string("root", 0) + b"\x2f" + struct.pack("<i", 7) + string("Type", 0)
            + struct.pack("<i", 1) + b"\x06" + struct.pack("<q", 1)
            + b"\x02\x30" + struct.pack("<ii", 7, 2)
            + b"\x27" + string("value") + string("hello")
            + b"\x09" + string("ref") + struct.pack("<i", 1)
            + b"\x05\x07\x05\x31")
    root = read_entries(data)[0].value
    child = root.entries[0].value[0]
    assert root.type_name == child.type_name == "Type"
    assert child.get("value") == "hello"
    assert child.get("ref") == Reference("internal", 1)


@pytest.mark.parametrize("payload", [b"\x27\x02", b"\x28\x01\xff\xff\xff\xff",
                                    b"\x06" + struct.pack("<q", -1), b"\x31\0", b"\x02\x30\0\0\0\0"])
def test_rejects_malformed_binary(payload):
    with pytest.raises(OdinError):
        read_entries(payload)


def test_monobehaviour_payload_bounds():
    raw = raw_fixture()
    assert perform_entries(raw)[0] == "fixture"
    with pytest.raises(OdinError):
        perform_entries(raw[:-1])


def test_gender_arms_require_explicit_condition_and_reunion():
    graph = graph_from_raw(raw_fixture())
    assert graph.keys == {"male", "female", "shared"}
    assert graph.sides == {"male": {"M"}, "female": {"F"}}
    assert graph.pairs == {"male": "female", "female": "male"}
    assert graph.avatars["male"] == {"NPC"}
    assert graph.voices["male"] == {"voice"}
    assert not graph_from_raw(raw_fixture(rejoin=False)).sides
    assert not graph_from_raw(raw_fixture(gender=False)).sides
    assert graph_from_raw(raw_fixture(shared=True)).sides["female"] == {"M", "F"}
    assert graph_from_raw(raw_fixture(picture=True)).sides == graph.sides


def test_configured_asset_container_is_required(monkeypatch):
    path = "Data/ScriptConfig/Perform/Data/GalGame/fixture.asset"
    target = SimpleNamespace(class_id=114, path_id=1, get_raw_data=raw_fixture)
    pointer = SimpleNamespace(m_FileID=0, m_PathID=1)
    bundle = SimpleNamespace(class_id=142, path_id=2,
                             read=lambda: SimpleNamespace(m_Container=[(asset_hash(path), SimpleNamespace(asset=pointer))]))
    monkeypatch.setattr("UnityPy.load", lambda _: SimpleNamespace(objects=[bundle, target]))
    assert graphs_from_cab(b"fixture", {asset_hash(path): path})[path].name == "fixture"
    assert not graphs_from_cab(b"fixture", {"wrong": path})


def test_shared_references_and_conflicting_assets_are_not_filtered():
    path = "fixture.asset"
    links = graph_links({path: graph_from_raw(raw_fixture())}, {path: {"M", "F"}})
    assert links["female"]["explicit_gender"]
    shared = graph_from_raw(raw_fixture(shared=True))
    merged = graph_links({path: graph_from_raw(raw_fixture()), "other": shared},
                         {path: {"M", "F"}, "other": {"M", "F"}})
    assert not merged["female"]["explicit_gender"]


def test_filter_routes_keeps_npc_repeats_and_unpaired_candidates(tmp_path):
    links = graph_links({"fixture": graph_from_raw(raw_fixture())}, {"fixture": {"M", "F"}})
    records = [{"source_key": key, "chapter": "Chapter220", "scene": "1", "family": "GalGame",
                "text": "same NPC line", "perform": link} for key, link in links.items()]
    records += [{**records[0], "source_key": "pause", "perform": {}}]
    kept, dropped = _filter_perform_routes(records)
    assert dropped == 1 and {r["source_key"] for r in kept} == {"male", "shared", "pause"}
    female = next(r for r in records if r["source_key"] == "female")
    assert female["_discard_reason"] == "perform_gender_route"
    assert female["_paired_source_key"] == "male"
    assert _filter_perform_routes([female])[1] == 0
    csv = tmp_path / "story.csv"
    _write_csv([{**kept[0], "scene_speakers": [], "text_variants": None}], csv)
    import csv as csv_module
    with csv.open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv_module.DictReader(handle))
    assert json.loads(row["perform"]) == kept[0]["perform"]


def test_duplicate_only_omissions_require_near_complete_common_asset():
    prefix = "Main_GalGame_Chapter210_121000258"
    path = "fixture.asset"
    tm = TextMap({prefix + f"_{n:03}": f"line-{min(n, 16)}" for n in range(1, 20)}, "CHS")
    from zzz_story.perform_graph import Graph
    graph = Graph(prefix, set(list(tm.keys())[:16]))
    links = graph_links({path: graph}, {path: {"M", "F"}})
    link_unused_copies(links, {path: graph}, {path: {"M", "F"}}, tm)
    assert all(links[prefix + f"_{n:03}"]["copy_of"] == prefix + "_016" for n in (17, 18, 19))
    # A distinct omitted line means the scene is incomplete, not duplicate-only.
    tm._mapping[prefix + "_019"] = "different text"
    links = graph_links({path: graph}, {path: {"M", "F"}})
    link_unused_copies(links, {path: graph}, {path: {"M", "F"}}, tm)
    assert prefix + "_017" not in links
    tm._mapping[prefix + "_019"] = "line-16"
    link_unused_copies(links, {path: graph}, {path: {"M"}}, tm)
    assert prefix + "_017" not in links


def test_heuristics_cannot_remove_verified_sister_npc_on_male_route():
    base = {"chapter": "Chapter220", "scene": "1", "family": "GalGame", "sub_no": None}
    rows = [{**base, "source_key": "wise", "line_no": 1, "speaker": "哲", "text": "same"},
            {**base, "source_key": "belle", "line_no": 2, "speaker": "铃", "text": "same",
             "perform": {"sides": ["M"], "explicit_gender": True}}]
    assert _collapse_gender_pairs(rows, "M")[1] == 0
    rows[0]["text"], rows[1]["text"] = "铃，你好", "哥哥，你好"
    assert _filter_branch_lines(rows)[1] == 0


def test_voice_alias_with_multi_part_line_suffix():
    from zzz_story.speakers import alias_from_source
    assert alias_from_source("GalGame_Chapter110_JuFufu_200_006_01") == "JuFufu"
