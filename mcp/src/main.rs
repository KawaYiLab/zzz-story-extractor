use std::io::Write as _;
use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Instant;

use anyhow::{Context, Result};
use arc_swap::ArcSwap;
use clap::{Parser, Subcommand};
use tracing_subscriber::EnvFilter;

use zzz_story_mcp::corpus::{Corpus, save_snapshot};
use zzz_story_mcp::mcp::{Server, tools};
use zzz_story_mcp::text::thousands;
use zzz_story_mcp::transport::{http, stdio};
use zzz_story_mcp::{engine, load_source};

#[cfg(feature = "mimalloc")]
#[global_allocator]
static GLOBAL: mimalloc::MiMalloc = mimalloc::MiMalloc;

const DEFAULT_SOURCE: &str = "out/zzz_story_3.2.0_chs";

#[derive(Parser)]
#[command(
    name = "zzz-story-mcp",
    version,
    about = "绝区零剧情库 MCP 服务（检索 / 顺读 / 角色 / 总结指引）"
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// 从提取器输出目录构建快照（预建索引，服务秒级启动）。
    Build {
        /// zzz-story-extractor 的输出目录（含 story.jsonl）。
        #[arg(long, default_value = DEFAULT_SOURCE)]
        data: PathBuf,
        /// 快照输出路径。
        #[arg(long, short, default_value = "zzz_story.zsc")]
        output: PathBuf,
    },
    /// 启动 MCP 服务。默认 stdio；指定 --http 时为 Streamable HTTP。
    Serve {
        /// 快照文件，或提取器输出目录（现场构建）。
        #[arg(long, env = "ZZZ_STORY_SOURCE", default_value = DEFAULT_SOURCE)]
        source: PathBuf,
        /// HTTP 监听地址，如 127.0.0.1:8765。
        #[arg(long, env = "ZZZ_STORY_HTTP")]
        http: Option<SocketAddr>,
        /// HTTP 端点路径。
        #[arg(long, env = "ZZZ_STORY_PATH", default_value = "/mcp")]
        path: String,
        /// 允许的浏览器 Origin（可重复；`*` 为全部允许）。默认只允许本机来源。
        #[arg(
            long = "allowed-origin",
            env = "ZZZ_STORY_ALLOWED_ORIGINS",
            value_delimiter = ','
        )]
        allowed_origins: Vec<String>,
        /// 要求 `Authorization: Bearer <token>`。
        #[arg(long, env = "ZZZ_STORY_TOKEN", hide_env_values = true)]
        token: Option<String>,
    },
    /// 在本地直接调用一个工具并打印结果（调试用）。
    Call {
        #[arg(long, env = "ZZZ_STORY_SOURCE", default_value = DEFAULT_SOURCE)]
        source: PathBuf,
        /// 工具名，如 zzz_search。
        tool: String,
        /// JSON 参数，如 '{"keyword":"妮可"}'。
        #[arg(default_value = "{}")]
        args: String,
    },
    /// 用一组典型查询测量延迟。
    Bench {
        #[arg(long, env = "ZZZ_STORY_SOURCE", default_value = DEFAULT_SOURCE)]
        source: PathBuf,
        /// 每个查询重复次数。
        #[arg(long, default_value_t = 200)]
        iterations: usize,
        /// 自定义查询（可重复），格式 `工具名=JSON`，如 `zzz_search={"keyword":"妮可"}`；不给则用内置用例。
        #[arg(long = "case")]
        cases: Vec<String>,
    },
}

fn init_tracing() {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")))
        .with_writer(std::io::stderr)
        .with_ansi(std::io::IsTerminal::is_terminal(&std::io::stderr()))
        .with_target(false)
        .init();
}

