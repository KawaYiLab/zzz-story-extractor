# 主线提取架构检查

## 结论

当前架构能收集主线候选文本，但尚不能将所有候选还原为连续、单一路线的剧情。
核心问题是把 TextMap 键当作台词播放事件：正文按章节、内容类型、场景、键编号排列，
演出资源主要用于补角色与过滤性别分支，没有完整解释任务触发、条件、跳转与外部演出。
顺序错乱与角色缺失有共同的资源关联缺口，也各有独立原因。

输入为已核验的 ZenlessData 3.3.0 与本机 CNPRODWin3.3.0。
基线为 `out/zzz_story_3.3.0_chs`；新默认与完整性输出分别为
`out/architecture_review_final_3.3.0` 和 `out/architecture_review_final_3.3.0_audit`。
原输出保留。

## 用户指出的第 32 幕：资源标注不等于正式对白

进一步核对 Chapter240 的 `124000032`、`124000033`、`124000034` 后发现：
共 5 条正文是会客室总结、调查结果概述、过渡到回忆等编写说明。
它们的姓名键确实为“安比”，第 32 幕的原始节点 actorId=1011、头像键为 Anbi；
第 32～33 幕共 4 条还填有 Anbi 配音键。三幕没有回放档案条目，标题值为空；
第 33～34 幕使用相同图片背景资源。资源字段吻合不能证明这些概述是安比的正式台词，
配音键存在也不能证明实际有录音或该节点会被游戏播放。

上一轮把结构化字段已关联当作足够依据，遗漏了文本是否为正式内容的核对。
现保留 5 条文本及稳定 ID，改为 `line_type=placeholder`、
`content_status=reviewed_placeholder`，移除对白署名和出场名单；
原始安比标注保存在 `source_attribution`，完整 Perform 节点证据继续保留。
这表示已核对的剧情占位说明，不指定另一个说话人，也不宣称资源不可达。

检查规则绑定来源键和原文 SHA-256。未来原文改变或其他正常安比对白不会自动被改类；
其他疑似编写说明尚未批量分类。新增 `placeholder-records.jsonl` 供单独核查。
已同步更新用户打开的 story.txt 以及默认/完整性 JSONL、CSV、分章、清单和审计；
改前文件保存在各目录的 `before_placeholder_review/`。

本次复核后 165 项测试通过，候选原文、稳定 ID 与去向对账通过。
下文的 80 条补名等数字是上一轮历史结果；本次另将 5 条“安比对白”纠正为占位说明，
默认正文仍有 46,873 条记录，其中带角色署名为 33,859 条，未标识仍为 2,298 条。

## 用户指出的第 36～37 幕：未关联演出的对白候选

Chapter240 的 `124000036` 有 9 条候选，内容涉及三台终端与中央电梯权限；
`124000037` 有 17 条候选，内容涉及巢主空洞与罗塞塔数据的来源。
它们在 PerformTemplateTb 中有同名 GalGame asset 配置，但这些路径在本机更新版、
基础版 `2837526243.blk` 索引中均未匹配；缓存也没有逐句 Perform/Timeline 引用。
标题、简介值为空，无回放档案条目。没有配音关联不能证明实际没有配音。

两幕的姓名只来自 TextMap `_Name_*` 表，不足以确定逐句角色或实际出场。
第 36 幕保留 001/002、005/006、008/009 三组相邻同文及 004 的短句；
第 37 幕保留 005/006、013/014 两组同文，003/004 分别称呼铃和哲。
分支、播放及先后仍未核实，不能按语意补角色、删除重复，或将两幕改类为占位说明。

TXT 渲染现在对整幕均缺结构化引用且说话人未知的姓名表使用“姓名表”标题和候选提示，
避免“出场”及相邻排列让读者误以为已还原连续播放。已同步默认与完整性 story.txt
和全部分章；JSONL、CSV、来源键、原文及记录顺序不变。改前文本与审计保存在
各输出目录 `before_unlinked_scene_review/`。169 项测试通过，包含候选展示、同文及
称呼版本保留、混合证据与跨类型场景隔离。两份输出的导出错误和文本异常均为 0；
57,928 条候选、原文、稳定 ID 及去向对账通过。

## 已确认问题与修复

| 问题 | 证据与处理 |
| --- | --- |
| 主线先按类型分块，不能代表执行顺序 | `extract._line_sort_key` 优先使用 FAMILY_ORDER，随后按档案/键编号排列；跨场景 chronology_status 继续标为 unknown |
| 键编号与真实局部先后相反 | `Main_Chat_Chapter01_40100031_03` 的 StartTime=0，`_01`=3000，`_02`=6000；现按时间排列。另修复 Chapter120 的 `809234000` |
| 气泡字段漏读 | 1,277 个 GalBubbleStoryNode 使用 Speaker / Text / Voice，旧解析只读取小写字段；现保留槽位、文本、配音、起止时间与位置 |
| 旧聊天未进入结构化解析 | 主线资源扫描发现 14,650 个 MainCityChatPlayStoryNode，没有 sectionIdx/subSectionIdx；现用数组位置定位，读取同节点字段 |
| 过滤规则误删真实名字 | “咨询”“购买”“找零”是「141」商店邦布的名字；移出全局排除表，恢复 28 条已保留台词的名字 |
| 字段布局不同 | 黑屏使用 dialogueKeys 列表；PlayChatPlusStoryNode 使用 NpcName / DialogueKey / ExternalVoiceKey；均加入类型解析 |
| 已有配音但别名未解 | 补 Timeline_Csr、OngoingLevel、ChatPlus、BubbleStory_Bubmale 命名布局，明确 Play_/Stop_ 音效事件不计配音 |
| 旁白/屏幕表现被当成缺角色 | 使用 GalSwitchSceneNode、GalSubNarratorNode 等类型证据；隐藏姓名且无 actor_id、speaker_binding、配音的聊天单列为无显示名表现 |
| 相同角色的姓名键不同 | 爱芮的头像名键与场景名键解析为相同显示名；比较解析后的名字，避免误判冲突 |
| 归档插值可能反向 | 数值相邻场景在档案表中反向出现时，原算法可产生负步长；现无有效区间就进入来源编号兜底 |
| 同场景号跨类型共享幕次 | scene_act 的场景身份加入 family |

