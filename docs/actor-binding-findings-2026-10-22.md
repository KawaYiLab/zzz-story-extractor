# 已提取对白的角色证据补全

本轮只读取公开配置与本地保存的 Unity 资源，没有启动游戏或读取运行中进程。
文本字典与 FileCfg 快照为 3.3.0，固定上游提交
`fd6cb326c07c75f39b0b05845d204302c451ec34`；本地版本为 `CNPRODWin3.3.0`。
代码改动补充可核验的逐句证据，不以台词语义、姓名表位置或角色模型身份推断显示名。

## 完整配音引用的显示名证据

`OngoingTipsConfigTemplateTb` 每行明确关联 `FGAHJLHNEDB` 文本键、
`BLOGJEGIBOH` 显示名键，以及 `PFOBGIIIICG` / `CIBKAFBOGCI` 配音键。
本轮把相同**完整配音键**上的显示名证据用于无显示名的已读取演出节点。
必须所有 occurrence 均有可核对配音引用、所有引用的显示名一致；显式显示名、
冲突、旁白和选项不会被覆盖。相同内部角色别名不作为关联依据。

八个气泡键对应的完整配音引用在这张表中有确定显示名“警惕的队长”：

| 气泡文本键 | 表中引用文本键 | 完整配音键 |
| --- | --- | --- |
| `Main_BubbleStory_Chapter140_414000023_02` | `Main_OngoingLevel_Chapter140_111101106_02` | `OngoingLevel_Chapter140_LuciasFather_111101106_001` |
| `Main_BubbleStory_Chapter140_414000023_03` | `Main_OngoingLevel_Chapter140_111101106_03` | `OngoingLevel_Chapter140_LuciasFather_111101106_002` |
| `Main_BubbleStory_Chapter140_414000024_01` | `Main_OngoingLevel_Chapter140_111101112_01` | `OngoingLevel_Chapter140_LuciasFather_111101112_001` |
| `Main_BubbleStory_Chapter140_414000024_03` | `Main_OngoingLevel_Chapter140_111101112_03` | `OngoingLevel_Chapter140_LuciasFather_111101112_002` |
| `Main_BubbleStory_Chapter140_414000025_01` | `Main_OngoingLevel_Chapter140_111101119_01` | `OngoingLevel_Chapter140_LuciasFather_111101119_001` |
| `Main_BubbleStory_Chapter140_414000025_02` | `Main_OngoingLevel_Chapter140_111101119_02` | `OngoingLevel_Chapter140_LuciasFather_111101119_002` |
| `Main_BubbleStory_Chapter140_414000025_03` | `Main_OngoingLevel_Chapter140_111101119_03` | `OngoingLevel_Chapter140_LuciasFather_111101119_003` |
| `Main_BubbleStory_Chapter140_414000025_04` | `Main_OngoingLevel_Chapter140_111101119_04` | `OngoingLevel_Chapter140_LuciasFather_111101119_004` |

同一别名 `LuciasFather` 的其他来源也使用“虚弱的队长”，因此不能把该别名全局
映射到某个名字。部分气泡文本和 Ongoing 文本措辞不同，例如“提高警惕，继续前进。”
与“没关系，继续前进。”；原文均保留，`perform.speaker_evidence` 记录
`kind=exact_configured_voice`、表行 ID、来源键、姓名键与 `text_difference`。
这证明配置引用身份，不证明字幕与实际录音吻合，也不证明运行时会播放哪个候选。

已有 Ongoing 直接补名还扩展到代理人和街区来源，重复配置显示名冲突时不取最后一行；
补名时保留既有 Perform / Timeline 元数据。

## 嵌套转场文字

本地 `Main_Chat_Chapter230_323000065.asset` 与
`Main_Chat_Chapter240_324000009.asset` 等对象的父节点是
`MainCityChatTransitionWithActionsNode`（`nodeType=29`），其 `Cfg` 类型为
`TransitionWithActionsCfg`，`DialogueKey` 是转场/屏幕表现文字。
旧 occurrence 只保留子配置类型，把这一类字段计成未关联说话人的对白。
现同时保存 `node_type` 与 `parent_node_type`，仅已核对的父子字段组合标记旁白；
其他未知 `*Cfg.DialogueKey` 不按名称猜测分类。文字、来源 ID 与排序不被重写。

## A/B/C 槽位研究界限

精确读取以下两个配置选中的资产（AssetBundle container hash 与 PPtr 定位）：

- `Data/ScriptConfig/Perform/Data/Bubble/Chapter01/Main_Chat_Chapter01_40100031.asset`
- `Data/ScriptConfig/Perform/Data/BubbleStory/Chapter00/Main_BubbleStory_Chapter00_4000064.asset`

对象中只有 `storySections` 和 `storySegment`。`GalBubbleStoryNode` 保存
`Speaker`、`Text`、`Voice`、`StartTime`、`EndTime`；前一个资源以 A/B 槽位
表示演员，后一个资源为 A。`GalBubbleAction` 只有中断/重播控制字段，
没有把槽位绑定姓名的演员表。已有缓存中同资源、同 section、同槽位的已解析
配音身份，也没有为这些未解主线候选提供可直接传播的唯一显示名。

