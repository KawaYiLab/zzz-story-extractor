# zzz-story-mcp：绝区零剧情库 MCP 服务

给「剧情总结 AI」用的只读 MCP 服务。数据来自本仓库提取器的输出（`story.jsonl`、`supplement.jsonl`、`lore/**/*.md`），
提供检索、顺读、目录、角色速览和任务指引五个工具，支持 stdio 与 Streamable HTTP 两种传输。
接口风格参考虚空终端（AkashaTerminal）：先检索、再按稳定的 `docId` 读原文。

## 快速开始

需要 Rust 1.88+。

```powershell
# 1. 先用提取器生成数据（见仓库根目录 README）
.\.venv\Scripts\python.exe -m zzz_story extract --out out

# 2. 编译
cd mcp
cargo build --release

# 3. 构建快照：预建索引，服务启动只需几十毫秒
.\target\release\zzz-story-mcp.exe build --data ..\out\zzz_story_3.2.0_chs -o ..\out\zzz_story.zsc

# 4a. stdio 模式（本机客户端拉起进程）
.\target\release\zzz-story-mcp.exe serve --source ..\out\zzz_story.zsc

# 4b. Streamable HTTP 模式
.\target\release\zzz-story-mcp.exe serve --source ..\out\zzz_story.zsc --http 127.0.0.1:8765
```

`--source` 也可以直接指向提取器输出目录，启动时现场构建（约 1 秒），省去 `build` 步骤。

> `mimalloc` 分配器需要 C 编译器（MSVC 或 MinGW）。不方便时用 `cargo build --release --no-default-features` 改用系统分配器。

### 客户端配置

Streamable HTTP（与虚空终端相同的写法）：

```json
{
  "mcpServers": {
    "zzz-story": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

stdio（Claude Desktop、Cursor 等）：

```json
{
  "mcpServers": {
    "zzz-story": {
      "command": "C:\\path\\to\\zzz-story-mcp.exe",
      "args": ["serve", "--source", "C:\\path\\to\\zzz_story.zsc"]
    }
  }
}
```

Claude Code：

```bash
claude mcp add --transport http zzz-story http://127.0.0.1:8765/mcp
# 或 stdio
claude mcp add zzz-story -- /path/to/zzz-story-mcp serve --source /path/to/zzz_story.zsc
```

## 工具

| 工具 | 用途 |
| --- | --- |
| `zzz_catalog` | 目录。无参数列出全部章节（游戏顺序，含场景数/句数/字数）与设定分类；`path=ch:Chapter110` 按阅读顺序列出一章的场景，按内容类型与官方任务分节，带 docId 与出场角色；`path=doc_…` 看某篇的位置与前后篇；`keyword` 按标题筛选。 |
| `zzz_search` | 全文检索。空格分隔多词为「同篇同时出现」（AND），没有全中时退化为部分匹配并明确告知；可按 `scope`（story/supplement/lore）、`path`（章节/分类）、`speaker`（说话人）过滤；给 `docId` 时为篇内检索，列出全部命中行。结果按 BM25 排序，标题、路径与出场名单命中加分。 |
| `zzz_read` | 读原文。`L行号 说话人：台词`，`【选项】` 为玩家选项；按 `offset`/`limit` 分页并受 `maxChars` 字数预算约束；`follow=true` 读完一篇自动接下一篇；`docId` 也可以是章节 id，从章首顺读。结尾总给出可照抄的续读调用。 |
| `zzz_character` | 角色速览。设定档案、按章节的出场场景数/台词数/被提及次数、每章首次出场或首次提及的场景、常同场角色、相关名称（如「零号·安比」之于「安比」）。 |
| `zzz_guide` | 任务方法指引：`summary` 剧情总结、`character` 角色弧线、`timeline` 事件时间线、`verify` 原文查证。同样以 MCP prompts（`chapter_summary` / `character_arc` / `event_timeline` / `fact_check`）提供。 |

典型的整章总结流程：

```text
zzz_catalog()                                   → 找到章节 id
zzz_catalog(path="ch:Chapter110")               → 看场景与任务分节，规划阅读
zzz_read(docId="ch:Chapter110", maxChars=30000) → 从章首顺读
zzz_read(docId="doc_…", offset=…, follow=true)  → 照抄结尾的续读调用，直到「已全部读完」
zzz_search(keyword="…", path="ch:Chapter110")   → 核对关键事实
```

`docId`（`doc_` + 12 位十六进制）由文档的来源键哈希而来，数据版本不变时跨构建稳定，可以写进总结里当出处。

## 命令

```text
zzz-story-mcp build  --data <提取器输出目录> -o <快照>
zzz-story-mcp serve  --source <快照或输出目录> [--http 地址] [--path /mcp]
                     [--allowed-origin <Origin>…] [--token <令牌>]
