# ADR-001: 反爬架构决策 — CDP 浏览器拦截优先策略

> **状态**: 已采纳 (2026-06-20)
> **决策人**: 辉 + Claude
> **影响范围**: 抖音、小红书、及未来所有含 JS 动态签名平台

---

## 背景

### 问题

2026年6月，抖音同小红书先后升级反爬机制：

| 平台 | 新防护 | 对 HTTP 直连的影响 |
|------|--------|-------------------|
| 抖音 | JSVM 虚拟机保护 (`_$jsvmprt`) | 首页无法获取真实 HTML，ttwid 不再通过 HTTP Cookie 下发 |
| 抖音 | 强制登录 | 搜索 API `status_code: 2483`，需 sessionid |
| 抖音 | msToken/verifyFp/uifid/webid 动态生成 | 每次页面加载 JS 重新生成，跨请求复用返回空结果 |
| 小红书 | x-s/x-s-common 一次性签名 | 收割后跨请求复用触发 `code: 300011`（账号异常） |

### 旧方案（HTTP 直连 + 签名逆向）

```
curl_cffi (TLS伪装) → a_bogus/x_s 签名 → 收割 token → HTTP 直连 API
```

**失败原因**：token/签名为一次性，JavaScript 动态生成，收割后无法复用。

### 新方案（CDP 浏览器拦截）

```
Chrome (CDP:9222) → Playwright connect → page.on("response") → 实时拦截 API 响应
```

**验证结果**（2026-06-19）：

| 平台 | 搜索词 | 结果数 | 数据字段 |
|------|--------|--------|----------|
| 抖音 | AI | 9条 | 25+字段（点赞/评论/分享/收藏/时长/分辨率/音乐/标签） |
| 小红书 | AI | 22条 | 18字段（点赞/收藏/评论/分享/图片数/笔记类型） |

---

## 决策

### 我们决定

**抖音、小红书正式放弃纯 HTTP 逆向方案。CDP 浏览器拦截成为唯一正式方案。**

所有新平台接入默认使用 CDP 优先策略。

### 架构层级

```
┌─────────────────────────────────────┐
│          Smart Agent 请求层          │
├─────────────────────────────────────┤
│  1st: CDP 浏览器拦截 (Primary)       │  ← 所有 JS 动态签名平台
│  2nd: curl_cffi HTTP (Fallback)     │  ← 无 JS 签名平台 / CDP 暂不可用
│  3rd: anti_bot_escalator (Auto)     │  ← 自动检测封阻并升级
└─────────────────────────────────────┘
```

### 各平台策略

| 平台 | 主方案 | Fallback | 备注 |
|------|--------|----------|------|
| 抖音 | CDP 拦截 | ❌ 无 | HTTP 已完全不可用 |
| 小红书 | CDP 拦截 | ❌ 无 | HTTP 触发 300011 封号 |
| B站 | CDP 拦截 | curl_cffi | HTTP 仍可用但 CDP 更稳 |
| 微博 | curl_cffi | CDP 拦截 | HTTP 基本够用 |
| 知乎 | curl_cffi | CDP 拦截 | smart_fetch 已覆盖 |

---

## 影响

### 正面

1. **零逆向维护** — Chrome 自动更新，签名由浏览器原生 JS 生成，平台升级反爬唔影响我哋
2. **封号风险最低** — 真实 Chrome TLS 指纹 + 完整 JS 执行环境 + 人类行为模拟
3. **数据完整性** — 单次拦截获取 25+ 字段（vs HTTP 方案嘅 6 字段）
4. **开发效率** — 新平台接入只需写 response handler，唔使研究签名算法

### 代价

1. **Chrome 常驻** — 需长期运行 CDP Chrome 进程（~300-500MB RAM）
2. **首次登录** — 需手动扫码登录（之后 Profile 持久化，7-30 天有效）
3. **单点依赖** — CDP Chrome 崩溃需重启（已有 watchdog 自动重启机制）

### 迁移

- `config/settings.py`: `BROWSER_ENGINE` 默认值 `playwright` → `auto`
- 新增 `scripts/start_cdp_chrome.ps1` 启动脚本
- `anti_bot_escalator.py`: 最高级别(EscalationLevel.CDP_BROWSER) 已内置

---

## 参考资料

- 诊断报告: `docs/diagnostic-report-2026-06-19.md`
- CDP 启动脚本: `scripts/start_cdp_chrome.ps1`
- 抖音 Adapter: `src/agents/douyin_adapter.py`
- 抖音 HTTP Util: `src/utils/douyin_http.py`
- 小红书 HTTP Util: `src/utils/xhs_http.py`
- 反反爬升级引擎: `src/utils/anti_bot_escalator.py`
- 浏览器服务: `src/utils/browser_service.py`

---

*本 ADR 遵循 [Michael Nygard 的架构决策记录模板](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions.html)*
