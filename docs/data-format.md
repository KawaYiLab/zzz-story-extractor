# 输出数据格式

本文对应工具 0.3.0、已验证的 3.3.0 数据。计数与质量结论以具体输出目录的 `manifest.json`、`coverage.json` 和审查报告为准。

## 主线记录

`story.jsonl` 使用 UTF-8，一行一个 JSON 对象。以下为字段示例，文本为占位符；实际输出还包含角色、任务和资源证据等字段：

```json
{
  "line_id": "CH240_GalGame_124000040_0001",
  "chapter": "Chapter240",
  "scene": "124000040",
  "family": "GalGame",
  "line_no": 1,
  "sub_no": null,
  "variant": null,
  "speaker": null,
  "speaker_source": "none",
  "speaker_confidence": 0.0,
  "speaker_status": "unresolved",
  "speaker_gap_reason": "no_structured_reference",
  "has_voice": false,
  "text": "示例文本",
  "raw_text": null,
  "source_key": "Main_GalGame_Chapter240_124000040_001",
  "line_type": "unknown",
  "chronology_status": "unknown",
  "line_order_source": "source_key",
  "line_order_status": "unknown"
}
```

### 标识与原文

| 字段 | 含义 |
| --- | --- |
| `source_key` | 原始 TextMap 键，用于追溯输入与跨版本核查 |
| `line_id` | 稳定记录 ID，形如 `CH<章节 token>_<类型>_<场景>_<四位行号>`；可含子编号/变体，不随章节排序变化 |
| `chapter` / `chapter_label` / `chapter_order` | 章节 token、可读标签与排序值 |
| `scene` / `scene_act` / `scene_title` | 来源场景号、导出幕次与可用标题；幕次属于导出顺序 |
| `family` | 内容类型，例如 `GalGame`、`MainChat`、`BubbleStory` |
| `line_no` / `sub_no` / `variant` | 来源键中的行号、子编号与变体 |
| `text` | 清除布局、HTML 等标记后的文本 |
| `raw_text` | 清洗前原文；与 `text` 相同时默认写 `null`，`--keep-raw` 或完整性模式强制保留 |
| `text_variants` | 原文中的男女主角内嵌分支，清洗后两版不同时记录 |
| `order` | 本次导出的全局排列序号 |

`line_id` 标识来源文本，尚未变为实际播放事件 ID。同一文本键可能被多个演出节点引用。

章节编号从第二季起按 `第 N 季第 M 章 → Chapter{(N-1)*100 + M*10}` 推导，例如 `2.1 → Chapter110`、`3.4 → Chapter240`。第一季的非常规 token 保留显式映射。未知 token 保留原值并给出 `unknown-chapter` 警告。

新输出使用整数章节顺序，`manifest.chapter_order_scale=10` 表示排序单位。不要将新整数与旧小数直接混用；上传器会在打包时迁移旧顺序。

### 说话人与内容类型

| 字段 | 含义 |
| --- | --- |
| `speaker` | 原显示名，可能为 `null`；节点显示名优先于配音别名 |
| `speaker_id` | 已确认形态归一后的角色名，属于文本名称，不是游戏数字 ID |
| `speaker_form` | 已确认的服装或形态；不会按名字包含关系随意合并角色 |
| `speaker_alias` | 可用的资源内部配音别名 |
| `speaker_source` | `voice`、`avatar`、`timeline`、`tips`、`scene_alias`、`scene_name` 或 `none` |
| `speaker_confidence` | 解析或推断的置信标记；场景别名与单角色兜底分别为 0.6、0.4 |
| `speaker_status` | `resolved`、`inferred`、`unresolved`、`not_applicable` |
| `speaker_gap_reason` | 未解决原因，例如没有结构化引用、演员槽位未绑定、显示名冲突或配音别名未解 |
| `speaker_slot` | 气泡中的 A/B/C 等局部演员槽位；未绑定时不猜测姓名 |
| `scene_speakers` | TextMap 姓名表清理后的角色候选，已去掉选项、旁白等非角色条目 |
| `has_voice` | 此保留行是否关联配音键；不等于已确认存在录音或运行时播放 |
| `line_type` | `dialogue`、`option`、`narration`、`unknown` 或 `placeholder` |

