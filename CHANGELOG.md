# Changelog

## v0.1.0 (2026-05-24)

### Initial Release

- **5 platforms**: Bilibili, Xiaohongshu (RED), Douyin, Zhihu, Kuaishou
- **5 operations per platform**: search, hot/rank, detail, comment, user
- **Nested comments**: recursive reply extraction for all platforms
- **6 storage backends**: JSON, CSV, JSONL, Excel, SQLite, MySQL
- **WebUI**: FastAPI + Vanilla JS SPA with WebSocket real-time logs
- **MCP Server**: fastmcp integration for AI agent tool calling
- **Dual engine**: Playwright (headless) and CDP (authenticated session)
- **Proxy pool**: round-robin rotation with env-var configuration
- **Cache**: in-memory TTL cache for deduplication
- **CI/CD**: GitHub Actions with smoke tests and linting
