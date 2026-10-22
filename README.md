# 绝区零剧情文本提取器

从公开 [ZenlessData](https://git.mero.moe/dimbreath/ZenlessData) 和本机《绝区零》资源中提取主线文本，解析逐句说话人，导出可读剧本与带来源证据的 JSONL。也支持设定资料导出、语料校验、版本对比和 [绳网后端](https://github.com/KawaYiLab/ikserver-rs) 上传。

当前工具版本为 **0.3.0**，已验证游戏数据版本为 **3.3.0（CHS）**。输出按章节、内容类型和场景整理；**跨场景播放顺序尚未还原**，不能直接将目录顺序当作剧情时间线。

## 快速开始

需要 Windows 和 Python 3.11+（本仓库使用 Python 3.12 验证）。解析演出资源与配音说话人还需要本机安装游戏；仅提取文本可使用 `--no-speakers`。

在 PowerShell 中运行：

```powershell
git clone https://github.com/KawaYiLab/zzz-story-extractor.git
cd zzz-story-extractor
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m zzz_story doctor
.\.venv\Scripts\python.exe -m zzz_story extract --out out
```

首次运行会下载 TextMap 与配置表，缓存到 `data/cache/3.3.0/`；`doctor` 检查依赖、数据来源、游戏目录和资源索引。已有仓库也可运行 `scripts/setup.ps1` 创建环境、安装依赖并执行诊断。

默认结果写入 `out/zzz_story_3.3.0_chs/`，可从 `story.txt` 或 `chapters/` 开始阅读。安装后也可用 `.\.venv\Scripts\zzz-story.exe` 代替 `python.exe -m zzz_story`。

**每次提取请使用新的输出目录。** 如果目标目录已含正文、设定或清单等产物，工具会在写入前报错；再次提取时换一个 `--out`，例如 `out\run2`。

## 使用

```powershell
# 只提取文本，跳过演出说话人解析与设定导出
.\.venv\Scripts\python.exe -m zzz_story extract --no-speakers --no-lore --out out\textonly

# 只提取指定章节（也支持 --only-chapter 210,220；自动跳过设定导出）
.\.venv\Scripts\python.exe -m zzz_story extract --only-chapter 240 --out out\ch240

# 同时生成 JSONL、TXT 和 CSV（UTF-8 BOM，方便 Excel 打开）
.\.venv\Scripts\python.exe -m zzz_story extract --format jsonl,txt,csv --out out\csv

# 完整性模式：保留双方路线、重复候选及原文，供对账核查
.\.venv\Scripts\python.exe -m zzz_story extract --accuracy-first --out out\audit

# 只导出设定资料
.\.venv\Scripts\python.exe -m zzz_story extract-lore --out out\lore-only
```

常用参数（`extract`）：

| 参数 | 用途 |
| --- | --- |
| `--out PATH` | 输出目录；仅默认值 `out` 会展开为版本子目录，其他路径直接使用 |
| `--data-dir PATH` | 使用本地 ZenlessData，跳过下载 |
| `--game-dir PATH` | 指定 `ZenlessZoneZero Game` 目录，含空格时用引号包裹 |
| `--lang CHS` | TextMap 语言，默认为简体中文；说话人别名映射以中英文数据为基础 |
| `--only-chapter TOKEN` | 按章节 token 筛选，如 `240` 或 `210,220` |
| `--limit N` | 仅处理前 N 个台词键，用于调试 |
| `--format jsonl,txt,csv` | 输出格式，默认为 `jsonl,txt`；后续校验与上传需要 JSONL |
| `--no-speakers` / `--no-lore` / `--no-supplement` | 分别跳过演出说话人解析、设定导出、Comic/CS 补充文本 |
| `--accuracy-first` | 关闭分支与重复候选删减、场景名单推断，并保留原文 |
| `--no-dedupe` | 关闭重复行合并；完整候选核查请使用 `--accuracy-first` |
| `--keep-raw` | 即使清洗前后相同，也写入 `raw_text` |
| `--refresh` / `--refresh-speakers` | 分别重新下载数据、强制重建说话人缓存；仍需新的输出目录 |
| `--require-speakers 0.95` | 最终保留行的配音说话人覆盖率低于阈值时返回退出码 3 |
| `--allow-issues` | 结构校验发现错误时允许命令成功结束，问题仍写入报告 |

查看完整帮助：

```powershell
.\.venv\Scripts\python.exe -m zzz_story --help
.\.venv\Scripts\python.exe -m zzz_story extract --help
```

## 输出文件

| 文件或目录 | 内容 |
| --- | --- |
| `story.jsonl` | 一行一条主线记录，包含文本、说话人、稳定 ID 和来源证据 |
| `story.txt` / `chapters/` | 按章节与场景组织的可读剧本、分章文本 |
| `story.csv` | 可选 CSV，包含逐行字段与 JSON 编码的证据 |
| `supplement.jsonl` / `supplement.txt` | Comic/CS 补充文本，有候选且启用对应格式时生成 |
| `manifest.json` / `coverage.json` | 输入哈希、版本、章节、计数、覆盖率及校验结果 |
| `discarded.jsonl` | 删减候选的原文、来源键、原因与配对证据；完整性模式为空 |
| `speaker-gaps.jsonl` / `placeholder-records.jsonl` | 未解决的说话人记录、已复核的剧情占位说明 |
| `name_candidates.jsonl` | 完整性模式的姓名候选，用于核验姓名条目删减 |
| `lore/` | 代理人、装备、绳网、影院等设定 Markdown，以及互动对白审计 |
| `content-audit.md` / `content-audit.json` | 单独运行内容审计后生成的质量报告 |

字段、排序、覆盖率和删减审计的详细约定见 [数据格式说明](docs/data-format.md)。计数随输入、筛选范围和解析版本变化，请以本次输出的清单为准。

## 校验与版本对比

`extract` 自动校验记录结构，将结果写入 `manifest.json` 和 `coverage.json` 的 `validation`。结构错误或覆盖率未达标时返回退出码 3；命令失败后仍应检查已写出的报告。

```powershell
# 对已完成的输出重新执行结构校验（存在错误时返回退出码 1）
.\.venv\Scripts\python.exe -m zzz_story verify --out out\zzz_story_3.3.0_chs

# 将同一份输入、同一筛选范围的默认输出与完整性输出对账
.\.venv\Scripts\python.exe scripts\check_corpus_integrity.py --output out\zzz_story_3.3.0_chs --audit out\audit

# 检查相邻同文、残留标记及 JSONL/TXT/CSV/分章一致性，写入质量报告
.\.venv\Scripts\python.exe -m zzz_story.content_audit --output out\zzz_story_3.3.0_chs

# 按稳定 line_id 比较两个版本；--examples 0 只显示计数
.\.venv\Scripts\python.exe -m zzz_story diff --old out\zzz_story_3.2.0_chs --new out\zzz_story_3.3.0_chs
```

内容审计可加 `--baseline PATH` 比较旧结果，加 `--cache PATH` 读取 `speakers_cache.json` 中的演出资源清单，检查已解析资源的引用缺口。结构校验与原文对账不能证明候选在游戏中的实际播放关系。

## 上传到绳网后端

`upload` 将 JSONL、清单和 `lore/**/*.md` 打成 gzip 语料包，上传到 [ikserver-rs](https://github.com/KawaYiLab/ikserver-rs)，供剧情库 MCP（`/v1/story/mcp`）检索。需要后端管理员账号或令牌：

```powershell
.\.venv\Scripts\python.exe -m zzz_story upload --out out\zzz_story_3.3.0_chs --server https://your-server.example --account admin@example.com
```

密码默认交互输入，也可从 `IK_PASSWORD` 读取。服务器、账号和令牌分别支持 `IK_SERVER`、`IK_ACCOUNT`、`IK_TOKEN` 环境变量；`--token` 可代替账号密码。

`--save bundle.json.gz` 可同时保存语料包；未指定服务器且未设置 `IK_SERVER` 时，只保存到本地。可读 TXT、分章文本和审计附件不上传。旧输出的小数章节顺序会在打包时统一迁移为整数。

## 范围与已知限制

- 主线正文覆盖 `Main_GalGame`、`Main_Chat`、`Main_BubbleStory`、`Main_Bubble`、`Main_Ongoing*`、`Main_ChatAudio`、`Main_ChatPlus` 和 `MainChat_Chapter*`。活动、支线、代理人秘闻等不进入 `story.jsonl`；设定及代理人互动单独写入 `lore/`。
- 默认偏向男主视角，有明确证据的分支或副本移入删减审计；无法确认的重复与 NPC 台词继续保留。需要双方候选时使用 `--accuracy-first`。
- 原显示名优先于配音别名，隐藏身份不被提前揭示；无法可靠关联的角色保留为空。`line_type=unknown` 不等于“有配音但别名缺失”，覆盖率仅对关联配音的保留行计算。
- 章节内以内容类型、回放档案或来源编号排列，当前跨场景 `chronology_status` 为 `unknown`。局部时间排序只用于证据完整且唯一的单资源、单 section 气泡组。
- Comic 尚无可靠的场景关联；CS 只确认章节关系。它们独立输出，不能按相邻位置串成连续剧情。
- 已复核的编写说明保留为 `placeholder`，原角色标注另存证据。资源节点、配音键或姓名表存在，均不能单独证明它是正式对白或实际被播放。
- 输入下载固定同一上游提交并记录文件哈希；缺少可核验来源时标记 `source_version=unknown`。缓存指纹会随输入与资源元数据变更而重建；保留元数据的二进制改动需手动 `--refresh-speakers`。

## 开发

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

测试使用临时目录与构造数据，无需下载完整语料或安装游戏。缓存、提取产物、构建目录和本地环境文件均由 `.gitignore` 排除。GitHub Actions 在 Windows、Python 3.11/3.12 上运行静态检查和测试。

| 路径 | 职责 |
| --- | --- |
| `zzz_story/cli.py`、`extract.py` | 命令行与提取主流程 |
| `fetch.py`、`textmap.py`、`keys.py`、`chapters.py`、`clean.py` | 数据来源、键解析、章节与文本清洗 |
| `catalog.py`、`mhy1.py`、`odin.py`、`perform*.py`、`timeline.py` | 资源索引、解码、演出节点与时间轴 |
| `speakers.py`、`narrative.py` | 角色归因、内容分类和局部顺序证据 |
| `lore.py`、`writers.py`、`validate.py`、`content_audit.py` | 设定、导出与质量核查 |
| `diff.py`、`upload.py` | 版本对比与语料打包上传 |
| `tests/`、`scripts/`、`reference/` | 回归测试、辅助脚本与算法参考 |

审查证据与历史统计：

- [主线架构检查及后续场景复核](docs/mainline-architecture-review-2026-10-21.md)
- [3.3 全量内容复查](docs/full-content-review-2026-10-21.md)
- [提取稳定性审查](docs/review-2026-10-21.md)
- [3.3.0 资源兼容记录](MODLOG.md)

## 许可与致谢

项目代码采用 [MIT 许可](LICENSE)。游戏文本版权归米哈游所有；本工具用于本地个人研究，请勿分发提取出的游戏文本。

- mhy1 / Perform 算法参考 [simon300000/zenless-voice](https://github.com/simon300000/zenless-voice)（MIT），参考实现位于 `reference/galgame-perform.ts`。
- Oodle 解压依赖 [pyooz](https://pypi.org/project/pyooz/)（GPLv3）；当前安装依赖已包含此包。
- 文本与配置来自 Dimbreath 的 ZenlessData 社区整理，优先使用 [Gitea 镜像](https://git.mero.moe/dimbreath/ZenlessData)，备用 [GitHub 镜像](https://github.com/malu-no996/ZenlessData) 必须包含相同提交。
