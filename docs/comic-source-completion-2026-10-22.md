# 漫画上下文与特殊来源补充

已核对本机 CNPRODWin3.3.0、ZenlessData 3.3.0 TextMap 和 PerformTemplateTb。
本次解析离线资源，不读取游戏进程，不改写游戏文件。

## 漫画实际引用链

PerformTemplateTb 的 101 个 `Data/ScriptConfig/Comic/*.asset` 配置均在本机索引匹配。
ComicConfig 是普通 Unity MonoBehaviour，不使用既有 Perform 的 Odin storySections 布局。
通过配置 AssetBundle container hash/PPtr 找到 ComicConfig；原 mhy 节点 CAB 名保留后，
按照 fileID 对应的 external-file CAB 名和 pathID 找到 TimelineAsset，额外核对目标 bundle
在原配置的 m_Dependencies 中。TimelineAsset 的 track roots、child tracks 与父 PPtr
逐层核对，再读取 EventTriggerTrack 的 marker PPtr 列表，排除同文件其他 timeline 的节点。

EventTriggerMarkerInfo 与 BubbleEvent 使用 UnityEngine.Timeline / Unity.Timeline 类型标识。
BubbleEvent 同事件 GUID 对应 `Comic_<GUID>` TextMap 键；其他 ImageExchangeEvent GUID 不当作台词。
同事件 body 的显示名字段作为姓名证据，marker double 时间仅是 timeline 内局部时间。
姓名字段在固定标量与可变点数组之后，可能再跟 TwoPointAnim 等动画对象。
Terminus 前最后一个字符串可能是 Linear、QuadEaseOut 等动画曲线，不作为姓名。
所有 occurrence 保留资源、timeline、marker pathID、时间、字段位置与显示名，多个引用不合并为一次播放。
不据此推断跨漫画、跨主线场景播放顺序。

ComicConfig 的布局包含 3 个 PPtr、一个标量、11 个变体 PPtr、一个字符串和嵌套字符串数组。
部分依赖 timeline 在其他块中：C01_02a 的配置引用 CAB-a7187f1f38f081b1667563a5a65bd4fb，
从声明 dependency bundle hash 经 catalog 找到相应块，再按原 external CAB 名/PPtr 解析。
C01_99 的所有 timeline PPtr 为 null，继续保持未关联。

对当前 2,505 条 Comic 候选，2,452 条获得明确资源引用，459 条获得显示名；剩余 53 条没有足够证据。
缓存绑定配置、游戏版本、解析代码、catalog 与资源元数据，额外校验跨块依赖的元数据；refresh 可强制重建。

## 特殊及空原文

`Main_BubbleStory_Chapter170_417001009_01_Gender` 是独立来源值。
分别解析 M/F 后与 `_01` 完全等价，但原始富文本标签顺序不同。
将它作为 source_variant 进入原文审计，并附在基础正文，不当成第二次播放、不改变原稳定 ID。
若未来该值与基础来源不同，保留 distinct_source_variant 供核对，不按现有等价结果覆盖新原文。

`Main_Chat_Chapter02_30200076_08` 至 `_13` 的 CHS base 均为空。
CHS overwrite 没有这些键；EN base / overwrite 也没有这些键。
没有恢复原文的输入证据，保留 empty_source 审计，不用其他语言或推测文案填充中文正文。
