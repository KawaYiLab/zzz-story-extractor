# 绝区零主线剧情文本提取器

从本机《绝区零》3.2.0 游戏资源 + 公开 ZenlessData 中提取主线剧情全文，并按“章节 → 场景 → 台词”排序；能解析游戏 Perform 资源中的 voiceKey，为每句有配音的台词补上说话人。

## 产出

默认目录：`out/zzz_story_3.2.0_chs/`

| 文件 | 内容 |
| --- | --- |
| `story.jsonl` | 一行一句；含章节、场景、行号、说话人、文本、原始 TextMap 键、性别分支 |
| `story.txt` | 按章节/场景分组的可读剧本 |
| `supplement.jsonl` / `supplement.txt` | `Comic_*`、`CS_*` 补充文本（可选） |
| `manifest.json` | 数据版本、来源哈希、计数、章节表（序号/标签/行数）、校验结果 |
| `coverage.json` | 说话人覆盖率、未解析别名、缺失文本、去重统计、校验结果（`by_chapter` 以章节 token 为键，标签见 `manifest.json` 的 `chapters`） |

实测 3.2.0 结果：45,376 条主线台词，20+ 章节；其中 32,931 条带说话人（Perform voiceKey 解析 21,842 条、探索提示配置补 3,795 条、头像名与场景推断补足其余）。有 voiceKey 的台词说话人覆盖率 **100%**。旁白、无配音选项、未解析 NPC 允许 `speaker=null`，并在 `coverage.json` 中单独统计。

每章内部按内容类型分块排列（GalGame 主线 → 主线聊天 → 聊天 → 气泡 → 关卡内对话等）；GalGame 场景按游戏内“剧情回放”档案的官方顺序排列，并按官方任务名分节。类型之间的时间交错关系在公开数据中不存在，不做臆测。

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

## 使用

先检查环境：

```powershell
.\.venv\Scripts\python.exe -m zzz_story doctor
```

正常会看到：

- TextMap/FileCfg 缓存就绪；
- 本机游戏目录和 `CNPRODWin3.2.0`；
- 资源目录块 `1677012929.blk`；
- 约 30,000 条主线 Perform 资源映射到 17 个 block。

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
```

重新下载 TextMap 或重建说话人缓存：

```powershell
.\.venv\Scripts\python.exe -m zzz_story extract --refresh --refresh-speakers --out out
```

## 校验输出

```powershell
.\.venv\Scripts\python.exe -m zzz_story verify --out out/zzz_story_3.2.0_chs
```

`extract` 结束时会自动跑同一套校验，结果写进 `coverage.json` 和 `manifest.json` 的 `validation` 字段；出现 `error` 级问题时默认以退出码 3 失败，加 `--allow-issues` 可以保留输出继续用。

校验目前覆盖：

- `supplement-chapter-shadow`：补充文本被挂到主线章节号上、但标题对不上——章节重新编号后最容易出的错（见下）；
- `duplicate-line-id`：`line_id` 重复；
- `chapter-label-conflict`：同一个章节 token 出现多个标题；
- `unknown-chapter`：章节 token 不在 `chapters.py` 表内（warning，按编号规则推导标签）。

## 章节编号

3.2.0 的规则是 `第N季 第M章 -> Chapter{(N-1)*100 + M*10}`：`2.1 -> Chapter110`、`3.1 -> Chapter210`、将来的 `3.4 -> Chapter240`。

`CS_*` 过场字幕的键名只带一个「季.章」前缀（如 `CS_21_01_010` 表示 2.1），所以以前靠手写映射表。3.2.0 把第二季从 2xx 挪到 1xx 之后，旧表仍把 `CS_21..25` 指向 `Chapter210..250`，结果第二季 1–5 章的过场字幕全部挂到了第三季 1–3 章上（等 3.4 上线时 `Chapter240` 还会再撞一次）。现在第二季以后统一由 `chapters.season_chapter_token()` 推导，第一季的非常规 token（`01.5`、`028`、`05.2`…）保留显式映射；`verify` 会在同类问题再次出现时直接报错。

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
- `--server`、`--account`、`--token` 也可以用环境变量 `IK_SERVER`、`IK_ACCOUNT`、`IK_TOKEN`。

## 数据来源

- 文本与配置：Gitea 镜像 `https://git.mero.moe/dimbreath/ZenlessData`（3.2.0，优先），备用 GitHub 镜像 `https://github.com/malu-no996/ZenlessData`。除 TextMap 外还使用 PerformTemplateTb、ArchivePerformTemplateTb（剧情回放顺序）、QuestConfigTemplateTb（任务名）、OngoingTipsConfigTemplateTb（关卡内对话说话人）等配置表。
- 本地游戏：自动探测 `D:\米哈游\miHoYo Launcher\games\ZenlessZoneZero Game`、HoYoPlay 常见目录和注册表；也可用 `--game-dir`。
- 说话人：读取本地游戏的资源目录块和 17 个 Perform block，解析 `dialogueKey` 与 `externalVoiceKey/voiceKey`，再用 AvatarBase + 英文 TextMap 把内部别名映射成中文名。
- 缓存默认位于 `data/cache/3.2.0/`。

