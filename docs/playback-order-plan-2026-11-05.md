# 跨场景播放顺序：证据与实施方案

调查日期：2026-11-05。状态：方案与可行性调查，尚未实现跨场景执行图。
游戏与配置版本沿用 3.3.0；ZenlessData 固定提交为
`fd6cb326c07c75f39b0b05845d204302c451ec34`。

## 目标

从任务入口及其触发条件出发，解析演出的执行关系，再按主角、选项和任务状态生成播放事件。
输出应对应一条明确路线的播放顺序。允许自由触发的内容、并行事件和未知条件保留其约束与分支。
这里恢复的是玩家看到剧情的顺序；闪回按其播放位置保留，不重新编排故事世界中的时间线。

## 已核实的现状

| 位置 | 当前行为 | 尚缺信息 |
| --- | --- | --- |
| `zzz_story/extract.py::_line_sort_key` | 章节后先按 `FAMILY_ORDER`，再按档案/来源键和局部行号排列 | 不同资源类型之间的实际调用顺序 |
| `zzz_story/extract.py::_load_archive_order` | 读取回放档案顺序；部分档案 ID 通过数值规则关联已存在的任务 | 任务步骤与演出触发关系；档案位置不能单独证明播放顺序 |
| `zzz_story/perform_graph.py::Graph` | 保留文本 occurrence、节点地址、角色、选项与部分性别分支信息 | 持久化的控制节点、入口、执行边、外部调用和返回点 |
| `zzz_story/perform_graph.py::graph_from_raw` | 局部解释性别条件与部分节点，识别本资源内跳转 | 完整节点语义和外层调度；`GalJumpChapterNode` 当前目标是资源内地址，不能按名称认定为跨章节调用 |
| `zzz_story/narrative.py::annotate_local_order` | 对单资源、单 section、唯一 occurrence 的气泡按时间排序 | 时间轴被哪个事件启动，以及何时完成、返回 |

当前的 `chronology_verified_scenes` 仍为 0。资源成功解析、文本完整对账与执行顺序验证是不同指标。

## 本轮新核实的配置入口

在同一 ZenlessData 提交实际读取了以下表，缓存位于
`data/cache/chronology-research-20261105/`：

- `MainCityQuestTemplateTb.json`：9,764 行，字段大多混淆，需核实任务步骤、状态和资源关联。
- `MainCityGraphConfigTemplateTb.json`：1,998 行，`KEGFAKLAELH` 中存在
  `Assets/NapResources/Data/MainCityNodeGraph/*.json` 路径。
  样本包含约会、移动、气泡等交互流程；已发现路径不等于已确认主线调度器。
- `LevelDataTemplateTb.json`：2,759 行，`CDOIBPMLECB` 包含 `Level/.../*.asset` 关卡资源路径。
- 同时读取 `QuestAccessConfigTemplateTb`、`QuestMappingRuleTemplateTb`、`LevelQuestTemplateTb`，
  作为后续关联检查输入；尚未证明这些表之间的运行时连接。

公开仓库有 `Data/WorldGraph/NodeConfig` 目录，但本次读取的
`MainCity10/NodeConfigMainCity10.json` 仅是一个数值，不含可直接遍历的节点与边。
尚不能认定公开 JSON 已包含完整执行图；下一步应沿已发现的路径检查本机资源。
未知字段需要资源内容与实际播放的交叉验证，不能仅凭字段名、编号相近或值相同建立执行边。

## GitHub 实现参考

本轮实际通过 GitHub API 读取并缓存了以下固定提交的源码；借鉴执行模型，不假设《绝区零》使用相同引擎。

