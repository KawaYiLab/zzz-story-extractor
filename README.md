# 绝区零主线剧情文本提取器

从本机《绝区零》3.3.0 游戏资源 + 公开 ZenlessData 中提取主线剧情全文，并按“章节 → 场景 → 台词”排序；能解析游戏 Perform 资源中的 voiceKey，为每句有配音的台词补上说话人。

## 产出

默认目录：`out/zzz_story_3.3.0_chs/`

本次全量检查后的结果在 `out/zzz_story_3.3.0_chs_complete/`，完整性审计版在 `out/zzz_story_3.3.0_chs_complete_audit/`。检查报告为 `content-audit.md` / `content-audit.json`。旧输出保留不覆盖。

| 文件 | 内容 |
| --- | --- |
| `story.jsonl` | 一行一句；含章节、场景、行号、说话人、文本、原始 TextMap 键、性别分支 |
| `story.txt` | 按章节/场景分组的可读剧本 |
| `supplement.jsonl` / `supplement.txt` | `Comic_*`、`CS_*` 补充文本（可选） |
| `manifest.json` | 数据版本、来源哈希、计数、章节表（序号/标签/行数）、校验结果 |
| `coverage.json` | 说话人覆盖率、未解析别名、缺失文本、去重统计、校验结果（`by_chapter` 以章节 token 为键，标签见 `manifest.json` 的 `chapters`） |
| `name_candidates.jsonl` | 完整性模式的姓名来源键与原文，用于核验姓名删减 |
| `discarded.jsonl` | 每条启发式删减的原文、来源键、原因、配对来源键与可用的相似度；完整性校对模式不删减 |
| `content-audit.md` / `content-audit.json` | 全量相邻同文、资源覆盖缺口、角色缺口、格式一致性与版本前后对比 |
| `lore/agents/dialogue-audit.jsonl` | 代理人互动候选的原文、来源键、角色、资源证据及路线删减记录 |

本机 3.3.0 全量检查后：47,625 条主线台词，其中 34,518 条带说话人；另有 4,605 条补充文本。配音说话人覆盖为 19,976 / 19,986（约 99.95%），仍有 10 条未解析。新增结构化读取也计入以前漏报的 Timeline 配音键，因此缺口与旧结果不可直接比较。旁白、无配音选项、未解析 NPC 允许 `speaker=null`。

3.3 新增 `Chapter240`「第三季 第四章 重返天空的旅程」，默认输出 2,197 条主线台词。完整性模式共 53,141 条主线、4,787 条补充。两种输出均通过结构校验和候选原文保留核对。

此前已修复 `Chapter210` 第 55 幕「烈火与缰绳」漏读 ChatPlus 时间轴的问题，现为 42 行，均有角色标注、无相邻同文。此次全量复查继续读取 2,213 个配置对应的 Odin 演出资源，新增 1,713 条明确性别路线与 9 条未使用副本移入审计，恢复 407 条误删候选，保留正文无改写。普通与图片式对白的显示姓名优先于配音别名，避免泄露「？？？」的身份。

代理人互动另有 40,033 条带来源审计的候选，其中 1,077 条明确女主路线不在默认文档重复显示；姓名键不再混入对白，不同偶遇事件分别展示。设定标题中的代理人、音擎、邦布和收藏品数量改为实际计数。

全量扫描不代表所有运行时内容已核实。主线仍有 317 组相邻同文（159 组长度至少 12 字），包括选项与回答、真实停顿，以及资源不完整的场景；这些不作全局去重。188 个场景存在部分文本未被已读取资源引用，可能涉及旧文本、子剧情或外部资源，逐项清单见检查报告。

每章内部按内容类型分块排列（GalGame 主线 → 主线聊天 → 聊天 → 气泡 → 关卡内对话等）；GalGame 场景使用“剧情回放”档案表排列，缺失场景按来源编号插入。这个排列没有被证实为实际播放顺序，不能直接用来建立剧情时间线。旧版任务编号推导只有能查到名称时才保留，较新章节可能没有任务分节。

每行增加 `order_source`、`chronology_status`、`archive_order`、`quest_id` / `quest_source`，说明排列和关联的依据；当前 `chronology_status` 均为 `unknown`。`manifest.json` 与 `coverage.json` 的 `quality` 给出档案覆盖、任务关联和未关联漫画数量。

