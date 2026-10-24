# 2026-10-22 短信配置补齐与独立复核

本次使用 ZenlessData 3.3.0 的同一提交
`fd6cb326c07c75f39b0b05845d204302c451ec34`。先通过仓库 tree API 分页确认表名，
再读取该提交的原始 JSON。正式提取输入通过 `fetch.REQUIRED_FILES` 与来源清单绑定；
研究目录中的临时下载不作为隐式输入。

## 配置来源

| 文件 | 行数 | 来源 |
| --- | ---: | --- |
| MessageConfigTemplateTb.json | 12,205 | [固定提交原文](https://git.mero.moe/dimbreath/ZenlessData/raw/commit/fd6cb326c07c75f39b0b05845d204302c451ec34/FileCfg/MessageConfigTemplateTb.json) |
| MessageGroupConfigTemplateTb.json | 928 | [固定提交原文](https://git.mero.moe/dimbreath/ZenlessData/raw/commit/fd6cb326c07c75f39b0b05845d204302c451ec34/FileCfg/MessageGroupConfigTemplateTb.json) |
| MessageNPCTemplateTb.json | 199 | [固定提交原文](https://git.mero.moe/dimbreath/ZenlessData/raw/commit/fd6cb326c07c75f39b0b05845d204302c451ec34/FileCfg/MessageNPCTemplateTb.json) |
| MessageItemConfigTemplateTb.json | 74 | [固定提交原文](https://git.mero.moe/dimbreath/ZenlessData/raw/commit/fd6cb326c07c75f39b0b05845d204302c451ec34/FileCfg/MessageItemConfigTemplateTb.json) |

## 字段证据及解析边界

| 表及字段 | 已核对的关系 |
| --- | --- |
| MessageConfig.PFOAJKNPCHL | 消息配置 ID；不同 ID 可以引用相同文本来源键 |
| MessageConfig.EGBBBFIINLO | 对话组 ID，与 MessageGroup 的同名字段精确对应 |
| MessageConfig.HBPLELJNAEA | 本地 section 标记，保留原值；没有当成完整播放顺序 |
| MessageConfig.LDHNMACDKLH | 短信正文 TextMap 键；9,290 个非空字段值，其中部分键在 TextMap 中不存在 |
| MessageConfig.NMIFFJEFBJI / HPKJODNLJOA | 两个配置显示身份槽位，数字 ID 可连接 MessageNPC.PFOAJKNPCHL |
| MessageNPC.HAKHHHCAENA | 显示名 TextMap 键 |
| MessageGroup.GJMPCHPFOMM | 通讯对象 ID，连接 MessageNPC；不代替逐条消息身份 |
| MessageConfig.FNOKFPDDECI / GGHOAADLHCF | 两个短选项引用槽位，常见 Option01 / Option02 TextMap 键 |
| MessageConfig.NAPGHEGEOOC / EEJNOOGPFND | 两个回复内容槽位，常见 OptionLong TextMap 键；也可能是图片路径 |
| MessageItem.AJEGPOBMPCG / DOPCCNPLNAF / GOHLPPCCDPJ | 附件标题、正文和顶部标题的 TextMap 引用 |

双显示身份字段的 24,410 个值中，18,419 个可连接 NPC 表，5,511 个为 0，
480 个为非零但未在 NPC 表中找到。正文、NPC 显示名、通讯对象以及少量
`VO_Message/...` 配音路径相互支持这些字段属于消息身份的解释。
这仍是离线配置关系，没有读取游戏 C# 字段定义或观察实际运行时发送行为。
`sender_source=message_config_identity` 表示已确定的配置显示身份，不证明该消息必然被发送。

只有两槽位 ID 完全一致、非零、所有同 ID 姓名行均可解析且显示名一致时才输出 sender。
任何冲突、缺名或零值都保留未知；不把 0 解释成哲或铃。
例如 Message_1060101 的两个槽位分别连接“伊埃斯研讨会”和“塔维斯进货Q&A”，
解析保留两个候选，没有按台词选择一个。
Message_970801 使用 0 / 0，正文包含男女主称呼，也仍不推断发送方。

男女路线标签只生成 `text_variants` 和男主/女主路线展示。
它们可能是对收件人的称呼变化，不能作为发送者身份证据。

## 真实数据导出统计

使用同一 CHS TextMap 在临时目录调用 `_extract_interknot` 的结果：

| 项目 | 数量 |
| --- | ---: |
| 原短信来源记录 | 9,925 |
| 按配置确认显示发送身份的来源 | 8,640 |
| 发送身份未知的来源 | 1,285 |
| 额外回复、选项或补充正文来源键 | 4,633 |
| 附件文本来源键 | 151 |
| 完整消息配置事件 | 12,205 |

原输出 9,923 条短信正文全部保留，另恢复了 2 条此前被筛掉的来源。
正文含“占位”字样不再按子串删除；这包含需要后续人工判断的编写说明候选。
空正文也进入来源审计，以 `retained=false` / `reason=empty_text` 标记。
正文不采用数字格式时写入未归属组，不静默丢弃。

4,633 和 151 是独立来源键数，不是实际新增消息播放数。
同一选项键可能被多个消息事件、两个选项槽位或两个长回复槽位引用；这些 occurrence
保留在配置审计中，没有通过同文去重合并。
回复字段中的图片路径保留为非文本引用，不渲染成一句对白。

未知来源按优先原因分组：

| 原因 | 来源键数 |
| --- | ---: |
| 没有 MessageConfig 正文引用 | 898 |
| NPC 名称缺失或配置身份未解 | 354 |
| 两身份槽位均为 0 | 19 |
| 两身份槽位冲突 | 7 |
| 相同来源被不同身份多次引用 | 5 |
| 相同来源兼作短信正文与选项 | 2 |

例如 Message_100601 的文本在多个配置中分别由“「启明星」”及“孤高的天才”显示。
每次配置引用的身份明确，整体来源键的 sender 则保留未知。
因此来源未解数不能等同于运行时消息事件未解数。

`Message_1010212`（“报酬五五分的那个”）在配置 1010212 中由猫又显示，
又被配置 302001201、302001401、302001601、302001701、302001801 用作 option_2。
`Message_20011308`（“我就知道你也这么想！”）在配置 20011307 中由妮可显示，
也被同组配置 20011306 用作 option_2。来源级 sender 均保留未知；message occurrence
和配置事件中的猫又、妮可身份仍保留。这两条没有新增或删除正文，只撤销了把正文身份
泛化到所有引用角色的标记，因此未知来源从 1,283 增至 1,285。

## 审计与独立复核

- `message-audit.jsonl`：所有非姓名 Message 正文来源、原文、路线文本及配置关系。
- `message-extra-sources.jsonl`：原短信正文之外的配置文本引用，逐项保留原文。
- `message-config-audit.jsonl`：完整配置事件与原字段、引用槽位、section、显示身份候选。
- `message-item-audit.jsonl`：附件表原字段及全部文字来源。

`scripts/check_corpus_integrity.py` 已纳入短信来源、额外来源的唯一性、原文与两种模式
候选集合对账，并要求默认/完整性模式的配置事件和附件审计完全一致。
这证明保存和模式一致性，不证明所有事件可达或分支顺序已恢复。

代理人互动当前前缀共有 56,474 个 TextMap 键，其中 53,845 个被解析为候选，
剩余 2,629 个均为姓名元数据。未发现该范围内的非姓名遗漏；短句、嵌套事件 ID
和独立相同文本均保留。重复形态同名代理人的代号映射绑定已展示档案，
同一代号指向不同代理人时保留归属未知。

街头独立检查发现 `EventName` 标题会被数字尾缀解析为正文，例如
`PasserBy_Chat_Roscaelifer_30130486_EventName_01` 的“可爱的设计作业”。
最终已修复：54 个 `EventName` 与 4 个 `InteractName` 均作为标题元数据保留。
章节/街头名字计数下降、旁白计数变化必须按来源与节点类型核查，不能直接报告为
补齐说话人的数量。

相关测试覆盖双身份冲突、零身份、重复 NPC 缺名、同源多事件冲突、联系人配置优先、
M/F 标签、选项和附件引用、占位字样与空来源保存，以及真实同源键兼作正文与选项时
保留 occurrence 身份、撤销来源级姓名泛化。

## 新结构化扫描撤销的旧角色标注

独立比较两个缓存的 `SpeakerIndex`，不把资源扫描数量当成正文数量：

- 旧缓存：`data/cache/3.3.0/source-17a3b9e1104b63e3/speakers_cache.json`，缓存版本 8，
  fingerprint=`cf0378402d98d9b81f96d003816d10a961f96610ef3ee2681639b6027a762aad`。
- 新缓存：`data/cache/3.3.0/speakers_cache.json`，缓存版本 9，
  fingerprint=`bb445d64da15f8dc85a52b0a9117150c4a64c410b385d60ca6ea64307927d0c6`。

在全部 53,845 个代理人互动候选中，9 条旧角色名被新节点解析撤销。
它们都来自 `GalBubbleStoryNode`，仅有本地演员槽位 A；同节点没有可确定姓名。
这是缓存层对比，尚未应用选项分类；文字没有删掉。最终正文对比见下方说明。

| 来源键 | 旧显示名 | 新状态 |
| --- | --- | --- |
| PartnerTalk_Chat_340170502_01 | 柏妮思 | 槽位 A，姓名未关联 |
| PartnerTalk_Chat_PartnerAstra_340290602_01 | 耀嘉音 | 槽位 A，姓名未关联 |
| PartnerTalk_Chat_PartnerAstra_340290801_01 | 耀嘉音 | 槽位 A，姓名未关联 |
| PartnerTalk_Chat_PartnerAstra_340290802_01 | 耀嘉音 | 槽位 A，姓名未关联 |
| PartnerTalk_Chat_PartnerAstra_340291001_01 | 耀嘉音 | 槽位 A，姓名未关联 |
| PartnerTalk_Chat_PartnerBurnice_340171999_01 | 柏妮思 | 槽位 A，姓名未关联 |
| PartnerTalk_Chat_PartnerYeshunguang_340430703_01 | 叶瞬光 | 槽位 A，姓名未关联 |
| PartnerTalk_Chat_PartnerYeshunguang_340430703_02 | 叶瞬光 | 槽位 A，姓名未关联 |
| PartnerTalk_Chat_PartnerYeshunguang_340430703_04 | 叶瞬光 | 槽位 A，姓名未关联 |

旧近邻字符串扫描可以给这些文本提供一个名字，却没有逐节点绑定证据。
这一变化属于撤销不充分的角色标注，不能计为补齐说话人。
代理人档案归属与逐句演员是不同字段；即使来源代号明确属于耀嘉音的互动，
同一场景仍可能包含主角或其他角色，不能把代号直接填入 speaker。

主线额外检查将新缓存与完整 OngoingTips 说话人映射合并后，对当前正文旧标注比较，
缓存层发现 `Main_GalGame_Chapter240_124000031_130` 的旧“「挽昼」”不同，
但不能据此移除最终正文身份：该来源最终保留完整配音证据。只比缓存会误报
3,927 条 tips 来源缺失，因为 tips 是提取时合并而非存于 Perform 缓存。

最终以 `out/zzz_story_3.3.0_chs` 对比新的 v2 输出：旧主线已有姓名无丢失或更换，
另补 8 条姓名；代理人旧标注撤销 10 条，其中 8 条是没有绑定的局部演员槽位，
2 条实际为选项（`PartnerTalk_Chat_330100401_06`、`PartnerTalk_Chat_330261401_07`）。
这与裸缓存层比较范围不同，以 `completion-comparison.json` 和最终清单为准。


最终街头旧范围复核补回 240 个 Bubble_PasserBy、Activity_Bubble_PasserBy21Spring、
Enclave_Bubble_PasserByWhitFiled 来源。候选为 24,058 个、姓名/标题元数据 3,561 个。
旧 Markdown 的 64 个未精确匹配行都在现有多行原文内，属于分段显示，未缺来源。