zzz-story-mcp call   --source <…> <工具名> '<JSON 参数>'     # 本地直接调用工具，调试用
zzz-story-mcp bench  --source <…> [--iterations N] [--case '工具名=JSON']…
```

`serve` 的参数都可以用环境变量给：`ZZZ_STORY_SOURCE`、`ZZZ_STORY_HTTP`、`ZZZ_STORY_PATH`、
`ZZZ_STORY_ALLOWED_ORIGINS`（逗号分隔）、`ZZZ_STORY_TOKEN`。日志级别用 `RUST_LOG`（默认 `info`，只写 stderr）。

### HTTP 部署

- 端点：`POST /mcp`（带不带尾斜杠均可）；`GET /healthz` 返回语料统计。
- 无状态：不发 `Mcp-Session-Id`、不开 SSE 推送流，`GET`/`DELETE /mcp` 返回 405，任何实例都能处理任何请求，可以直接水平扩展。
- 安全：默认只接受无 `Origin` 或本机来源的请求（防 DNS 重绑定）；公开部署时用 `--allowed-origin '*'` 或具体域名放开浏览器来源，
  并建议加 `--token`（客户端发 `Authorization: Bearer …`）。
- 响应按 `Accept-Encoding` 自动 gzip/br 压缩，请求体上限 1 MiB，单请求超时 30 秒。
- 更新数据：重新 `build` 快照（先写临时文件再改名），然后 `kill -HUP <pid>`，新语料原子替换，进行中的请求不受影响（Unix）。

## 架构

```text
提取器输出 ──build──▶ 快照 (.zsc) ──load──▶ Corpus ──▶ engine（工具逻辑，产出文本）
                                                       ▲
                     stdio / Streamable HTTP ──▶ mcp（JSON-RPC 分发）
```

- `corpus`：扁平内存模型。全部台词拼成一块文本，行、文档、分组都是下标区间；同一章的场景在行数组里相邻，顺读时缓存友好。
- `index`：字符二元组倒排（CSR 存储）。中文子串检索的标准做法：查询词的每个二元组取倒排求交（长短悬殊时指数搜索），
  三字以上再逐行核对；每行补一个「末字 + 结束符」键，单字查询变成按首字取一段连续键求并（大结果用位图）。
  检索前做逐字符一对一的折叠（全角→半角、大小写、各种间隔号→「·」），命中位置可直接映射回原文截取片段。
- 标题/路径检索：标题拼成一块做一次 SIMD 子串扫描；路径按去重后的几百条各比一次再展开。
- 检索流程：各词求出命中文档集合 → 先在文档集合上求交（AND）→ 只为入选文档构建命中表 → BM25 打分 → 线性选出前 N 篇再排序。
- 快照：`ZZSC` 魔数 + 格式版本 + xxh3 校验 + postcard 负载，损坏或版本不符时拒绝加载并提示重建。
- `mcp`：手写的无状态 JSON-RPC 层，支持协议 2024-11-05 ～ 2025-11-25 的版本协商、批量请求、通知；
  工具清单与提示清单启动时序列化一次，之后 `tools/list` 只是拷贝字节。工具参数宽松解析（`"10"`、`"true"` 也接受），
  参数或数据错误以 `isError: true` 返回，让模型自行修正。
- `transport`：stdio（逐行 JSON）与 axum 实现的 Streamable HTTP；语料放在 `ArcSwap` 里，热更新无锁。

## 性能

在 4 核云容器上、3.2.0 数据（主线 45,635 句 + 补充 + 设定，共 18,408 篇 / 137,789 行）实测：

| 项目 | 结果 |
| --- | --- |
| 构建快照 | 约 1.0 秒，快照 25.7 MB |
| 加载快照 | 约 50 ms |
| `zzz_search` 常见查询（「妮可」「零号空洞」「以骸」） | p50 60～130 µs |
| `zzz_search` 极高频词（「委托」「的」） | p50 1～2 ms |
| `zzz_read` 3 万字预算 | p50 约 11 µs |
| `zzz_character` | p50 约 0.2 ms |
| `zzz_catalog` 根目录 | p50 约 0.1 ms |

用 `zzz-story-mcp bench --source <快照>` 在自己机器上复测。

## 测试

```bash
cargo test           # 单元测试 + 端到端测试（tests/fixtures/sample 是带说话人的小型提取器输出）
cargo clippy --all-targets
```