## 数据模型与边界

新增 `perform.occurrences`：逐次保留资源、section、node、节点类型、文本字段、
显示名键、配音键、选项/旁白标识、actor_id、speaker_binding、角色槽位和起止时间。
同一文本键被引用多次时保留多个 occurrence，不再仅以引用集合表示资源。
正文 line_id 仍表示来源文本，尚未切换为播放事件 ID。

新增 `speaker_status`（resolved / inferred / unresolved / not_applicable）、
`speaker_gap_reason` 和 `speaker_slot`。`speaker-gaps.jsonl` 保留每条未解决记录及证据；
清单与覆盖率的 attribution 按原因、类型统计。A/B/C 是局部演员槽位，不能直接猜成姓名。

`line_order_source=perform_time` 与 `line_order_status=within_section` 仅表示局部时间依据。
726 个场景组满足完整、唯一、单资源单 section 的气泡时间条件，其中实际有 2 个场景
改变了保留台词的相对先后。多资源、多次引用、多 section 或未完整引用时继续按来源键排列。
数组位置本身没有被当成完整执行顺序，跨场景 chronology_status 仍为 unknown。

## 全量验证

- 161 项测试通过；默认及完整性输出通过结构校验。
- 候选仍为 53,141 条主线、4,787 条补充，共 57,928 条。
- 默认保留 46,873 条主线、4,605 条补充；6,450 条台词与 5 条姓名进入删减审计。
- 与基线相比恢复 121 条候选，873 条原保留台词移入审计：871 条明确性别路线、2 条主角同文配对。
- 共同保留记录原文变化为 0；原文、稳定 ID、候选去向与配对来源全部对账通过。
- 80 条原本无角色的保留台词恢复名字；已有非空角色标注丢失 0 条；另有 1 条“哲”细化为“学生哲”。
- unknown 从 3,088 降到 2,298。共同保留的原 unknown 中，65 条补齐姓名，722 条有资源依据改为 narration；另有 3 条移入分支审计。80 条补名包括原 narration 候选。
- 结构化引用覆盖 39,829 条保留主线，基线为 22,891 条；5,781 个主线及关联 GalGame 资源解析失败为 0。
- 默认配音关联 21,402 条，21,356 条有名字。46 条无名字中，43 条继续等待角色关联，3 条是旁白/屏幕表现。新分母包含此前漏读的配音，不能直接与旧版 10 条缺口比较。
- TXT、CSV、分章与 JSONL 重渲染一致，文本异常与导出错误为 0。
- 代理人互动仍有 40,033 条候选，两种模式原文、来源键全部对账，默认删减仍为 1,077 条。

剩余 unknown 的原因：

| 原因 | 行数 |
| --- | ---: |
| 已知局部角色槽位，尚未绑定姓名 | 1,203 |
| 没有已读取的结构化引用 | 947 |
| 已读节点，但缺显示名或角色绑定未解析 | 143 |
| 不同资源显示名冲突 | 4 |
| 显示名原文无法解析 | 1 |

这是候选文本的覆盖情况，不等于游戏遗漏台词数。开发占位、旧文本与没有证据的旁白/对白
判断仍需核对。默认仍有 310 组相邻同文、188 个部分引用场景，未用全文去重掩盖缺口。

## 后续架构

应以“任务/剧情入口 → 资源 → 播放节点 → 文本引用”为主模型，TextMap 作为文本字典。
资源解析层保留条件、跳转、选项、外部调用与角色绑定；文本 ID 与播放事件 ID 分开，
同文多次播放保留为不同事件。当前 occurrence 是这一层的基础，尚未完整构建执行图。

角色按同节点显示名、局部绑定与明确配音来源逐层解析。气泡 A/B/C 的姓名需查调用场景、
关卡实体或相关角色表；不能从台词内容猜测。缺引用项继续进入独立审计，不因没引用就删除。

顺读输出应由任务触发与执行边生成，选择明确主角和选项路径，未知条件保留分支。
仅有回放档案时提供目录视图。验证还应检查跳转目标、入口可达性、分支返回、角色绑定作用域
和重复执行。当前验证证明保存与局部解析行为，不能证明完整运行时主线已经恢复。

## 复现

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
.\.venv\Scripts\python.exe -X utf8 -m zzz_story extract --out out\new_default --format jsonl,txt,csv
.\.venv\Scripts\python.exe -X utf8 -m zzz_story extract --accuracy-first --out out\new_audit --format jsonl,txt,csv
.\.venv\Scripts\python.exe -X utf8 scripts\check_corpus_integrity.py --output out\new_default --audit out\new_audit
.\.venv\Scripts\python.exe -X utf8 -m zzz_story.content_audit --output out\new_default --cache data\cache\3.3.0\speakers_cache.json
```
