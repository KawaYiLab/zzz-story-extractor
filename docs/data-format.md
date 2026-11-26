# 绳网剧情档案库语料包

`out/story-corpus.json.gz` 是 gzip 压缩的 UTF-8 JSON，对应绳网后端的 `Bundle`，`format` 为整数 `1`。

| 成员 | 内容 |
| --- | --- |
| `manifest` | 语言、输入文件哈希、数据版本、章节、记录数与结构校验结果。两位主角合并时 `protagonist` 为 `mixed`。 |
| `story` | 主线 JSONL 原文。 |
| `extra` | 活动、支线、代理人故事与空洞事件 JSONL 原文。 |
| `supplement` | 漫画和过场字幕 JSONL 原文。 |
| `lore` | 以相对路径为键的设定文件。机器目录 `documents.jsonl` 通过来源键关联代理人互动、街头对白和短信等记录。 |

剧情正文使用 `text`，署名使用 `speaker`。独立来源各自保留原始 `source_key`。一个共用来源含两种不同的正文或署名时，两条记录共用来源键，`selected_variant` 分别为 `M`（哲）和 `F`（铃）。第一条沿用原 `line_id`，另一条在其后加 `:F`。两边相同的共用记录只写一次。有明确路线的来源使用该路线的正文。设定目录和所引用的 JSONL 保留 `text_variants`，档案库导入时会展开。

章节与场景按目录顺序整理，跨场景播放顺序仍待核实。设定字段见[机器目录说明](lore-machine-format.md)。