`scene_alias` 与 `scene_name` 属于推断；完整性模式关闭这些兜底。姓名表只能提供候选，不能单独证明逐句说话人或实际出场。整幕缺少结构化引用且角色未知时，TXT 会提示这些候选尚未核实。

`line_type=unknown` 包括角色未解、整个场景缺少说话人数据等情况，不能全部归因为配音别名缺失。旁白与玩家选项可以没有说话人。

已逐项复核的剧情编写说明使用 `content_status=reviewed_placeholder`、`line_type=placeholder`，移除对白署名，原角色字段保存在 `source_attribution`，核查依据保存在 `content_evidence`。分类绑定来源键与原文哈希，原文改变后需要重新核查。

### 资源与顺序证据

| 字段 | 含义 |
| --- | --- |
| `perform` | 已读取的演出关联、角色与分支证据 |
| `perform.occurrences` | 每次文本引用的资源、section、节点位置、类型、姓名键、配音、演员绑定与时间字段 |
| `timeline` | 经场景号、字幕号及文本验证的 ChatPlus 时间轴关联，包含 M/F 路线及可用的 `copy_of` |
| `order_source` / `archive_order` | 场景排序的依据与回放档案位置 |
| `chronology_status` | 当前均为 `unknown`，跨场景播放顺序仍未确认 |
| `line_order_source` / `line_order_status` | 默认 `source_key` / `unknown`；证据完整且唯一的气泡组为 `perform_time` / `within_section` |
| `quest_id` / `quest_name` / `quest_source` | 可核验的任务关联及来源；不能查到名称时不保留旧式任务编号推断 |

章节内按内容类型分块，GalGame 场景优先使用回放档案排列，缺失条目使用来源编号插入或兜底。档案顺序、数组位置和键编号均不能单独证明实际执行顺序。

`timeline.text_difference=true` 表示主文本与时间轴字幕不同，正文继续保留主文本。不会用旧时间轴字幕自动替换新文本。

## 补充文本与设定

- `Comic_*` 使用 `context_status=unlinked`，尚无可靠的场景或播放关联，每条独立展示来源。
- `CS_*` 使用 `context_status=chapter_only`，只确认所属章节。季章 token 通过与正文相同的规则推导，避免章节改号后跨季挂载。
- 补充文本 ID 为 `SUP_<source_key>`，新增条目不会重编号。旧 `SUP00001` 等编号应通过来源键迁移。
- `lore/` 导出设定 Markdown；代理人互动的 `lore/agents/dialogue-audit.jsonl` 保留来源键、原文、角色、资源证据与路线去向。

## 活动、支线与代理人故事

`extra.jsonl` 收录主线以外的剧情文本，字段与主线记录相同（空字段省略），另加 `domain`：

| `domain` | 来源键族（示例） |
| --- | --- |
| `activity` 活动剧情 | `Activity_<类型>_<活动>_…`、`ActivityChat_*`、`ActivityBubble_*`、`GalGame_<活动>_…`、`TL_Activity*` |
| `side` 支线委托 | `Side_<类型>_<支线>_…`、`SideChat_*`、`SideBubble_*`、`PhotoSideChat_*` |
| `companion` 代理人故事 | `Companion_<类型>_<代理人>_…`、`CompanionChat_*`、`GalGame_Chapter<代理人>_…`、`PartnerDate_*` |
| `hollow` 空洞事件 | `AutoEvent<事件>_<行>`、`InLevel_<类型>_…` |
| `other` 其他剧情 | `Other_*`、`Store_*`、`StoreChat_*`、`Enclave*` |
| `legacy` 旧版文本 | `Galgame_*`（小写 g）、`Chat_Chapter*`；未确认是否仍在游戏中出现 |