fn load_timed(source: &Path) -> Result<Corpus> {
    let started = Instant::now();
    let corpus = load_source(source).with_context(|| format!("加载 {} 失败", source.display()))?;
    tracing::info!(
        source = %source.display(),
        docs = corpus.docs.len(),
        lines = corpus.lines.len(),
        bigrams = corpus.index.key_count(),
        postings = corpus.index.posting_count(),
        elapsed_ms = started.elapsed().as_millis() as u64,
        "语料已加载"
    );
    Ok(corpus)
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    init_tracing();
    match cli.command {
        Command::Build { data, output } => build(&data, &output),
        Command::Serve {
            source,
            http,
            path,
            allowed_origins,
            token,
        } => {
            let runtime = tokio::runtime::Builder::new_multi_thread().enable_all().build()?;
            runtime.block_on(serve(
                source,
                http,
                http::HttpOptions {
                    path,
                    allowed_origins,
                    token,
                },
            ))
        }
        Command::Call { source, tool, args } => {
            let corpus = load_timed(&source)?;
            let args: serde_json::Value = serde_json::from_str(&args).context("参数不是合法 JSON")?;
            let started = Instant::now();
            let result =
                tools::call(&corpus, &tool, Some(args)).map_err(|_| anyhow::anyhow!("未知工具 {tool}"))?;
            let elapsed = started.elapsed();
            let mut stdout = std::io::stdout().lock();
            match result {
                Ok(text) => writeln!(stdout, "{text}")?,
                Err(engine::ToolError(msg)) => writeln!(stdout, "[isError] {msg}")?,
            }
            tracing::info!(elapsed_us = elapsed.as_micros() as u64, "工具耗时");
            Ok(())
        }
        Command::Bench {
            source,
            iterations,
            cases,
        } => bench(&source, iterations, &cases),
    }
}

fn build(data: &Path, output: &Path) -> Result<()> {
    let started = Instant::now();
    let corpus = zzz_story_mcp::corpus::build_from_dir(data)?;
    let built = started.elapsed();
    let bytes = save_snapshot(&corpus, output)?;
    let load_started = Instant::now();
    let _ = zzz_story_mcp::corpus::load_snapshot(output)?;
    tracing::info!(
        output = %output.display(),
        size_mb = format!("{:.1}", bytes as f64 / 1e6),
        docs = corpus.docs.len(),
        lines = corpus.lines.len(),
        speakers = corpus.speakers.len(),
        bigrams = corpus.index.key_count(),
        build_ms = built.as_millis() as u64,
        reload_ms = load_started.elapsed().as_millis() as u64,
        "快照已生成"
    );
    Ok(())
}

async fn serve(source: PathBuf, addr: Option<SocketAddr>, options: http::HttpOptions) -> Result<()> {
    let corpus = tokio::task::spawn_blocking({
        let source = source.clone();
        move || load_timed(&source)
    })
    .await??;
    let shared = Arc::new(ArcSwap::from_pointee(corpus));
    let server = Arc::new(Server::new(shared.clone())?);
    spawn_reload_on_sighup(source, shared);

    match addr {
        None => stdio::serve(server).await,
        Some(addr) => {
            let listener = tokio::net::TcpListener::bind(addr)
                .await
                .with_context(|| format!("监听 {addr} 失败"))?;
            tracing::info!(%addr, path = %options.path, "Streamable HTTP 已启动");
            let app = http::router(server, options);
            axum::serve(listener, app)
                .with_graceful_shutdown(shutdown_signal())
                .await?;
            Ok(())
        }
    }
}

/// SIGHUP：重新加载语料并原子替换，进行中的请求继续用旧语料，零停机。
#[cfg(unix)]
fn spawn_reload_on_sighup(source: PathBuf, shared: Arc<ArcSwap<Corpus>>) {
    use tokio::signal::unix::{SignalKind, signal};
    tokio::spawn(async move {
        let Ok(mut hup) = signal(SignalKind::hangup()) else {
            return;
        };
        while hup.recv().await.is_some() {
            let src = source.clone();
            match tokio::task::spawn_blocking(move || load_timed(&src)).await {
                Ok(Ok(corpus)) => {
                    shared.store(Arc::new(corpus));
                    tracing::info!("SIGHUP：语料已热更新");
                }
                Ok(Err(e)) => {
                    tracing::error!(error = %format!("{e:#}"), "SIGHUP：重新加载失败，继续使用旧语料")
                }
                Err(e) => tracing::error!(error = %e, "SIGHUP：重新加载任务异常"),
            }
        }
    });
}

