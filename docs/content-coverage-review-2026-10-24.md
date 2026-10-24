# 内容覆盖检查（2026-10-24）

## 结论

旧流程只读 `Main_`、`MainChat_`、`Comic_`、`CS_` 四个前缀，主线外剧情几乎全部缺失，主线本身也漏了第一季过场演出。
线上剧情库 MCP（`corpusRevision=corpus_v1_7f9b…c56d`，3.3.0）检索以下原文均为零命中：

| 检索词 | 来源键 | 内容 |
| --- | --- | --- |
| `交通科` | `GalGame_Chapter050_010_*` | 第一季第五章过场 |
| `分拣录像带` | `GalGame_ChapterMana_01_*` | 猫又代理人故事 |
| `苦情慢歌` | `Side_Chat_ZenkovS1_*` | 支线委托 |
| `伊卡罗` | `Activity_Chat_MegaRobot_Chapter2_*` | 限时活动 |
| `安比空洞求生记录` | `Galgame_Chapter0_*` | 旧版序章文本 |

本次改动后，五个检索词在本地构建的语料中均能命中。

## 数据规模

以下数字来自 GitHub 镜像 [malu-no996/ZenlessData](https://github.com/malu-no996/ZenlessData) 当前快照
（该镜像尚停在 3.2.0，438,030 个 CHS 键），只用于判断量级；3.3.0 的实际计数以提取清单为准。

| 内容域 | 键数 | 字数 | 去向 |
| --- | ---: | ---: | --- |
| `main` 主线 | 62,347 | 1,448,615 | `story.jsonl` |
| `activity` 活动剧情 | 58,737 | 1,325,874 | `extra.jsonl`（新增） |
| `side` 支线委托 | 23,742 | 523,435 | `extra.jsonl`（新增） |
| `companion` 代理人故事 | 18,303 | 415,868 | `extra.jsonl`（新增） |
| `hollow` 空洞事件 | 12,664 | 341,419 | `extra.jsonl`（新增） |
| `other` 其他剧情 | 4,082 | 74,883 | `extra.jsonl`（新增） |
| `legacy` 旧版文本 | 3,207 | 65,644 | `extra.jsonl`（新增） |
| `lore` 代理人互动、路人、绳网 | 92,665 | 1,772,285 | `lore/` |
| `supplement` CS / Comic | 4,733 | 70,821 | `supplement.jsonl` |

主线外剧情约 275 万字，接近主线的两倍。按同一份数据、无游戏资源（`--no-lore`）提取：

- `story.jsonl` 从 50,477 行增至 55,745 行。`diff` 结果为 +5,268、-0、~0，新增全部来自第一季
  `GalGame_Chapter000/01/010/02/025/03/030/040/050`。`Main_GalGame` 在第一季第一至第五章没有键。
- `extra.jsonl` 共 108,125 行、284 个来源分组：活动 52,390、支线 20,852、代理人故事 16,507、
  空洞事件 12,370、其他 3,432、旧版 2,574。删减 1,414 条女主副本和 1,794 条相邻同文，均写入 `extra-discarded.jsonl`。
- 上传包 gzip 后 9.1 MB，服务端上传上限为 64 MB。

## 架构调整

旧流程的问题是“提取哪些键”分散在 `extract.py` 的前缀判断、`lore.py` 的 `startswith` 和 `speakers.py` 里。
新版本由 [`zzz_story/content.py`](../zzz_story/content.py) 统一登记：

1. 通用语法 `{Category}_{Kind}_{Tag}_{Scene}_{Line}` 按 `Category` 归域；旧式键（`GalGame_Chapter*`、`SideChat_*`、
   `CompanionChat_*`、`AutoEvent*`、`TL_*` 等）单列规则。
2. `coverage_report` 统计各域键数、字数，并列出形似对白却未登记的键族。提取时写出 `content-coverage.json`，
   `python -m zzz_story coverage` 可在下载数据后单独运行。新版本新增键族时，从这里发现缺口，不需要再靠检索抽查。
3. [`zzz_story/extras.py`](../zzz_story/extras.py) 是独立模块，不改动主线的分支、配对与去重流程。它和主线共用演出/配音说话人索引：
   提取时把主线外候选键加入 `text_keys`，本机有游戏时逐句署名会一并解析。

后端（ikserver-rs `crates/story`）新增 `DocKind::Event` / `GroupKind::Event`：语料包可选字段 `extra`，
分组 ID 为 `ev:<domain>.<标签>`，`scope=event`（别名 `活动`、`支线`、`代理人故事`）筛选。
根目录把数百个活动分组合成一行汇总，`ik_catalog(scope="event")` 再逐组列出。旧语料包缺少 `extra` 时照常加载。

## 已知限制与后续

- 活动分组名由 `event_names.py` 按证据推断（见数据格式说明）。公开数据没有“对白标签 → 活动名”的对照表：
  `ActivityInfo`、`ActivityDesign` 等配置表不含名称，`PerformTemplateTb` 只把场景号映射到资源路径。
  按 3.2 数据，活动组命名 40/151、覆盖 25,801/53,785 行；支线组命名 5/53。其余保留内部标签，不猜测。
  任务名换算（场景号 // 10000 等）只在任务名前缀与某个活动标题一致、且至少两个场景一致时采用。
- 无本机游戏资源时，主线外剧情只有空洞事件的行内署名（约 330 行）有说话人。默认去重只合并同场景相邻同文，
  不做主线那种分支路线判定。
- `legacy` 域（`Galgame_Chapter0/1`、`Chat_Chapter*`）可能是早期测试版文本，标注为“旧版文本”，没有确认是否上线。
- 仍未登记的对白类键族主要是技能、成就、提示等界面文本（`Bangboo_*`、`Partner_*`、`Tips_*` 等），以及少量
  `Chat_Avatar_*`、`Bubble_Avatar_*`。可从 `content-coverage.json` 的 `unclassified` 逐项复核。
- `extract.py` 的 `extract()` 仍是 600 多行的单函数。下一步可以按“候选收集 → 署名 → 过滤 → 排序 → 写出”拆成阶段，
  主线和主线外共用同一组阶段接口。本次没有动它，因为没有本机游戏资源，无法对说话人与分支过滤做回归核对。