`speaker` 保留原显示名，`speaker_id` 是已知形态归一后的角色名（不是游戏角色数字 ID），`speaker_form` 记录服装/形态。仅归一已确认的主角服装和明确列出的形态，不按名字包含关系合并角色。补充文本的 `line_id` 改为 `SUP_<source_key>`，插入新条目不会重编号；旧的 `SUP00001` 引用需通过来源键迁移。

`Comic_*` 目前没有可靠的场景与播放关系，标记为 `context_status=unlinked`，不能按相邻位置拼接台词。`CS_*` 只确认所属章节，标记为 `chapter_only`。恢复真实顺序和漫画场景关联仍需额外的演出节点或游戏实录证据。

## 安装

需要 Windows + Python 3.11/3.12。

```powershell
cd C:\Users\Administrator\Documents\GitHub\zzz-story-extractor
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

也可以直接运行：

```powershell
.\scripts\setup.ps1
```

从旧工具升级时，先运行 `.\.venv\Scripts\python.exe -m pip install -e .` 安装新增的 UnityPy 依赖，再执行提取；3.2 缓存和输出保留在原目录。

## 使用

先检查环境：

```powershell
.\.venv\Scripts\python.exe -m zzz_story doctor
```

正常会看到：

- TextMap/FileCfg 缓存就绪；
- 本机游戏目录和 `CNPRODWin3.3.0`；
- 资源目录块 `2837526243.blk`（本机优先使用 `Persistent/Blocks` 的更新版本）；
- 31,098 个 Perform 路径中 30,765 个匹配到本机索引，映射到 20 个 block。路径集合也包含活动和支线；TextMap 主线筛选决定最终输出。

完整提取：

```powershell
.\.venv\Scripts\python.exe -m zzz_story extract --out out
```

常用参数：

```powershell
# 不解析说话人，速度最快
.\.venv\Scripts\python.exe -m zzz_story extract --no-speakers --out out\textonly

# 只处理前 200 句，方便调试
.\.venv\Scripts\python.exe -m zzz_story extract --limit 200 --out out\sample

# 额外输出 CSV（UTF-8 BOM，方便 Excel）
.\.venv\Scripts\python.exe -m zzz_story extract --format jsonl,txt,csv --out out\csv

# 使用已克隆的 ZenlessData，跳过下载
.\.venv\Scripts\python.exe -m zzz_story extract --data-dir D:\ZenlessData --out out

# 指定游戏目录
.\.venv\Scripts\python.exe -m zzz_story extract --game-dir "D:\米哈游\miHoYo Launcher\games\ZenlessZoneZero Game" --out out

# 覆盖率低于 95% 时以退出码 3 失败
.\.venv\Scripts\python.exe -m zzz_story extract --require-speakers 0.95 --out out

# 保留与正文相同的 raw_text（文件大约翻倍）
.\.venv\Scripts\python.exe -m zzz_story extract --keep-raw --out out\full

# 只抽某一章（约 4 秒；写到独立目录，自动跳过 lore）
.\.venv\Scripts\python.exe -m zzz_story extract --only-chapter 230 --out out\ch230

# 完整性校对：保留双方分支与重复候选、保留原文；写到独立目录
.\.venv\Scripts\python.exe -m zzz_story extract --accuracy-first --out out\audit
```

重新下载 TextMap 或重建说话人缓存：

```powershell
.\.venv\Scripts\python.exe -m zzz_story extract --refresh --refresh-speakers --out out
```

## 校验输出

```powershell
.\.venv\Scripts\python.exe -m zzz_story verify --out out/zzz_story_3.3.0_chs_complete
```

`extract` 结束时会自动跑同一套校验，结果写进 `coverage.json` 和 `manifest.json` 的 `validation` 字段；出现 `error` 级问题时默认以退出码 3 失败，加 `--allow-issues` 可以保留输出继续用。

同一份输入和筛选范围分别生成默认输出和 `--accuracy-first` 输出后，可核对每条候选的原文和稳定 ID 是否保留或进入删减审计；完整性输出另含 `name_candidates.jsonl`，用于核验姓名删减：

```powershell
.\.venv\Scripts\python.exe scripts\check_corpus_integrity.py --output out\zzz_story_3.3.0_chs_complete --audit out\zzz_story_3.3.0_chs_complete_audit

