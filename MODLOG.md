# 3.3.0 extraction compatibility

Verified on 2026-10-21 with local `CNPRODWin3.3.0` resources. This session
reads installed files only. Existing 3.2.0 caches, outputs and working changes
were preserved.

## Inputs

- ZenlessData snapshot: [fd6cb326c07c75f39b0b05845d204302c451ec34](https://git.mero.moe/dimbreath/ZenlessData/commit/fd6cb326c07c75f39b0b05845d204302c451ec34).
- All 13 required files are bound to that commit and verified by SHA-256 in
  `data/cache/3.3.0/source_provenance.json`. The merged CHS map has 451,194 keys.
- The GitHub fallback mirror was still at 3.2.0 during inspection. It cannot
  substitute an older snapshot for files from the fixed Gitea commit.
- Perform, AvatarBase, archive and quest fields used by the extractor retain
  their existing names. `MainStoryChapterName_1021` supplies the Chapter240 title.
- Community reference inspected: [zenless-voice/galgame-perform.ts](https://github.com/simon300000/zenless-voice/blob/master/galgame-perform.ts).
  Its public catalog reader still expects gzip; the new layout below was
  verified against the local game files.

## Resource Index

The index is the untagged `Blocks/<id>.blk` entry in `res_version` or
`res_version_persist`, currently `2837526243.blk`. Resolve the persistent
version first, then the streaming install. Perform resources use the same
priority. There is no standalone gzip block in this 3.3 install.

The new index uses the existing mhy1 decoder. UnityPy locates custom object
class ID `6776977` in the decoded Unity file, so the parser does not hardcode
its file offset. The object's little-endian prefix is `03 00 00 00 52 65 73 00`.

| Table | Encoding |
| --- | --- |
| Assets | u32 count, then 12-byte entries: u32 bundle index + u64 path hash |
| Bundles | u32 count, then 44-byte entries; first u32 is the block index |
| Blocks | u32 count, then 9-byte entries; first u32 is the block filename ID |

Trailing dependency data is not needed to locate Perform blocks. Every table
end is checked before access. Legacy gzip keeps its 52-byte header, 28-byte
bundle stride and block filename ID at offset 1 within each 9-byte entry.

The persistent index contains 570,614 assets, 784,413 bundles and 10,532 blocks.
The base index also parses: 565,107 assets, 778,871 bundles and 10,470 blocks.
Of 31,098 Perform paths, 30,765 match the persistent index and use 20 blocks.
The base index matches 30,762 paths and uses 19 blocks. The scanner decoded
66,907 voice links, 181,898 avatar links and 41,903 options from the selected
20 blocks. Speaker fingerprints now cover both block directories, nested
resource files and both version manifests.

## Verification

- Tool version is 0.3.0; default cache and output version is 3.3.0.
- 124 Python tests pass, including both index layouts, truncated new tables,
  Unity object extraction, persistent resource priority and cache invalidation.
- Editable installation, dependency checks and `doctor` pass.
- Default extraction: 48,977 main lines, 4,605 supplement lines, 65 agent files;
  JSONL, TXT, CSV and lore are in `out/zzz_story_3.3.0_chs`.
- Accuracy extraction: 53,141 main lines and 4,787 supplement lines, in
  `out/zzz_story_3.3.0_chs_audit`.
- Both outputs pass `verify` with zero errors and zero warnings.
- `python -O scripts/check_corpus_integrity.py` passes: 57,928 line candidates,
  53,582 retained, 4,346 discarded lines and 5 discarded name entries. Raw
  text, candidate destinations and stable IDs were checked.
- Compared with `out/reviewed_final_3.2.0`, there are 2,248 new main lines,
  zero removed lines and 5 changed lines. All additions are Chapter240;
  changes in Chapter230 comprise one text edit and four speaker/type updates.

## Remaining Data Limits

- Default voiced coverage is 21,239 / 21,245, about 99.9718%. Five unresolved
  rows are historical; the sixth is
  `Main_GalGame_Chapter240_124000040_015` with alias `SunbringerBangboo`.
  No display name was guessed for it. Accuracy-mode coverage is 24,572 / 24,590.
- 333 configured Perform paths do not match the persistent index, including
  10 main paths. Chapter240 matches 130 / 133 paths; unmatched scenes are
  `124000036`, `124000037` and `124000038`. The first two have TextMap entries
  that remain candidates; the third has no matching TextMap scene.
- Six empty TextMap values in Chapter02 remain reported in `missing_examples`.
- No `CS_34_*` exists in this snapshot. Comic remains unlinked. Chapter240 has
  39 GalGame scenes, with no validated task association or playback chronology.
- Full extraction verifies the available inputs and retained candidates, not
  completeness against the game's runtime or an exact single-protagonist route.
- No game files or decoded containers were added to version control. No upload,
  deployment, commit or push was performed.

## ChatPlus Duplicate-Line Repair

The reported scene is `Main_GalGame_Chapter210_1721000030`, act 55,
"烈火与缰绳". The original default output had 78 lines; the same issue was
already present in the reviewed 3.2 output. Ordinary Perform scanning linked
only lines 001-010, leaving the rest unattributed and both routes visible.

Verified local resource chain:

- Perform row `1721000030` selects `TL_C30_ChatPlus_03B` in `BCKKFAEFDPP`
  (male route) and `TL_C30_ChatPlus_03G` in `LGJCAHIEBBK` (female route).
- Graphs in patched `Blocks/Data/1288178548.blk` invoke
  `PlayChatPlusTimeline` with the matching `TimelineDataKey`.
- `Blocks/3564160063.blk` contains `ChatPlusTimeline_3.0` configuration,
  referencing `CutScene_Runtime/ChatPlusTimeline/3.0/<name>/<name>.prefab`.
- Both prefabs resolve through the resource index to `3897008602.blk`.
  CABs 293 and 303 contain `TL_C30_ChatPlus_03B_Timeline` and
  `TL_C30_ChatPlus_03G_Timeline`, respectively.
- `ChatPlusDialogClip` is a MonoBehaviour (class 114). Its script PPtr is at
  offset 16, its aligned name string at offset 28, followed by three aligned
  UTF-8 Unity strings: avatar, text key, voice key. Cloned object names must
  also be read; otherwise lines 51, 63 and 85 are missed. UnityPy verifies
  the MonoScript class before parsing this layout.

`timeline.py` discovers the config blocks from manifest tag 2 and resolves
configured prefab paths, without pinning block IDs. Both declared routes must
be present. Main-text namespaces are linked only with matching scene/line
numbers, at least 10 comparable clips and at least 90% exact cleaned-text
alignment. Unused adjacent identical main copies are marked only when the
preceding timeline key is shared by both routes. This is not global text
deduplication. Public source text is never rewritten.

The scan resolved 68 prefab paths in 8 blocks and read 831 unique clips.
148 main-text candidates passed correspondence checks, in scenes 1721000005,
1721000006 and 1721000030. Other timeline/main namespaces remain unlinked.
Timeline avatar names take precedence over voice-bank aliases so the hidden
speaker is displayed as "？？？", not their internal voice identity.

Final verification:

- 132 tests pass, including cloned clips, script identity, namespace mismatch,
  missing route resources, shared NPC lines, distinct branch wording, repeated
  unattributed pauses, CSV metadata and complete default/audit extraction.
- Corrected output: `out/zzz_story_3.3.0_chs_corrected`, 48,940 main lines,
  35,817 attributed lines, 4,605 supplement lines. Voiced coverage is
  21,275 / 21,281; the same six unresolved lines remain.
- Audit output: `out/zzz_story_3.3.0_chs_corrected_audit`, 53,141 main lines,
  4,787 supplement lines. Voiced coverage is 24,645 / 24,663.
- Both pass verify with zero errors/warnings. Corpus integrity passes:
  57,928 candidates, 53,545 retained, 4,383 discarded lines and 5 discarded
  name entries. Every original candidate and stable retained ID is accounted for.
- Act 55 now has 42 lines, all attributed, with zero adjacent identical
  texts. Its 41 discarded original candidates comprise 29 female-route lines
  and 12 unused main-text copies. The common Billy line remains.
- Against the initial 3.3 default output, 38 lines were removed and one line
  restored, all in the three scenes above. The restored 1721000005_023 is
  Belle's independent NPC dialogue on the male route. No retained text changed.
- Act 55 main-text lines 014, 069 and 077 differ from timeline subtitles.
  014/077 contain merged segments; 069/077 have a sibling-address discrepancy.
  They retain their main text and carry `timeline.text_difference=true`.
  Full runtime chronology and resolution of these text discrepancies remain
  outside the verified scope.
- Initial 3.3 outputs and the partial CSV-failure attempt in
  `out/zzz_story_3.3.0_chs_fixed` are preserved. Use the corrected directory.

## Full Content Review (2026-10-21)

Read the original Odin binary entry specification from the public
TeamSirenix/odin-serializer repository (BinaryEntryType.cs and
BinaryDataReader.cs), then verified it against local MonoBehaviour objects.
The object name is an aligned Unity UTF-8 string at offset 28, followed by
serialization format 0, a bounded byte-array size, and the Odin stream.
Named strings support 8-bit or UTF-16LE character storage. Type references,
reference IDs, arrays and node boundaries are decoded without instantiating
serialized classes. AssetBundle container hashes and PPtrs resolve the exact
PerformTemplate-selected asset, rather than selecting nearby strings.

Verified `GalConditionNode.conditionKey=Gender`, values 1/2, uses
`bindSectionIndex` / `bindSubSectionIndex` for M/F routes. Separate arms use
`GalJumpChapterNode.chapterIndex` / `subIndex` to rejoin the common graph.
Only linear known-node arms with a verified reunion and mutual text peers
are filtered. Unknown conditions, non-rejoining arms and conflicting/shared
references remain candidates. `GalPlayPictureStoryNode` is also a dialogue
node. `conditionTransitionList` is not guessed as a gender condition.

Scanned 20 blocks, read 2,213 configured graphs, zero parse failures.
17,701 resource text keys have explicit gender peer evidence, including
non-main-story content. Nine main duplicate-only omissions meet the narrow
unused-copy checks, including scene 121000258 lines 017/018/019.
Exact avatar fields preserve hidden names; multi-part voice numeric suffixes
now resolve aliases. Explicit M routes protect independent Belle NPC lines.

The same evidence is used for agent lore interactions. Name metadata is
excluded, nested scene suffixes and encounter IDs are preserved, and
`lore/agents/dialogue-audit.jsonl` retains every extracted dialogue source and
original value. Counts in equipment/index headings are generated from data.

Final outputs: `out/zzz_story_3.3.0_chs_complete` and
`out/zzz_story_3.3.0_chs_complete_audit`. Main lines 47,625 / 53,141;
supplement lines 4,605 / 4,787; default voice attribution 19,976 / 19,986.
Compared with this round's baseline, 1,722 main candidates move to audit,
407 candidates return, 3,311 speaker labels change, zero retained texts change.
Agent interaction candidates 40,033 in both modes; default removes 1,077
explicit F-route entries with preserved raw text and retained peers.

149 tests pass. Both outputs pass verify. All 57,928 main/supplement
candidates and stable IDs reconcile (52,230 retained, 5,698 removed lines,
5 removed names). Lore candidates also reconcile without raw-text changes.
TXT, CSV and chapter exports match JSONL re-rendering. Full content audit
finds no supported-markup/empty/replacement-character anomalies.

Remaining signals are deliberately retained: 317 adjacent equal main pairs,
159 at least 12 characters; 188 partially referenced scenes; 90 equal lore
interaction pairs; two duplicated achievement rows with distinct source IDs;
10 unresolved voiced speakers and six empty TextMap values. Stub/missing
resources, external timelines and runtime chronology remain limitations.
See `docs/full-content-review-2026-10-21.md` and output content-audit files.
Several intermediate output folders are preserved, including failed lore
generation attempts; use only the final complete/complete_audit pair.

## 2026-10-21 Mainline architecture and attribution review

Confirmed that TextMap-key catalog ordering is not playback execution.
Offline inspection of 4,964 configured main-story assets found 1,277 bubble
nodes using Speaker/Text/Voice and 14,650 MainCityChatPlayStoryNode instances
without serialized address fields. These layouts were absent from typed
parsing. Added per-occurrence positions, node types, names, actor bindings,
voice keys and bubble timing. Main_Chat_Chapter01_40100031 plays key 03 at
0 ms, key 01 at 3000 ms, key 02 at 6000 ms: numeric ordering was reversed.
Only unambiguous, fully covered single-section bubbles use local timing.

Removed actual Bangboo names 咨询/购买/找零 from global non-character filters.
Added Timeline_Csr, Ongoing and bubble/chat voice alias layouts, black-screen
text lists and ChatPlus fields. Compare resolved display names across keys;
typed empty fields do not inherit nearby-string identities. Sound events in
voice fields do not count as voices. Unknown actor slots remain unbound.

Final outputs supersede the earlier complete pair for this review:
out/architecture_review_final_3.3.0 and matching _audit. 161 tests pass;
both outputs validate and render consistently. All 57,928 candidates retain
raw text, stable IDs and accounted destinations (51,478 kept / 6,450 removed
lines / 5 removed names). 80 previously unnamed retained lines regain names,
no existing named retained line loses attribution. Unknown 3,088 -> 2,298;
1,203 unbound slots, 947 missing typed references, 143 nameless nodes,
4 conflicting display names and 1 unresolved display key remain. 5,781
typed assets, zero parse failures. 726 groups use local bubble timing; two
groups change relative line order. Runtime cross-scene execution remains
unknown. See docs/mainline-architecture-review-2026-10-21.md.

## Follow-up: Chapter240 acts 32-34 are scene outlines

User identified the incorrect Anby attribution at story.txt line 71446.
Checked exact raw assets 124000032/33/34: their display names really are
Anby; act 32 uses actorId 1011 and Anby model keys, acts 32/33 have Anby
voice-key strings. Text values are scene-writing summaries and transition
instructions; configured resource metadata does not establish real dialogue
or playback. The previous structural review missed this distinction.

Five reviewed source keys are now marked placeholder using source-key and
raw-text SHA-256 matches, never broad keyword or character-name filtering.
Retain text, IDs, full resource evidence and source_attribution, remove
actual speaker/cast claims, and render explicit scene-outline labels.
Added placeholder-records.jsonl and regression validation. Updated the
opened final output and matching accuracy output in place with backups in
before_placeholder_review. 165 tests pass; all 57,928 candidate texts, IDs
and destinations still reconcile. No replacement speaker is inferred.

## 2026-10-22 Follow-up: Chapter240 acts 36-37 lack resource linkage

Scenes 124000036/37 retain 9/17 dialogue candidates. Their configured
GalGame asset paths match neither the persistent nor base local catalog;
no cached Perform/Timeline linkage identifies per-line actors or branches.
Scene Name keys list names but do not verify actual cast. Five adjacent
equal pairs and the separate Belle/Wise address versions remain intact.
Playback and placement remain unverified; these are not reviewed outlines.

Render fully unknown, unreferenced scenes with a name-table heading and
an explicit candidate-order notice. Existing referenced or named scenes
retain their presentation. Re-rendered both final TXT outputs and all
chapters with backups in before_unlinked_scene_review; JSONL, CSV and
record text/order/IDs are unchanged. 169 tests pass, including duplicate
and address-version preservation and isolation of scene evidence. Both
full audits report zero export errors or text anomalies; all 57,928
candidate texts, stable IDs and destinations reconcile.

## 2026-10-22 Follow-up: MCP query usability

Updated the sibling ikserver-rs story engine after reproducing strict-AND
and release-alias gaps in failing regression tests. Multi-term searches
try same-document complete matches first, then explicitly labeled partial
matches by default; allowPartial=false retains strict semantics. Path,
scope, speaker, docId and release selectors remain hard constraints.
Reviewed aliases 3.2 -> Chapter230 and 3.3 -> Chapter240 are supported by
catalog, read and search. They mean newly added main story, not the
snapshot version of every chapter. Unknown mappings are never inferred.

31 story end-to-end tests and all-targets compilation/format checks pass.
Local query verification against the current out/zzz_story_3.3.0_chs is
saved in out/search_usability_3.3.0.json. The 3.3 core query returns four
documents/five lines; the three-concept query remains strict-zero but
returns labeled partial candidates by default. Extraction data unchanged;
no upload, deployment, commit or push performed.

## 2026-10-22 Existing-dialogue actor evidence completion

Offline inspection confirmed that bubble assets 40100031 and 4000064 contain
only storySections/storySegment and Speaker A/B slots, without an actor-name
table. Same-resource/section/slot propagation has no unique known-name peer
for the unresolved main-story candidates. Fixed-snapshot NPCSub and main-city
object/graph tables were inspected outside the repository; 458 TextAssets in
the DateIdleMoveToBubble block contain no unresolved main-scene ID match.
Their ShowBubble calls use scoped npcTag/bubbleId parameters, so this pass
does not invent a global slot binding or claim all call sites were recovered.

OngoingTips exact complete voice references identify eight previously unnamed
LuciasFather bubble lines as the displayed “警惕的队长”. Different source wording
is preserved and recorded as speaker_evidence.text_difference; no internal
alias-wide name mapping is added. Conflicting keys and explicit hidden names
remain unresolved. Tip attribution now covers existing partner/street sources
and preserves Perform/Timeline evidence.

MainCityChatTransitionWithActionsNode (nodeType 29) owns
TransitionWithActionsCfg.DialogueKey screen text. Occurrences retain the
playable parent type and classify this validated combination as narration;
unknown child configuration types are not reclassified by name.
See docs/actor-binding-findings-2026-10-22.md for exact keys, sources, hashes
and the limits of the actor-slot search. Focused actor/parser tests pass.

The expanded scan's 26 layout errors are verified null layouts: 24 saved
empty storySections and two sparse node arrays. Preserve empty/partial status
and null node addresses, never jump across holes or use partial graphs to
prove unused copies. Re-scanning the two affected blocks produces 3,925
complete, 24 empty and two partial graphs with no parse errors. Per-target
CAB error collection now preserves successful sibling assets. Resolver cache
fingerprints include the partner/street prefix helpers used for asset scope.

## 2026-10-22 Existing-content completion final

The same 3.3.0 CHS snapshot and CNPRODWin3.3.0 local files now produce
out/zzz_story_3.3.0_chs_completed_v2_20261022 and the matching _audit.
All 13 old input hashes are unchanged; four SMS tables use the same pinned
fd6cb326c07c75f39b0b05845d204302c451ec34 commit.

Partner candidates increase 40,033 -> 53,845 (+13,812), with every old key
and raw text preserved. Street export preserves 24,058 candidates (23,949
retained), including short/repeated sources and 240 legacy Bubble_PasserBy,
activity and enclave sources; 3,561 name/title sources are
metadata. SMS retains 9,925 sources with 8,640 confirmed identities and
1,285 unknown, plus 4,633 extra text sources and 151 attachment sources.
Mixed message/choice references retain occurrence identities but no global
sender claim. Role labels are not character names.

ComicConfig external CAB/PPtr, owned tracks and BubbleEvent UUIDs link
2,452/2,505 existing comic sources; 459 explicit body display names are
confirmed. Animation strings are excluded by field layout, not a blacklist.
One auxiliary Gender source and six empty main sources receive audits.
No source IDs or main/comic export order is rewritten.

Main retained count stays 46,873, with 8 names restored and 57 presentation
lines correctly classified. Existing main names remain intact; unresolved
identity records decrease 2,298 -> 2,233. Ten old partner labels are retracted
(eight unbound slots and two choices), retaining raw text and destinations.

225 tests, Ruff and diff whitespace checks pass. Both verify/content audits
pass with zero text anomalies/export errors. All 57,928 main/supplement
candidates reconcile as 51,478 retained and 6,450 audited removals, plus five
name removals. Extended checks cover lore, SMS/config/items and source audits.
The old baseline remains; no upload, deployment, commit or push is made.
See docs/existing-content-completion-2026-10-22.md for exact output locations
and remaining evidence limits. Game text/research caches remain ignored.
