# 绝区零主线剧情文本提取器 + MCP 剧情库

从本机《绝区零》3.2.0 游戏资源 + 公开 ZenlessData 中提取主线剧情全文，并按“章节 → 场景 → 台词”排序；能解析游戏 Perform 资源中的 voiceKey，为每句有配音的台词补上说话人。

在文本提取之外，额外提供一个**只读 MCP 剧情库**，接口参考 akasha 的 `books / catalog / search / read / skill`，方便 AI 按章节检索和引用原文。

## 产出

默认目录：`out/zzz_story_3.2.0_chs/`

| 文件 | 内容 |
| --- | --- |
| `story.jsonl` | 一行一句；含章节、场景、行号、说话人、文本、原始 TextMap 键、性别分支 |
| `story.txt` | 按章节/场景分组的可读剧本 |
| `story.sqlite` | MCP 用的只读索引（`build-db` 生成） |
| `supplement.jsonl` / `supplement.txt` | `Comic_*`、`CS_*` 补充文本（可选） |
| `manifest.json` | 数据版本、来源哈希、计数、本地游戏版本 |
| `coverage.json` | 说话人覆盖率、未解析别名、缺失文本、去重统计 |

实测 3.2.0 结果：约 46,500 条主线台词，20+ 章节；有 voiceKey 的台词说话人覆盖率约 **95.6%**。旁白、无配音选项、未解析 NPC 允许 `speaker=null`，并在 `coverage.json` 中单独统计。

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

# 主角性别分支：F（铃，默认）/ M（哲）/ BOTH（两版都输出）
.\.venv\Scripts\python.exe -m zzz_story extract --protagonist BOTH --out out\both

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

## MCP 剧情库

接口参考 akasha，保留同样的使用节奏：先 `zzz_search` / `zzz_books` 定位，再 `zzz_read` 读原文。

```powershell
# 1. 从 story.jsonl + supplement.jsonl 构建只读 SQLite
.\.venv\Scripts\python.exe -m zzz_story build-db

# 2. 启动 streamable-http MCP（给 dsh-mcp-client 这类客户端用）
.\.venv\Scripts\python.exe -m zzz_story mcp --transport streamable-http --port 8765

# 或者 stdio（由 MCP 客户端拉起进程）
.\.venv\Scripts\python.exe -m zzz_story mcp --transport stdio
```

MCP 工具：

| 工具 | 用途 |
| --- | --- |
| `zzz_books` | 按章节标题 / token 检索章节，返回 `doc_id`、行数、场景数 |
| `zzz_catalog` | 查看章节目录；传 `chapter` / `pathHash` 列出该章场景 |
| `zzz_search` | 全文检索台词，返回章节、场景、行号、说话人、命中片段；可 `pathHash` 限定章节 |
| `zzz_read` | 按 `doc_id` / 章节 token / 章节标题读取原文，`offset` 从 1 开始 |
| `zzz_skill` | 返回 search / storytelling / subtext 的使用指引 |

默认只检索主线，`includeSupplement=true` 时把 `Comic`/`CS` 补充文本也纳入检索。

客户端配置参考 [mcp.example.yaml](<C:/Users/Administrator/Documents/GitHub/zzz-story-extractor/mcp.example.yaml>)：

```yaml
- insert:
    id: mcp-zzz-story
    name: '@deepseek-ai/dsh-mcp-client'
    config:
      serverName: zzz-story
      transport: streamable-http
      url: http://127.0.0.1:8765/mcp
```

`zzz_search` 的返回示例：

```text
[zzz_search] keyword='星见雅'，命中 24 行，22 个场景

## 第一季 第五章 | 场景 0069（MainChat）
doc_id: doc_0adc413b19e4（可用 zzz_read 读取整章）
- L0631 【未标注】星见雅凝视着兄妹二人，似乎识破了言语中的敷衍之意。…
```

## 数据来源

- 文本与配置：Gitea 镜像 `https://git.mero.moe/dimbreath/ZenlessData`（3.2.0，优先），备用 GitHub 镜像 `https://github.com/malu-no996/ZenlessData`。
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

- `speaker_source`：`voice`（voiceKey 解析）/ `scene_alias`（场景名单推断）/ `scene_name`（单角色场景兜底）/ `none`。
- `speaker_confidence`：1.0（AvatarBase/英文名精确映射）、0.6（场景别名推断）、0.4（单名兜底）、0（未解析）。
- `text_variants`：原文同时包含男/女主角分支且两版不同时才有值；默认 `text` 是女主人公（铃）版本。
- `line_type`：有说话人时为 `dialogue`，否则为 `unknown`（不再强行把无配音行标成旁白）。
- `scene_speakers`：该场景 `_Name_*` 提供的角色名单，已去掉“选项”“旁白”等非角色项。

## 范围与限制

- 只提取主线：
  - `Main_GalGame`、`Main_Chat`、`Main_BubbleStory`、`Main_Bubble`、`Main_Ongoing*`、`Main_ChatAudio`、`Main_ChatPlus`、`MainChat_Chapter*`。
  - 活动、支线、代理人秘闻、PartnerTalk、绳网 Message 等默认不进入 `story.jsonl`。
  - `Comic_*`、`CS_*` 放入 supplement，不混入主线章节。
  - 测试/占位表 `Chapter020`、`Chapter080`、`PortChapter110` 以及 `MainChat_2_*` 已排除。
- 说话人只对“有 voiceKey 的台词”计算覆盖率；聊天、旁白、无配音选项本来就没有 voiceKey，允许为空。
- 部分 NPC 的内部别名和英文名对不上，会被列为未解析别名；不会凭空猜测。
- 章节标签是 3.2.0 的内置映射；新版本出现未知 token 时保留原 token 并推导标签，不会丢数据。
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
  writers.py    JSONL/TXT/CSV 输出
  db.py         JSONL → 只读 SQLite 索引
  mcp_server.py MCP 剧情库（books/catalog/search/read/skill）
  cli.py        命令行
reference/
  galgame-perform.ts   mhy1/Perform 算法的参考实现（MIT）
mcp.example.yaml       MCP 客户端配置示例
```

## 致谢

- `mhy1`/Perform 解析算法参考 `simon300000/zenless-voice`（MIT）。
- Oodle 解压使用 `pyooz`（GPLv3 依赖，单独安装；如不接受该许可，可改用 `kraken_decompressor` 或 Node `ooz-wasm` 辅助脚本）。
- 数据结构参考 Dimbreath 的 ZenlessData 社区整理。