- `chapter` 是来源分组 `<domain>.<标签>`，如 `activity.SayItWithFlowers`；`chapter_label` 为 `活动剧情 · SayItWithFlowers`，绑定主线章节的支线表复用章节名。`chapter_order` 从 1,000,000 起按域分段，排在主线之后。
- `line_id` 为 `EX_<source_key>`，新增条目不会重编号。组内按类型、场景号、行号排列，`chronology_status=unknown`、`context_status=source_key_only`。
- `speaker` 来自共享的演出/配音索引（需本机游戏），或空洞事件正文中的 `名字：「…」`（`speaker_source=inline`）；其余保持为空，`line_type=unknown`。`_Name` 键只写入 `scene_speakers`。
- 默认模式丢弃有男主原键的 `…F` 女主副本和同场景相邻同文，写入 `extra-discarded.jsonl`；完整性模式全部保留。
- `extra.txt` 是按域、分组、场景排版的可读版本。`--no-extra` 跳过；`--only-chapter`、`--limit` 时不生成。

键族归属由 `zzz_story/content.py` 的登记表统一判定。每次提取写出 `content-coverage.json`：各域键数、字数，以及形似对白但未登记的键族（`unclassified`）。版本更新后可单独运行 `python -m zzz_story coverage` 检查新键族。

Season 1 的过场演出使用不带 `Main_` 前缀的 `GalGame_Chapter<数字>_<场景>_<行>`，现由主线流程收入 `story.jsonl`（`family=GalGame`）。`Chapter010`、`Chapter030` 与 `Chapter01`、`Chapter03` 共用章节名和排序位置。

## 默认模式与完整性模式

默认模式偏向男主视角。明确女主路线、已验证的未使用副本，以及符合既有配对规则的分支或重复候选移入 `discarded.jsonl`。无法严格确认的重复、NPC 同文与独立对白继续保留。

`--accuracy-first` 保留双方来源分支、重复候选和清洗前原文，关闭场景名单猜测，另生成 `name_candidates.jsonl`。它用于核验候选完整性，不能保证候选均为正式内容。

删减记录包括原文、来源键、稳定 ID、原因和 `paired_source_key`，可用时附带相似度。`record_kind` 区分 `line` 与 `name`；统计分别给出 `discarded_lines`、`discarded_names` 和 `discarded_entries`。完整性模式的删减文件为空。

`scripts/check_corpus_integrity.py` 要求两份输出具有相同输入哈希、语言和筛选范围，核查候选是否全部进入正文或删减审计、原文是否保留、稳定 ID 是否漂移。设定互动存在时也核查其候选与去向。

## 清单与覆盖率

`manifest.json` 记录输入文件的 SHA-256、数据版本、语言、本机游戏版本、提取参数、计数、章节表与校验结果。缓存中的 `source_provenance.json` 绑定上游提交及文件哈希，只有来源核验通过才使用版本标签；旧 `source_version.txt` 仅作为历史提示。

`coverage.json` 提供逐类型与逐章计数、配音说话人覆盖率、删减统计和缺口汇总：

- `voice_linked` / `voice_speaker` 只计算最终保留行；实际配音角色缺口为两者之差。
- `speaker_stats.unresolved_aliases` 与 `ambiguous` 属于资源扫描统计，可能包含主线以外内容，不可直接作为正文缺口。
- `attribution` 按 `speaker_status`、缺口原因和内容类型汇总。
- `by_chapter` 以章节 token 为键，显示标签见 `chapters` 表。
- `quality` 包含档案覆盖、任务关联和未关联漫画数量。
- `validation` 记录错误、警告和逐项问题，包括重复/缺失 ID、空正文、章节标签冲突、补充文本跨季挂载及占位说明署名。

所有覆盖率与结构检查均针对提取候选及已读取资源。恢复真实分支播放、跨场景顺序和漫画关联仍需要额外的演出执行证据或游戏实录。