# 检查全文重复信号、乱码、TXT/CSV/分章一致性，并生成逐项报告
.\.venv\Scripts\python.exe -m zzz_story.content_audit --output out\zzz_story_3.3.0_chs_complete --baseline out\zzz_story_3.3.0_chs --cache data\cache\3.3.0\source-17a3b9e1104b63e3\speakers_cache.json
```

删减审计用 `record_kind` 区分台词与场景姓名条目；统计分别给出 `discarded_lines`、`discarded_names` 和总条目 `discarded_entries`。

校验目前覆盖：

- `supplement-chapter-shadow`：补充文本被挂到主线章节号上、但标题对不上——章节重新编号后最容易出的错（见下）；
- `duplicate-line-id`：`line_id` 重复；
- `chapter-label-conflict`：同一个章节 token 出现多个标题；
- `unknown-chapter`：章节 token 不在 `chapters.py` 表内（warning，按编号规则推导标签）。

## 版本对比

```powershell
.\.venv\Scripts\python.exe -m zzz_story diff --old out\zzz_story_3.2.0_chs --new out\zzz_story_3.3.0_chs
```

按 `line_id` 逐行比较两个输出目录，给出每章的新增 / 删除 / 修改计数和前几条样例（`--examples 0` 只看计数）。`line_id` 只依赖章节 token，所以新版本在中间插入章节也不会把旧行误判成变化。

## 章节编号

3.2.0 起的规则是 `第N季 第M章 -> Chapter{(N-1)*100 + M*10}`：`2.1 -> Chapter110`、`3.1 -> Chapter210`、`3.4 -> Chapter240`。

`CS_*` 过场字幕的键名只带一个「季.章」前缀（如 `CS_21_01_010` 表示 2.1），所以以前靠手写映射表。3.2.0 把第二季从 2xx 挪到 1xx 之后，旧表仍把 `CS_21..25` 指向 `Chapter210..250`，导致字幕跨季挂载。现在第二季以后统一由 `chapters.season_chapter_token()` 推导，第一季的非常规 token（`01.5`、`028`、`05.2`…）保留显式映射；`verify` 会在同类问题再次出现时直接报错。3.3 快照没有 `CS_34_*` 条目，不会凭空生成新章字幕。

## 上传到论坛后端（剧情库 MCP）

提取结果可以一键上传到绳网后端（[ikserver-rs](https://github.com/KawaYiLab/ikserver-rs)），供剧情总结 AI 通过 MCP
（`/v1/story/mcp`）检索与顺读。需要管理员账号：

```powershell
$env:IK_PASSWORD = "管理员密码"   # 不设则交互输入
.\.venv\Scripts\python.exe -m zzz_story upload --server https://ik.tiwat.cn --account 管理员邮箱
```

- 读取 `--out` 指向的输出目录（默认与 `extract` 相同）：`story.jsonl`、`supplement.jsonl`、`manifest.json`、`lore/**/*.md`，
  打成 gzip 压缩的语料包（3.2.0 全量约 5 MB）后上传；`story.txt`、`chapters/` 等可读版本不上传。
- 服务端校验并建好索引后立即生效，无需重启；同一份数据重复上传不会多存一份；服务端保留最近 5 个版本可回滚。
- 用 `--token` 代替账号密码（已有管理员令牌时）；`--save bundle.json.gz` 同时把语料包存到本地。
- 旧版补充文本含浮点 `chapter_order` 时，上传会自动将整包章节顺序等比例转成整数，保留间章顺序，无需重新提取。
- `--server`、`--account`、`--token` 也可以用环境变量 `IK_SERVER`、`IK_ACCOUNT`、`IK_TOKEN`。

## 数据来源

- 文本与配置：Gitea 镜像 `https://git.mero.moe/dimbreath/ZenlessData`（3.3.0，优先），备用 GitHub 镜像 `https://github.com/malu-no996/ZenlessData`。下载固定同一提交；备用镜像必须含该提交才可用，不回退到较旧版本。除 TextMap 外还使用 PerformTemplateTb、ArchivePerformTemplateTb（剧情回放顺序）、QuestConfigTemplateTb（任务名）、OngoingTipsConfigTemplateTb（关卡内对话说话人）等配置表。
- 本地游戏：自动探测 `D:\米哈游\miHoYo Launcher\games\ZenlessZoneZero Game`、HoYoPlay 常见目录和注册表；也可用 `--game-dir`。
- 说话人：读取本地游戏的资源目录块和 20 个 Perform block，解析 `dialogueKey` 与 `externalVoiceKey/voiceKey`，再用 AvatarBase + 英文 TextMap 把内部别名映射成中文名。3.3 的资源索引位于 mhy1 加密的 Unity 容器，使用 UnityPy 定位对象并读取新表布局；仍支持旧版独立 gzip 索引。索引与 Perform 块优先从 `Persistent/Blocks` 读取，再回退到 `StreamingAssets/Blocks`。
- ChatPlus 时间轴：从资源清单定位配置中的 prefab 路径，再读取 `ChatPlusDialogClip` 的头像、字幕键与语音键。对应关系需通过场景编号、字幕编号和文本一致性验证；两套时间轴均存在时才标注路线。当前为三个主线场景补上 148 个候选键，不代表全部时间轴已经覆盖。
- 缓存默认位于 `data/cache/3.3.0/`；下载先固定上游提交并保存 `source_provenance.json`（提交、版本、文件哈希）。`source_version` 只在哈希核验通过时使用；旧缓存的 `source_version.txt` 仅是历史提示，缺少可核验来源时标为 `unknown`。说话人缓存绑定 TextMap、别名解析代码、Perform、游戏版本、两处资源目录及版本清单的路径/大小/修改时间，变更会自动重建；二进制修改若保留所有文件元数据，需 `--refresh-speakers`。

