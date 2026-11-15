import json

from scripts.check_mcp_lore_sources import check
from zzz_story.writers import write_jsonl


def fixture(tmp_path):
    data = tmp_path / "data"
    (data / "TextMap").mkdir(parents=True)
    values = {"Profile_1": "原文档案", "Chat_1": "{M#哥哥}{F#姐姐}，你好", "Item_1": "附件原文"}
    (data / "TextMap/TextMapTemplateTb.json").write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "out"
    lore = output / "lore"
    (lore / "agents").mkdir(parents=True)
    # The checker verifies only paths. This text deliberately is not a source.
    (lore / "agents/profile.md").write_text("display labels may differ completely", encoding="utf-8")
    (lore / "interknot").mkdir()
    (lore / "interknot/message.md").write_text("display output", encoding="utf-8")
    write_jsonl([{"source_key": "Chat_1", "raw_text": values["Chat_1"], "text": "姐姐，你好",
                  "text_variants": {"M": "哥哥，你好", "F": "姐姐，你好"}, "retained": True}],
                lore / "agents/dialogue-audit.jsonl")
    write_jsonl([{"item_id": 1, "references": [{"source_key": "Item_1", "raw_text": values["Item_1"],
                                               "text": values["Item_1"], "text_variants": None}]}],
                lore / "interknot/message-item-audit.jsonl")
    header = {"schema_version": 1, "record_type": "manifest", "protagonist": "F",
              "covered_source_files": ["agents/profile.md", "interknot/message.md"]}
    document = {"schema_version": 1, "record_type": "document", "doc_id": "agent:1", "category": "agents",
                "title": "角色", "source_file": "agents/profile.md", "items": [
                    {"kind": "source", "field": "profile", "source_key": "Profile_1", "raw_text": None,
                     "text": values["Profile_1"], "text_variants": None, "selected_variant": None,
                     "line_type": "text", "speaker": None, "speaker_status": "not_applicable",
                     "section_kind": "biography", "section_title": ""},
                    {"kind": "audit", "field": "dialogue", "record_source": "agents/dialogue-audit.jsonl",
                     "source_key": "Chat_1", "section_kind": "daily", "section_title": ""}],
                "profile": {"facts": [{"field": "agentId", "value": "1", "item_index": None,
                                        "source_ref": {"file": "config.json", "id": "1"}}]}}
    attachment = {"schema_version": 1, "record_type": "document", "doc_id": "item:1", "entity_id": "1", "category": "interknot",
                  "title": "附件", "source_file": "interknot/message.md", "items": [
                      {"kind": "audit", "field": "attachment", "record_source": "interknot/message-item-audit.jsonl",
                       "source_key": "Item_1", "section_kind": "other", "section_title": ""}]}
    catalog = [header, document, attachment]
    write_jsonl(catalog, lore / "documents.jsonl")
    return output, data, catalog


def test_lore_sources_accepts_originals_variants_and_nested_attachment_refs(tmp_path):
    output, data, _ = fixture(tmp_path)
    result = check(output, data)
    assert result["ok"], result["errors"]
    assert result["categories"]["agents"]["retained_audit_sources"] == 1
    assert result["categories"]["interknot"]["retained_audit_sources"] == 1


def test_lore_sources_rejects_display_text_in_source_body(tmp_path):
    output, data, catalog = fixture(tmp_path)
    catalog[1]["items"][0]["text"] = "档案记录：原文档案"
    write_jsonl(catalog, output / "lore/documents.jsonl")
    result = check(output, data)
    assert not result["ok"]
    assert any("differs from" in error for error in result["errors"])


def test_lore_sources_detects_missing_retained_source_and_dangling_ref(tmp_path):
    output, data, catalog = fixture(tmp_path)
    catalog[1]["items"][1]["source_key"] = "missing"
    write_jsonl(catalog, output / "lore/documents.jsonl")
    result = check(output, data)
    assert not result["ok"]
    assert result["categories"]["agents"]["unreferenced_audit_sources"] == 1
    assert any("dangling audit" in error for error in result["errors"])


def test_lore_sources_requires_config_reference_target(tmp_path):
    output, data, _ = fixture(tmp_path)
    audit = output / "lore/agents/dialogue-audit.jsonl"
    row = json.loads(audit.read_text(encoding="utf-8"))
    row["config_references"] = [{"config_id": 7}]
    write_jsonl([row], audit)
    result = check(output, data)
    assert not result["ok"]
    assert any("configuration reference" in error for error in result["errors"])


def test_lore_sources_rejects_known_source_attached_to_wrong_agent(tmp_path):
    output, data, catalog = fixture(tmp_path)
    audit = output / "lore/agents/dialogue-audit.jsonl"
    row = json.loads(audit.read_text(encoding="utf-8"))
    row["agent_id"] = 2
    write_jsonl([row], audit)
    catalog[1]["entity_id"] = "1"
    write_jsonl(catalog, output / "lore/documents.jsonl")
    result = check(output, data)
    assert not result["ok"]
    assert any("another agent" in error for error in result["errors"])


def test_lore_sources_rejects_unknown_group_without_event_tag(tmp_path):
    output, data, catalog = fixture(tmp_path)
    audit = output / "lore/agents/dialogue-audit.jsonl"
    row = json.loads(audit.read_text(encoding="utf-8"))
    row.update(agent_id=None, scope="PartnerTalk", family="Chat", scene="1001", event_tag="UnknownA")
    write_jsonl([row], audit)
    catalog[1]["entity_id"] = "PartnerTalk|Chat|1001"
    catalog[1]["items"][1]["scene_id"] = "1001"
    write_jsonl(catalog, output / "lore/documents.jsonl")
    result = check(output, data)
    assert not result["ok"]
    assert any("source group" in error for error in result["errors"])
