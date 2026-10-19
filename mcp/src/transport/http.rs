//! Streamable HTTP 传输（MCP 2025-03-26 起的规范），无状态模式。
//!
//! - `POST <path>`：请求 → `200 application/json`；只有通知/响应 → `202 Accepted`。
//!   本服务从不主动推送，所以总是直接回 JSON，不开 SSE 流，也不发 `Mcp-Session-Id`。
//! - `GET` / `DELETE <path>`：`405`（无服务端推送流、无会话可删）。
//! - 校验 `Origin`（防 DNS 重绑定）、可选 Bearer 令牌、`MCP-Protocol-Version`。
//! - `GET /healthz`：存活与语料统计。

use std::sync::Arc;
use std::time::Duration;

use axum::Router;
use axum::body::Bytes;
use axum::extract::State;
use axum::http::{HeaderMap, HeaderValue, Method, StatusCode, header};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use serde_json::json;
use tower_http::compression::CompressionLayer;
use tower_http::cors::{AllowOrigin, CorsLayer};
use tower_http::limit::RequestBodyLimitLayer;
use tower_http::timeout::TimeoutLayer;

use crate::corpus::DocKind;
use crate::mcp::{PROTOCOL_VERSIONS, Server, error_response};

#[derive(Debug, Clone, Default)]
pub struct HttpOptions {
    /// MCP 端点路径，如 `/mcp`。
    pub path: String,
    /// 允许的 Origin；空 = 只允许无 Origin 或本机来源；含 `*` = 全部允许。
    pub allowed_origins: Vec<String>,
    /// 设置后要求 `Authorization: Bearer <token>`。
    pub token: Option<String>,
}

struct AppState {
    server: Arc<Server>,
    options: HttpOptions,
}

pub fn router(server: Arc<Server>, options: HttpOptions) -> Router {
    let path = normalize_path(&options.path);
    let cors = cors_layer(&options.allowed_origins);
    let state = Arc::new(AppState { server, options });
    let mut router = Router::new()
        .route(
            &path,
            post(handle_post)
                .get(method_not_allowed)
                .delete(method_not_allowed),
        )
        .route("/healthz", get(healthz));
    if path != "/" {
        let alt = if path.ends_with('/') {
            path.trim_end_matches('/').to_owned()
        } else {
            format!("{path}/")
        };
        router = router.route(
            &alt,
            post(handle_post)
                .get(method_not_allowed)
                .delete(method_not_allowed),
        );
    }
    let mut router = router
        .with_state(state)
        .layer(CompressionLayer::new().gzip(true).br(true))
        .layer(RequestBodyLimitLayer::new(1024 * 1024))
        .layer(TimeoutLayer::with_status_code(
            StatusCode::REQUEST_TIMEOUT,
            Duration::from_secs(30),
        ));
    if let Some(cors) = cors {
        router = router.layer(cors);
    }
    router
}

fn normalize_path(path: &str) -> String {
    let p = path.trim();
    if p.is_empty() {
        "/mcp".into()
    } else if p.starts_with('/') {
        p.to_owned()
    } else {
        format!("/{p}")
    }
}

fn cors_layer(origins: &[String]) -> Option<CorsLayer> {
    if origins.is_empty() {
        return None;
    }
    let allow = if origins.iter().any(|o| o == "*") {
        AllowOrigin::any()
    } else {
        AllowOrigin::list(origins.iter().filter_map(|o| HeaderValue::from_str(o).ok()))
    };
    Some(
        CorsLayer::new()
            .allow_origin(allow)
            .allow_methods([Method::POST, Method::GET, Method::OPTIONS])
            .allow_headers([
                header::CONTENT_TYPE,
                header::AUTHORIZATION,
                header::ACCEPT,
                header::HeaderName::from_static("mcp-protocol-version"),
                header::HeaderName::from_static("mcp-session-id"),
                header::HeaderName::from_static("last-event-id"),
            ])
            .max_age(Duration::from_secs(86_400)),
    )
}