## JSONL 字段

```json
{
  "line_id": "CH110_GalGame_11100060_001",
  "chapter": "Chapter110",
  "chapter_label": "第二季 第一章 云霞同归处",
  "chapter_order": 170,
  "scene": "11100060",
  "family": "GalGame",
  "line_no": 1,
  "sub_no": null,
  "variant": null,
  "speaker": "橘福福",
  "speaker_alias": "JuFufu",
  "speaker_confidence": 1.0,
  "speaker_source": "voice",
  "text": "……",
  "raw_text": "……",
  "text_variants": null,
  "source_key": "Main_GalGame_Chapter110_11100060_001",
  "line_type": "dialogue",
  "scene_speakers": ["橘福福", "铃", "哲"],
  "order": 1
}
```

说明：

- `has_voice`：该保留行是否关联配音；`coverage.voice_linked` 与 `voice_speaker` 使用最终保留行计数。
- `speaker_source`：`voice`（voiceKey 解析）/ `avatar`（Perform 节点头像名）/ `timeline`（ChatPlus 时间轴显示角色）/ `tips`（探索提示配置，主要是关卡内对话）/ `scene_alias`（场景名单推断）/ `scene_name`（单角色场景兜底）/ `none`。
- `timeline`：仅验证通过的行含此字段，记录字幕键、语音键、时间轴名称、`sides`（M/F 路线）及可用的 `copy_of`。`text_difference=true` 表示主文本与时间轴字幕不一致，正文仍保留主文本。第 55 幕的 `_014`、`_069`、`_077` 存在断句或称呼差异，不自动以旧字幕替换新文本。
- `quest_name`：GalGame 场景所属的官方任务名（来自剧情回放档案 + 任务配置），不属于任何任务时为 `null`。
- `speaker_confidence`：1.0（AvatarBase/英文名精确映射）、0.6（场景别名推断）、0.4（单名兜底）、0（未解析）。
- `text_variants`：原文同时包含男/女主角分支且两版不同时才有值；`text` 默认选择哲版本；`--accuracy-first` 保留来源分支。不确定的重复候选保留，默认输出并非严格单一路线。女主（铃）作为 NPC（妹妹）出现在台词中。
- `raw_text`：清洗前的 TextMap 原文；与 `text` 完全一致时写 `null`（约 95% 的行如此），`--keep-raw` 可强制保留。
- `line_id`：`CH<章节 token>_<类型>_<场景>_<行号>`，只依赖 token，不随章节顺序变化；插入新章节不会让旧 id 漂移。
- `line_type`：`dialogue`（有说话人）/ `option`（玩家选项）/ `narration`（场景有说话人数据，但这一行没有）/ `unknown`（有配音但没解析出说话人，或整个场景缺说话人数据，如 Bubble、Ongoing 系列）。
- `scene_speakers`：该场景 `_Name_*` 提供的角色名单，已去掉“选项”“旁白”等非角色项。

## 范围与限制

- 只提取主线：
  - `Main_GalGame`、`Main_Chat`、`Main_BubbleStory`、`Main_Bubble`、`Main_Ongoing*`、`Main_ChatAudio`、`Main_ChatPlus`、`MainChat_Chapter*`。
  - 活动、支线、代理人秘闻、PartnerTalk、绳网 Message 等默认不进入 `story.jsonl`。
  - `Comic_*`、`CS_*` 放入 supplement，不混入主线章节。
  - 测试/占位表 `Chapter020`、`Chapter080`、`PortChapter110` 以及 `MainChat_2_*` 已排除。