继续核对了同源 `NPCSubTemplateTb`、`MainCityObjectTemplateTb`、
`MainCityObjectSubTemplateTb`、`MainCityGraphConfigTemplateTb`。
`NPCSubTemplateTb` 确认 `PFOAJKNPCHL` 子 ID 对应 `HAKHHHCAENA` 姓名键；
`MainCityObjectTemplateTb.KNFOBAIPGLD` 关联 NPC 子 ID。
然而当前未解主线节点没有可用的非零 `SpeakerSubID` / `SpeakerNpcTag`，
这些表不能凭空补出 A/B/C 映射。

`MainCityGraphConfigTemplateTb.KEGFAKLAELH` 指向 `Data/MainCityNodeGraph/*.json`，
`DGFIFFIHEJB` 是调用参数，例如 `npcTag,...;bubbleId,...`。
本地索引将 `Data/MainCityNodeGraph/DateIdleMoveToBubble.json` 定位到
`3890695391.blk`，其中精确引用的 TextAsset 有 `ShowBubble` 节点，参数为
`npcTag=&npcTag`、`bubbleId=&bubbleId`。读取该块全部 458 个 TextAsset 并核对
当前未解主线场景 ID，没有命中可用的主线气泡入口。
这只是该资源块的检查范围，不能宣称所有调用入口已找全；关卡/世界图的调用和参数
作用域仍需还原。公开 `AreaData/MainCityStreet.json` 在该快照只有 `null`，
不能作为有效的主城执行图。

## 配置来源

研究下载保存在仓库外的本地 `C:/Users/Administrator/zzz-story-research/actor-bindings/3.3.0/`，
没有把额外配置作为已核验导出输入偷偷混入清单。下列哈希是下载字节的 SHA-256：

| 表 | SHA-256 |
| --- | --- |
| [OngoingTipsConfigTemplateTb](https://git.mero.moe/dimbreath/ZenlessData/raw/commit/fd6cb326c07c75f39b0b05845d204302c451ec34/FileCfg/OngoingTipsConfigTemplateTb.json) | `87b8d849e7454d6ac1a517fcba0eabfc610ad637b39c5d3b4f8ff002e5f42970` |
| [NPCSubTemplateTb](https://git.mero.moe/dimbreath/ZenlessData/raw/commit/fd6cb326c07c75f39b0b05845d204302c451ec34/FileCfg/NPCSubTemplateTb.json) | `907a049c74803b36babf4eaa247b0e440a20942a342f9fe9f06fa38750457af8` |
| [MainCityGraphConfigTemplateTb](https://git.mero.moe/dimbreath/ZenlessData/raw/commit/fd6cb326c07c75f39b0b05845d204302c451ec34/FileCfg/MainCityGraphConfigTemplateTb.json) | `fb3e58278ad56df6f24d28e160e195d09ab83a010f44071707a0ec44cbb0244d` |
| [MainCityObjectTemplateTb](https://git.mero.moe/dimbreath/ZenlessData/raw/commit/fd6cb326c07c75f39b0b05845d204302c451ec34/FileCfg/MainCityObjectTemplateTb.json) | `ee134c3dc51cca7678d4ee2a86cb21e90016c02df3ecaae77f4ed795e9e25dad` |
| [MainCityObjectSubTemplateTb](https://git.mero.moe/dimbreath/ZenlessData/raw/commit/fd6cb326c07c75f39b0b05845d204302c451ec34/FileCfg/MainCityObjectSubTemplateTb.json) | `0cf8d2734240c0774b6ac8b7b0b8acfe1b1c5638839094d8a262955c857b6f30` |

定向回归测试覆盖完整配音引用、同键冲突、未具名显示字段、子配置父节点分类和
元数据保存。最终整库计数与验证结果以本轮输出清单为准，不把研究样本数当成完整覆盖率。

## 已提取街区资源的空节点布局

扩展已提取代理人/街区的结构化扫描后，原先 26 个报错资源实际是两种已保存布局：
24 个对象的 `storySections=null`，另两个 `PartnerTalkBubble` 对象的数组夹有 `null`。
空字段作为 `status=empty` 保存；有文本节点的稀疏数组作为 `status=partial`，
同时保存 `null_nodes` 地址。跳转/连续分支不跨过空槽位，也不用 partial 图证明未使用副本。
对原报错的两个块 `3087913050.blk`、`3199840165.blk` 定向重扫，
得到 3,925 个 complete、24 个 empty、2 个 partial 图，解析错误为零。
这是该两块的扫描结果，空对象和稀疏数组并不表示主线播放关系已经完整。

`graphs_from_cab` 还增加逐目标错误收集，坏配置只进入自己的路径错误记录，
不会让同 CAB 中其他已经成功读取的资产全部丢失。
