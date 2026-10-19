//! 绝区零剧情 MCP 服务。
//!
//! 分层：`corpus`（数据模型、构建、快照）→ `index`（二元组倒排）→ `engine`（工具逻辑，产出文本）
//! → `mcp`（JSON-RPC 分发）→ `transport`（stdio / Streamable HTTP）。

pub mod corpus;
pub mod de;
pub mod engine;
pub mod index;
pub mod mcp;
pub mod text;
pub mod transport;

use std::path::Path;

use anyhow::Result;

/// 加载语料：文件视为快照，目录视为 zzz-story-extractor 的输出目录（现场构建）。
pub fn load_source(path: &Path) -> Result<corpus::Corpus> {
    if path.is_dir() {
        corpus::build_from_dir(path)
    } else {
        corpus::load_snapshot(path)
    }
}