- 说话人只对“有 voiceKey 的台词”计算覆盖率；聊天、旁白、无配音选项本来就没有 voiceKey，允许为空。
- `line_type=unknown` 表示“这一行没解析出说话人”。本次默认输出有 3,088 行，实际配音角色缺口为 10 行，不能全部归因于别名表缺失。
- `coverage.speaker_stats.unresolved_aliases` 指“有配音、有别名、但仍映射不到中文名”的资源条目，包含主线外内容；`ambiguous` 指没有唯一可用说话人的配音条目，保留行的实际缺口以 `voice_linked - voice_speaker` 为准。
- 部分 NPC 的内部别名和英文名对不上，会被列为未解析别名；不会凭空猜测。
- 默认以男主（哲）视角筛选，不能确认的候选保留：以 `F` 结尾的女主分支键、女主版本的重复台词、以及已知同说话人、措辞完全一致且仅称呼不同的明确地址对会被移除；经验证的时间轴女主路线和未使用副本也会移入审计。男主对应台词与没有严格配对证据的 NPC 台词保留。
- 分支折叠同时覆盖马甲形态：启动时从 TextMap 的 `GalNPC<形态>Belle` 名字自动推导形态表（当前为 玩家/学生/道士/泳装/佩洛伊斯，取不到时回退到内置列表），按“哲侧 / 铃侧”配对，仅在台词完全一致时丢掉铃侧那一行；铃作为妹妹的独立对白不受影响。`门铃` 这类道具名不会被误判；出现未登记的新形态（`X哲`+`X铃` 成对）会在抽取日志里 warning。
- 去重只合并已知相反主角在邻近行说出的相同台词；NPC 在同一场景重复说的短句（如“……”）会保留。
- 章节标签与顺序来自 `chapters.py` 的 3.3.0 表（含 `Chapter240`）；新版本出现未知 token 时保留原 token 并按同一套编号规则推导标签，不会丢数据，校验里会给出 `unknown-chapter` 警告。
- 游戏文本版权归米哈游所有；本工具只用于本地个人研究，请勿分发提取出的游戏文本。

## 开发与测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

项目结构：

```text
zzz_story/
  fetch.py      数据下载、缓存、游戏目录探测
  textmap.py    TextMap 合并
  keys.py       TextMap 键解析
  chapters.py   章节顺序和标签
  clean.py      性别分支/布局标记/HTML 标记清洗
  mhy1.py       mhy1 容器解密（移植自 zenless-voice，MIT）
  catalog.py    gzip 资源目录解析与 asset → block 映射
  timeline.py   ChatPlus 时间轴角色与主文本分支对应
  perform.py    Perform CAB 字符串扫描
  odin.py       有边界校验的 Odin 二进制数据读取
  perform_graph.py  配置资源与明确性别分支证据
  content_audit.py  全文质量与导出格式一致性审计
  speakers.py   voice 别名 → 中文名、缓存
  extract.py    主流程
  validate.py   输出结构校验（章节挂载、重复 id）
  diff.py       两个输出目录的逐行对比
  writers.py    JSONL/TXT/CSV 输出
  upload.py     打包语料并上传到论坛后端（剧情库 MCP）
  cli.py        命令行
reference/
  galgame-perform.ts   mhy1/Perform 算法的参考实现（MIT）
```

## 致谢

- `mhy1`/Perform 解析算法参考 `simon300000/zenless-voice`（MIT）。
- Oodle 解压使用 `pyooz`（GPLv3 依赖，单独安装；如不接受该许可，可改用 `kraken_decompressor` 或 Node `ooz-wasm` 辅助脚本）。
- 数据结构参考 Dimbreath 的 ZenlessData 社区整理。

## 目录复用与审查

提取与设定导出需要新的输出目录。已有 story/supplement、chapters、lore 或 manifest 等产物时会在写入前报错，防止混入旧补充文件或把旧 JSONL 配上新清单。无需删除旧结果，换一个 `--out` 即可。

新清单的 `chapter_order_scale=10` 明确章节排序单位，禁止把新整数和旧小数混用。打包和后端直读均支持旧小数顺序；缺少比例标记的旧包按全包检测迁移，有自定义混合数据时应先修正清单。

默认输出保留不确定的重述、未知说话人与 NPC 重复。目录相邻不代表实际播放关系；Comic 每条独立显示来源，不能串成连续剧情。
