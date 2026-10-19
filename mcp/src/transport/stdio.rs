//! stdio 传输：每行一条 JSON-RPC 消息（MCP stdio 约定），响应写回 stdout，日志只走 stderr。

use std::sync::Arc;

use anyhow::Result;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};

use crate::mcp::Server;

pub async fn serve(server: Arc<Server>) -> Result<()> {
    let mut lines = BufReader::with_capacity(64 * 1024, tokio::io::stdin()).lines();
    let mut stdout = tokio::io::stdout();
    while let Some(line) = lines.next_line().await? {
        if line.trim().is_empty() {
            continue;
        }
        if let Some(mut resp) = server.handle(line.as_bytes()) {
            resp.push(b'\n');
            stdout.write_all(&resp).await?;
            stdout.flush().await?;
        }
    }
    tracing::info!("stdin 已关闭，退出");
    Ok(())
}