| 来源 | 已核对的机制 | 对本项目的启发 |
| --- | --- | --- |
| [Ink Divert](https://github.com/inkle/ink/blob/35c63e52f1d36060930dc7ed3cfba38ea224b528/ink-engine-runtime/Divert.cs)、[CallStack](https://github.com/inkle/ink/blob/35c63e52f1d36060930dc7ed3cfba38ea224b528/ink-engine-runtime/CallStack.cs)、[写作说明](https://github.com/inkle/ink/blob/35c63e52f1d36060930dc7ed3cfba38ea224b528/Documentation/WritingWithInk.md) | 条件跳转、目标路径、带调用栈的子故事调用与返回 | 同一段剧情可以从不同位置调用；资源顺序无法表达返回位置 |
| [Yarn Spinner VirtualMachine](https://github.com/YarnSpinnerTool/YarnSpinner/blob/c5215f86dd5a6761aecbdc9f60f6a6108f91f919/YarnSpinner/VirtualMachine.cs) | 程序位置、字符串表引用、条件选项、等待选择、节点跳转、Detour 与 Return | 文本字典、执行状态与输出事件分别建模；未知选择不能默认走第一项 |
| [ZenlessData MainCityGraph 配置](https://git.mero.moe/dimbreath/ZenlessData/src/commit/fd6cb326c07c75f39b0b05845d204302c451ec34/FileCfg/MainCityGraphConfigTemplateTb.json)、[LevelData 配置](https://git.mero.moe/dimbreath/ZenlessData/src/commit/fd6cb326c07c75f39b0b05845d204302c451ec34/FileCfg/LevelDataTemplateTb.json) | 同版本流程图与关卡资源路径 | 定位后续需要检查的资源，不能仅凭表的排列推断执行关系 |

## 数据模型

整体链路为：任务/关卡入口 → 条件与动作节点 → 演出调用 → 文本 occurrence。
从完整资源与文本候选建图，路线筛选在建图之后进行。

- **文本来源**：沿用现有 `line_id` / `source_key`，保存原文和译文。
- **静态出现位置**：版本、资源、section、节点、嵌套字段路径/索引。
  同一文本被多个节点引用时分别记录；仅有 `(section, node)` 不足以区分节点内多个文本槽。
- **播放事件**：一次具体路线中对上述位置的一次执行，另记调用上下文和访问序号。
  同一节点在循环或第二次调用中再次播放，应产生新事件。
- **执行关系**：顺序、条件/选项、跳转、调用/返回、事件触发、等待完成。
  每条关系保留原始资源、字段/节点位置、条件与适用版本。
  未核实的目标或语义明确列为缺口。

无台词的节点也必须保留，它们可能负责推进任务、切场景或触发下一段演出。
同步调用需要保存返回点；异步演出需要记录启动与完成/等待关系。
两个时间轴的局部起始时间不能直接互相比大小，并发对白应保留区间或分组。

存在循环、状态条件与调用返回时，不能对全部节点做一次拓扑排序就认定为真实路线。
只沿已解释的语义求取执行关系；状态未知时保留条件分支，不自行补成线性顺序。

## 实施顺序与阶段产物

1. **先证明一条跨场景链能贯通。** 选一章中的一个主线任务，固定版本与主角路线，
   追踪任务入口、第一段演出、结束动作、下一段演出。优先选择包含两种以上资源类型的样本。
   产出资源/字段对应表与已证实、待解析的连接清单。若入口还无法定位，先报告这一缺口，
   不以编号排序填补。
2. **完善资源执行图。** 扩展 `perform_graph.py` 保存节点和边，在专门的任务/关卡适配层解析
   外部触发。现有 Odin、资源目录、occurrence 和角色关联继续复用。
   `GalGame`、`ChatPlus`、过场、漫画等按实际引用连接，各自保留内部结构。
3. **增加路线输出。** 用独立路线解释层生成事件，再由 `narrative.py` / 输出层渲染。
   同时提供带条件的完整图和带路线参数的顺读剧本；缺失连接及未解决分支在输出中可见。
   已验证路线采用执行位置排序；档案排序继续作为明确标识的目录视图。
4. **用实机播放核对后扩展。** 对试点章固定版本、主角、关键选项和任务状态，
   记录场景进入、演出开始/结束、分支汇合的录像或可用日志时间点。
   用这些锚点对照生成的路线；验证范围随具体路线报告，之后再扩展章节与节点类型。

去重按播放事件处理：同一次事件被多个提取通道重复采集可以合并；
同文在不同节点或同节点的两次执行中实际播放，应保留。跨场景排序不能伴随全文同文删除。

## 验收标准

- 试点路线从入口至终点的每个跨场景连接均有配置或实机记录依据，未解释连接数为 0；
  实机记录与静态解析依据分别标注。
- 对照录像/日志的已观测场景顺序无冲突；未观测分支不标为已验证。
- 覆盖选项分支与汇合、外部调用返回、同节点重复执行、缺失目标及并行演出的检查。
- 报告“已解释控制节点 / 发现的控制节点”“已解析目标 / 所有显式引用目标”、
  入口可达覆盖与实机核对路线数，分母及排除项明确。
- 新路线中的文本都能追溯到来源与出现位置；文本未进入某条路线时记录原因，
  不能由单一路线不可达推出该文本从不播放。

在这些条件满足前，可称为部分还原或某条路线已验证，不宣称全游戏存在唯一的完整播放顺序。
