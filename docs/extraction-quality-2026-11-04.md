# GitHub 实现对照与提取质量改进

日期：2026-11-04。输入为同一份已校验的 ZenlessData 3.3.0 和本机 CNPRODWin3.3.0 资源，451,194 个 TextMap 键。基线为本轮修改前的 `6444187`，在相同机器重新全量提取；未覆盖原有用户输出。

## 查阅的项目与采用方式

以下源码均实际从 GitHub 读取，并固定到当次查阅的提交。

| 项目与源码 | 已核对的做法 | 本项目采用方式 |
| --- | --- | --- |
| [Trafilatura 去重文档](https://github.com/adbar/trafilatura/blob/1622ce88ef0da929b21724078f8a425e4f753def/docs/deduplication.rst)、[实现](https://github.com/adbar/trafilatura/blob/1622ce88ef0da929b21724078f8a425e4f753def/trafilatura/deduplication.py) | 区分完全重复与相似内容；重复检查有最小长度、次数参数；可使用独立缓存隔离不同提取批次 | 保留场景/类型边界与每次调用独立状态；短句、停顿、NPC 复读不凭同文自动删除 |
| [DataTrove 精确去重](https://github.com/huggingface/datatrove/blob/384d81c011fda5cf54be3ba1d58967c21fafe25d/src/datatrove/pipeline/dedup/exact_dedup.py)、[句段去重](https://github.com/huggingface/datatrove/blob/384d81c011fda5cf54be3ba1d58967c21fafe25d/src/datatrove/pipeline/dedup/sentence_dedup.py) | 候选签名、重复查找、过滤分阶段；可按优先级保留文档；三句窗口；可另存删减内容 | 共用演出证据筛选器；三行窗口只用于报告；删减保留原文、资源证据、最终配对与中间链 |
| [DataTrove 文本归一化](https://github.com/huggingface/datatrove/blob/384d81c011fda5cf54be3ba1d58967c21fafe25d/src/datatrove/utils/text.py) | 归一化可分别控制数字、大小写、标点、空白及附加符号 | 段落比较只使用 NFC 和空白归一化，保留数字、标点、角色、选项类型；正文不采用比较用归一化结果 |
| [zenless-voice 演出关联](https://github.com/simon300000/zenless-voice/blob/771b3124759d7a8fc39433a3bac40427524aae08/galgame-perform.ts) | 对话键关联配音来源；严格/回退候选分开；多候选关联保留歧义 | 延续本仓库现有的资源关联方式，精确键优先，等强度姓名冲突保留未知；扩展已实现的结构化节点解析范围 |

Trafilatura 和 DataTrove 用作成熟文本处理方案参考；zenless-voice 用作同游戏格式参考。本次没有引入这些项目的新运行依赖，也没有把网页/训练语料的全文相似删除规则直接用于剧情。

## 实际修复

- **语言覆盖顺序**：完整中文表作为回退，然后应用目标语言的基础表与覆盖表。本地 29 个英文值此前被中文覆盖表盖掉；核查全部 445,022 个 EN 值均保持目标语言优先。读取支持 UTF-8 BOM，同一文件内冲突的重复键报错，避免静默丢值。
- **文本清洗**：使用平衡括号解析嵌套布局/性别分支，保留 `{0}` 参数；保留未知尖括号字面量，识别换行及 `noparse`。注音由两层标记转换为“正文（注音）”，原文另存。21 条含布局和格式参数的实际文本均通过检查，其中原先漏解的 6 条包含嵌套括号。
- **资源覆盖**：通过统一内容登记表纳入活动、支线、代理人等 Chat/Bubble 配置资源，复用现有 Odin/Perform 解析器。缓存版本升级，清洗器和内容登记表纳入缓存指纹。
- **角色归因**：精确文本键优先于别名键；等强度姓名冲突不按字典序任选。场景推断只接受同类型、同场景内唯一别名/姓名配对；结构化缺口不被场景猜测覆盖。主线外姓名按来源性别渲染，保留“？？？”显示身份。
- **分支与重复**：主线外保留 `perform`、`timeline` 和归因状态，使用共用的互相配对分支证据。空基础键不再导致女主文本丢失；复制记录不得跨场景、行类型或未选中的文本变体合并。公共路线上的主角对白得到保护，称呼启发式限定邻近行。字幕同文和兄妹称呼变化不再单独作为删除依据。
- **可复现性**：固定活动命名的任务证据选择顺序，消除同输入在不同进程中由集合遍历顺序造成的审计差异。
- **审计闭环**：连续过滤的 `paired_source_key` 追溯至最终保留来源，中间关系保存在 `paired_source_chain`。`verify`、默认提取校验、原文对账均覆盖 `extra.jsonl`。内容审计增加主线外导出比对、角色标记检查和重复段落检测。

## 同输入全量对比

| 指标 | 修改前 | 修改后 |
| --- | ---: | ---: |
| 解析的结构化演出资源 | 17,935 | 29,535 |
| 主线保留行 | 51,450 | 51,911 |
| 补充文本保留行 | 4,605 | 4,787 |
| 主线外保留行 | 111,669 | 107,626 |
| 主线外正文携带演出/时间轴证据 | 0 | 89,130 |
| 主线外按结构化分支筛去 | 0 | 4,204 |
| 主线外相邻同文组 | 1,690 | 744 |
| 主线、补充、主线外相邻同文组合计 | 2,040 | 1,600 |
| 主线外姓名残留性别标记 | 706 | 0 |

主线外相邻同文组减少 **56.0%**；全部叙事域合计减少 **21.6%**。这是扫描到的同文组数变化，不是人工标注的错误率。

恢复的候选共 **800 条**：主线 461、补充 182、主线外 157。它们缺少充分的互斥/副本证据，不应仅因文本重复而删除。主线外新筛出的 4,204 条中，4 条此前已被相邻同文规则筛去，因此相对基线新增移出正文为 4,200 条。

主线外在两版共同保留的来源中，新增 874 条有姓名记录，共有 1,591 条姓名变化（含标记渲染、隐藏身份和结构化显示名调整）。共同保留正文中仅主线的 4 条注音排版发生变化；补充及主线外正文变化均为 0。

## 验证与产物

- 269 项回归测试通过，新增 31 项；Ruff 和 `git diff --check` 通过。
- 默认版与完整性版共 **176,428 条**主线、补充、主线外候选，完整对账：164,324 条正文 + 12,104 条删减；另有 5 条姓名删减。
- 所有候选均有去向，原文一致，保留记录稳定 ID 一致；台词删减均指向最终保留来源。完整性模式无台词删减。
- 两种模式结构校验均为 0 错误、0 警告；JSONL/TXT/CSV/分章/主线外文本导出一致，残留标记及替换乱码扫描为 0 项。
- 设定互动 53,845 条、街头候选 24,058 条、短信 9,925 条，以及配置事件和附件来源一并通过原有对账。

本机结果：

- `out/quality-baseline-20261104/`：修改前基线。
- `out/quality-verified-20261104/`：最终默认输出；`content-audit.json`、`quality-comparison.json`、`integrity-check.json` 为详细证据。
- `out/quality-final-audit-20261104/`：最终完整性输出。

复现时使用新的输出目录：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -X utf8 -m zzz_story extract --out out\quality-new --format jsonl,txt,csv
.\.venv\Scripts\python.exe -X utf8 -m zzz_story extract --accuracy-first --out out\quality-new-audit --format jsonl,txt,csv
.\.venv\Scripts\python.exe -X utf8 scripts\check_corpus_integrity.py --output out\quality-new --audit out\quality-new-audit
.\.venv\Scripts\python.exe -X utf8 -m zzz_story.content_audit --output out\quality-new --cache data\cache\3.3.0\speakers_cache.json
```

最终仍保留 744 组主线外相邻同文、677 组主线相邻同文、179 组补充同文和 30 组重复段落供核对；这些可能包含选项回声、真实复读或未解分支。原有 6 条空主线源文本与跨场景播放顺序缺口仍存在。没有运行时标注集，本轮不宣称已测得总体语义错误率。
