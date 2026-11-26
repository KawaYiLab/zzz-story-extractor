# Lore machine document format, version 1

`lore/documents.jsonl` is an optional, UTF-8, source-keyed catalog. It is
collected during extraction from TextMap reads and audit objects, never by
parsing Markdown. The existing bundle format remains 1.

The first nonempty record is a manifest:

```json
{"schema_version":1,"record_type":"manifest","covered_source_files":["README.md","agents/00_代理人全景总览.md","agents/01_狡兔屋.md"]}
```

Paths are relative to `lore/`, use `/`, and name files whose content is fully
replaced by the machine documents. Covered Markdown must not also be indexed.
An uncovered old Markdown file may use the old importer. A malformed machine
catalog, unknown schema version, or dangling audit reference must fail import;
it must not silently fall back to the covered Markdown. Generated introductions,
overview tables, inferred classifications, preview truncation, and missing-value
labels are presentation content, not source text. Their files may be covered
without producing an empty document.

Every subsequent record is a nonempty document:

```json
{"schema_version":1,"record_type":"document","doc_id":"lore:agents:agent:1011","category":"agents","title":"安比","source_file":"agents/01_狡兔屋.md","entity_id":"1011","items":[{"kind":"source","field":"Partner_ProfileDesc_1011","source_key":"Partner_ProfileDesc_1011","text":"原始档案段落","raw_text":"原始档案段落","text_variants":null,"selected_variant":null,"line_type":"text","speaker":null,"speaker_status":"not_applicable","section_kind":"biography","section_title":""},{"kind":"audit","field":"dialogue","record_source":"agents/dialogue-audit.jsonl","source_key":"Chat_PartnerTalk_Anbi_2_4_7","section_kind":"daily","section_title":"互动","scene_id":"2_4","scene_title":null}],"profile":{"faction":"狡兔屋","facts":[{"field":"agentId","value":"1011","item_index":null,"source_ref":{"file":"FileCfg/AvatarBaseTemplateTb.json","field":"PFOAJKNPCHL","id":"1011"}}]}}
```

`doc_id` is stable and derived from category, entity type, and source/config
identity. `title` and `source_file` are metadata, not text appended to a line.
`items` preserve document order. Source items carry the full original TextMap
value in `raw_text` when cleaning changes it (otherwise null means identical
to `text`), its cleaned selected rendering in `text`, and separate
M/F renderings in `text_variants` when they differ. `selected_variant` is the
actual M/F selection when different inline gender variants exist, including
fallback when a branch is empty. The importer indexes each distinct rendering.
Source keys with identical text remain distinct. Each item is one source field,
including multiline source values; labels, speaker prefixes and branch labels
are not inserted into `text`.

Audit items resolve by the exact pair `(record_source, source_key)` within the
document category. The allowed files are `agents/dialogue-audit.jsonl`,
`agents/unassigned-dialogue.jsonl` (only if the main agents audit is absent),
`street/dialogue-audit.jsonl`, `interknot/message-audit.jsonl`,
`interknot/message-extra-sources.jsonl`, and
`interknot/message-item-audit.jsonl` (keys inside `references`). Only retained,
nonempty source rows are referenced. A source can occur in multiple documents
when the configuration references it in multiple contexts. It is not a second
source or proof of repeated playback. Speaker, unknown attribution, raw text,
variants, resource occurrences, configuration events, and chronology status
remain in the audit evidence and must survive import. Joining source text to
display Markdown is unnecessary.

`section_kind` is one of `introduction`, `biography`, `commentary`, `trust`,
`daily`, `bubble`, `other`. Optional `section_title`, `scene_id`, and
`scene_title` define typed profile/context ranges and never enter body text.

Agent `profile` is optional typed metadata. `facts.field` is `agentId`,
`faction`, `birthday`, `height`, or `wEngine`; `value` is the pure source value.
`item_index` is a zero-based source item index when a TextMap field proves the
fact. Otherwise it is null and `source_ref` identifies the configuration
source. Such metadata must not pretend to have a quoted text line. Facts and
faction mappings do not establish a speaker or playback chronology.