## JSONL 字段

```json
{
  "line_id": "CH17_110_GalGame_11100060_001",
  "chapter": "Chapter110",
  "chapter_label": "第二季 第一章 云霞同归处",
  "chapter_order": 17,
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

- `speaker_source`：`voice`（voiceKey 解析）/ `avatar`（Perform 节点头像名）/ `tips`（探索提示配置，主要是关卡内对话）/ `scene_alias`（场景名单推断）/ `scene_name`（单角色场景兜底）/ `none`。
- `quest_name`：GalGame 场景所属的官方任务名（来自剧情回放档案 + 任务配置），不属于任何任务时为 `null`。
- `speaker_confidence`：1.0（AvatarBase/英文名精确映射）、0.6（场景别名推断）、0.4（单名兜底）、0（未解析）。
- `text_variants`：原文同时包含男/女主角分支且两版不同时才有值；`text` 固定为男主（哲）版本，只提取男主视角。女主（铃）作为 NPC（妹妹）出现在台词中。
- `line_type`：`dialogue`（有说话人）/ `option`（玩家选项）/ `narration`（场景有说话人数据，但这一行没有）/ `unknown`（有配音但没解析出说话人，或整个场景缺说话人数据，如 Bubble、Ongoing 系列）。
- `scene_speakers`：该场景 `_Name_*` 提供的角色名单，已去掉“选项”“旁白”等非角色项。

## 范围与限制

- 只提取主线：
  - `Main_GalGame`、`Main_Chat`、`Main_BubbleStory`、`Main_Bubble`、`Main_Ongoing*`、`Main_ChatAudio`、`Main_ChatPlus`、`MainChat_Chapter*`。
  - 活动、支线、代理人秘闻、PartnerTalk、绳网 Message 等默认不进入 `story.jsonl`。
  - `Comic_*`、`CS_*` 放入 supplement，不混入主线章节。
  - 测试/占位表 `Chapter020`、`Chapter080`、`PortChapter110` 以及 `MainChat_2_*` 已排除。
- 说话人只对“有 voiceKey 的台词”计算覆盖率；聊天、旁白、无配音选项本来就没有 voiceKey，允许为空。
- 部分 NPC 的内部别名和英文名对不上，会被列为未解析别名；不会凭空猜测。
- 只提取男主（哲）视角：以 `F` 结尾的女主分支键、女主版本的重复台词、以及含“师妹/铃小姐”等女主称呼且存在男主对应版本的台词都会被移除；“师弟/哲先生”这类男主称呼以及称呼潘引壶等 NPC 为“师弟”的台词全部保留。
- 去重只合并主角双分支留下的重复行（两套分支段落、相邻重复）；NPC 在同一场景重复说的短句（如“……”）会保留。
- 章节标签与顺序来自 `chapters.py` 的 3.2.0 表；新版本出现未知 token 时保留原 token 并按同一套编号规则推导标签，不会丢数据，校验里会给出 `unknown-chapter` 警告。
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
  perform.py    Perform CAB 字符串扫描
  speakers.py   voice 别名 → 中文名、缓存
  extract.py    主流程
  validate.py   输出结构校验（章节挂载、重复 id）
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