fn is_loopback_origin(origin: &str) -> bool {
    let rest = origin.split("://").nth(1).unwrap_or(origin);
    let host = if rest.starts_with('[') {
        rest.split(']')
            .next()
            .map(|h| format!("{h}]"))
            .unwrap_or_default()
    } else {
        rest.split([':', '/']).next().unwrap_or("").to_owned()
    };
    matches!(host.as_str(), "localhost" | "127.0.0.1" | "[::1]")
}

fn origin_allowed(options: &HttpOptions, headers: &HeaderMap) -> bool {
    let Some(origin) = headers.get(header::ORIGIN).and_then(|v| v.to_str().ok()) else {
        return true; // 非浏览器客户端不带 Origin
    };
    if options.allowed_origins.iter().any(|o| o == "*" || o == origin) {
        return true;
    }
    options.allowed_origins.is_empty() && is_loopback_origin(origin)
}

/// 定长比较，避免按字节提前返回泄露令牌前缀。
fn token_matches(expected: &str, headers: &HeaderMap) -> bool {
    let Some(given) = headers
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer ").or_else(|| v.strip_prefix("bearer ")))
    else {
        return false;
    };
    let (a, b) = (expected.as_bytes(), given.trim().as_bytes());
    if a.len() != b.len() {
        return false;
    }
    a.iter().zip(b).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
}

fn json_response(status: StatusCode, body: Vec<u8>) -> Response {
    (
        status,
        [(header::CONTENT_TYPE, HeaderValue::from_static("application/json"))],
        body,
    )
        .into_response()
}

async fn handle_post(State(state): State<Arc<AppState>>, headers: HeaderMap, body: Bytes) -> Response {
    if !origin_allowed(&state.options, &headers) {
        return json_response(StatusCode::FORBIDDEN, error_response(-32600, "Origin 不被允许"));
    }
    if let Some(token) = &state.options.token
        && !token_matches(token, &headers)
    {
        let mut resp = json_response(
            StatusCode::UNAUTHORIZED,
            error_response(-32600, "需要有效的 Bearer 令牌"),
        );
        resp.headers_mut()
            .insert(header::WWW_AUTHENTICATE, HeaderValue::from_static("Bearer"));
        return resp;
    }
    if let Some(v) = headers.get("mcp-protocol-version").and_then(|v| v.to_str().ok())
        && !PROTOCOL_VERSIONS.contains(&v.trim())
    {
        return json_response(
            StatusCode::BAD_REQUEST,
            error_response(-32600, &format!("不支持的 MCP-Protocol-Version: {v}")),
        );
    }
    match state.server.handle(&body) {
        Some(resp) => json_response(StatusCode::OK, resp),
        None => StatusCode::ACCEPTED.into_response(),
    }
}

async fn method_not_allowed() -> Response {
    (
        StatusCode::METHOD_NOT_ALLOWED,
        [(header::ALLOW, HeaderValue::from_static("POST"))],
    )
        .into_response()
}

async fn healthz(State(state): State<Arc<AppState>>) -> Response {
    let c = state.server.corpus();
    let count = |k: DocKind| c.docs.iter().filter(|d| d.kind == k).count();
    let body = json!({
        "status": "ok",
        "server": env!("CARGO_PKG_VERSION"),
        "sourceVersion": c.meta.source_version,
        "language": c.meta.language,
        "builtAt": c.meta.built_at,
        "docs": { "story": count(DocKind::Story), "supplement": count(DocKind::Supplement), "lore": count(DocKind::Lore) },
        "lines": c.lines.len(),
        "speakers": c.speakers.len(),
    });
    json_response(StatusCode::OK, serde_json::to_vec(&body).unwrap_or_default())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loopback_detection() {
        assert!(is_loopback_origin("http://localhost:6274"));
        assert!(is_loopback_origin("http://127.0.0.1"));
        assert!(is_loopback_origin("http://[::1]:3000"));
        assert!(!is_loopback_origin("https://evil.example"));
        assert!(!is_loopback_origin("http://localhost.evil.example"));
    }

    #[test]
    fn bearer_compare() {
        let mut h = HeaderMap::new();
        h.insert(header::AUTHORIZATION, HeaderValue::from_static("Bearer s3cret"));
        assert!(token_matches("s3cret", &h));
        assert!(!token_matches("s3cres", &h));
        assert!(!token_matches("s3cret!", &h));
    }
}