#[cfg(not(unix))]
fn spawn_reload_on_sighup(_source: PathBuf, _shared: Arc<ArcSwap<Corpus>>) {}

async fn shutdown_signal() {
    let ctrl_c = async {
        let _ = tokio::signal::ctrl_c().await;
    };
    #[cfg(unix)]
    let term = async {
        if let Ok(mut s) = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()) {
            s.recv().await;
        }
    };
    #[cfg(not(unix))]
    let term = std::future::pending::<()>();
    tokio::select! {
        () = ctrl_c => {},
        () = term => {},
    }
    tracing::info!("收到退出信号");
}

fn bench(source: &Path, iterations: usize, custom: &[String]) -> Result<()> {
    let corpus = load_timed(source)?;
    let first_chapter = corpus.groups.first().map(|g| g.id.clone()).unwrap_or_default();
    let mut cases: Vec<(&str, serde_json::Value)> = Vec::new();
    for case in custom {
        let (tool, json) = case.split_once('=').context("--case 格式应为 工具名=JSON")?;
        cases.push((
            tool,
            serde_json::from_str(json).with_context(|| format!("--case 参数不是合法 JSON: {json}"))?,
        ));
    }
    let builtin: Vec<(&str, serde_json::Value)> = vec![
        ("zzz_catalog", serde_json::json!({})),
        ("zzz_catalog", serde_json::json!({ "path": first_chapter })),
        ("zzz_search", serde_json::json!({ "keyword": "铃" })),
        ("zzz_search", serde_json::json!({ "keyword": "妮可" })),
        ("zzz_search", serde_json::json!({ "keyword": "零号空洞" })),
        ("zzz_search", serde_json::json!({ "keyword": "狡兔屋 妮可 委托" })),
        (
            "zzz_search",
            serde_json::json!({ "keyword": "以骸", "scope": "story" }),
        ),
        (
            "zzz_read",
            serde_json::json!({ "docId": first_chapter, "maxChars": 30000 }),
        ),
        ("zzz_character", serde_json::json!({ "name": "妮可" })),
    ];
    if cases.is_empty() {
        cases = builtin;
    }
    let mut stdout = std::io::stdout().lock();
    writeln!(
        stdout,
        "{:<14} {:<40} {:>10} {:>10} {:>10} {:>8}",
        "tool", "args", "p50(µs)", "p99(µs)", "max(µs)", "chars"
    )?;
    for (tool, args) in cases {
        let mut samples = Vec::with_capacity(iterations);
        let mut chars = 0;
        for _ in 0..iterations.max(1) {
            let started = Instant::now();
            let out =
                tools::call(&corpus, tool, Some(args.clone())).map_err(|_| anyhow::anyhow!("未知工具"))?;
            samples.push(started.elapsed().as_micros() as u64);
            chars = match out {
                Ok(t) => t.chars().count(),
                Err(e) => e.0.chars().count(),
            };
        }
        samples.sort_unstable();
        let pct = |p: f64| samples[((samples.len() - 1) as f64 * p) as usize];
        let shown = zzz_story_mcp::text::truncate_chars(&args.to_string(), 38);
        writeln!(
            stdout,
            "{:<14} {:<40} {:>10} {:>10} {:>10} {:>8}",
            tool,
            shown,
            pct(0.5),
            pct(0.99),
            samples.last().copied().unwrap_or(0),
            thousands(chars)
        )?;
    }
    Ok(())
}
