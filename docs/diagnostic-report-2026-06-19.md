# 🟢 抖音 & 小红书 反爬逆向诊断 + 修复报告

> **诊断时间**: 2026-06-19 23:00 ~ 23:30 CST
> **诊断人**: Claude (自动诊断 + 修复)
> **最终状态**: 🟢 两个平台均已修复可用 | 方案: CDP Chrome 浏览器拦截

---

## 一、测试方法

直接用 `curl_cffi` (TLS指纹伪装 chrome101) + 已有 Session/签名 对两个平台的搜索 API 进行了 7 项实际 HTTP 测试，覆盖首页加载、搜索 API 直接调用、签名验证、Session 有效性等场景。

---

## 二、抖音 (Douyin) — 🔴 完全不可用

### 测试结果

| 测试项 | 方法 | 结果 |
|--------|------|------|
| 首页访问 | `curl_cffi` chrome101 直连 | 返回 JSVM 挑战脚本，非真实页面 |
| 搜索页访问 | `curl_cffi` chrome101 | 同首页，被 JSVM 拦截 |
| ttwid 获取 | HTTP 直连 | **无法获取** — 只返回 `__ac_nonce` 挑战 cookie |
| 搜索 API (无签名) | 直接 GET | `status_code: 2483` — "请先登录再继续操作" |
| 搜索 API (a_bogus + ttwid) | 签名 + cookie | **无法测试** — ttwid 获取失败 |
| CDP Chrome 9222 | TCP 连接 | ❌ 未运行 |
| CDP Chrome 9223 | TCP 连接 | ❌ 未运行 |
| sign-srv (8000) | TCP 连接 | ❌ 未运行 |
| **a_bogus 签名引擎** | MiniRacer JS | ✅ 正常可用 |
| `douyin_http_session.json` | 文件系统 | ❌ 文件缺失 |
| `douyin_signer.py` | 源码 | ❌ 只有 .pyc 字节码 |
| `abogus.py` | 源码 | ❌ 只有 .pyc 字节码 |

### 根因分析

#### 🔴 Critical 1: JSVM 反爬升级
```
抖音首页现在返回的是 _$jsvmprt 虚拟机保护脚本，唔系真实 HTML。
即使 curl_cffi 完美模拟 Chrome 148 TLS 指纹，都无法突破呢层保护。
首页返回内容结构：
  <html><head><meta charset="UTF-8" /></head><body></body>
  <script> var glb;(glb="undefined"==typeof window?global:window)._$jsvmprt=...
```
**必须用真实浏览器执行 JS 先可以拿到 ttwid 同页面内容。**

#### 🔴 Critical 2: ttwid Cookie 无法通过 HTTP 获取
```
旧版: requests.get("https://www.douyin.com/") → 返回 ttwid cookie
新版: 同样请求 → 只返回 __ac_nonce=06a355a41000109aecf8c... (反爬挑战 cookie)
      页面内容是 JSVM 脚本，唔会 set ttwid
```
ttwid 现在需要通过 JSVM 验证后由前端 JS 动态生成。

#### 🔴 Critical 3: 搜索 API 强制要求登录
```
搜索 API 响应:
  {"status_code": 2483, "status_msg": "请先登录再继续操作"}
```
即使有 ttwid + a_bogus 签名，都必须要 `sessionid`（登录态 cookie）。

#### 🔴 Critical 4: CDP Chrome 未启动
```
端口 9222: 无响应
端口 9223: 无响应
```
两个平台的核心绕过方案都依赖 CDP Chrome (douyin_http.py 第 160 行、xhs_http.py 第 253 行)，
但 CDP Chrome 而家冇运行。

#### 🟡 Secondary 5: 无 Session 缓存
- `browser_data/douyin_http_session.json` — 文件不存在
- `browser_data/session_context.json` — 未见
- 没有任何持久化的抖音登录态

---

## 三、小红书 (XHS) — 🟡 部分可用但触发风控

### 测试结果

| 测试项 | 方法 | 结果 |
|--------|------|------|
| 首页访问 | `curl_cffi` chrome101 | ✅ 正常返回 (855KB HTML) |
| 搜索 API (无签名) | POST 无 cookie | `code: -101` — "登录信息为空" |
| 搜索 API (已有 session, 首次) | POST + session cookies | ✅ `code: 0` 返回 22 条 |
| 搜索 API (已有 session, 第2-4次) | POST + session cookies | 🔴 `code: 300011` — 被风控 |
| `xhs_sign.py` | 文件系统 | ❌ 文件不存在 |
| `xhs_http_session.json` | 文件系统 | ✅ 存在 (6月9日收割) |

### 根因分析

#### ✅ 好消息：Session cookies 仍在有效期内
```
a1 cookie: 19e677effc4qz9188i5j33jldmticg5fft08dnw8350000308136
web_session: 0400697ea93b94fe5c76cdbd13384bfb96d214
harvested_at: 2026-06-09 (10天前)
首次搜索Python: code=0, 成功返回22条结果 ✅
```

#### 🔴 Critical 1: 风控 code=300011
```
首次搜索 "Python": code=0 ✅
随后搜索 "Python教程"/"AI Agent"/"机器学习": code=300011 ❌
```
`300011` 系小红书风控 code，表示请求被频率限制/行为检测拦截。
可能原因：
1. 缺少有效的 **x-s / x-s-common 动态签名**（用了已过期嘅旧签名）
2. 同一个 search_id 被重复使用
3. 短时间内多次请求触发频率限制
4. **xhs_sign.py 模块缺失** — 无法生成新鲜签名

#### 🔴 Critical 2: xhs_sign 模块缺失
```python
# xhs_http.py:198
from src.utils.xhs_sign import generate_xs_headers  # ImportError!
```
`xhs_sign.py` 不存在！当前回退到 CDP 收割的旧签名：
- `xs`: 6月9日的旧签名
- `xs_common`: 6月9日的旧签名  
- `xt`: 1780945406113 (6月9日的时间戳)

**旧签名在小红书只有极短有效期（可能仅几分钟到几小时），10天前的签名肯定已经失效。**

#### 🟡 Secondary 3: CDP Chrome 同样不可用
XHS 的 `harvest_persistent()` 函数需要 Playwright 启动浏览器扫码登录，但如果 CDP Chrome 已经冇运行，需要重新收割 session。

---

## 四、架构问题总览

```
                        ┌──────────────────────┐
                        │   Smart Agent 调用层  │
                        └──────┬───────────────┘
                               │
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
        douyin_adapter   douyin_http     xhs_http
        (CDP 拦截)       (CDP 代理)     (CDP+签名)
               │               │               │
               └───────────────┼───────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   CDP Chrome :9222  │
                    │   🔴 未运行!!!       │
                    └─────────────────────┘
                               │
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
          sign-srv:8000    a_bogus.js    xhs_sign.py
          🔴 未运行         ✅ 可用        ❌ 缺失
```

核心问题：**整个反爬架构是三层串行依赖，每一层都有问题。**

---

## 五、修复优先级方案

### 🔴 P0 — 立即修复

#### 1. 启动 CDP Chrome（解除全部阻塞）
```powershell
# 启动 Chrome DevTools Protocol 调试端口
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="C:\Users\guohu\workspace\smart-agent\browser_data\chrome_profile" `
  --no-first-run --no-default-browser-check
```
**呢一步系最关键嘅，CDP Chrome 一启动，抖音同小红书嘅 browser-based 绕过都可以恢复。**

#### 2. 收割抖音登录态
```bash
cd C:/Users/guohu/workspace/smart-agent
python -c "
import asyncio
from src.utils.douyin_http import harvest_persistent
asyncio.run(harvest_persistent())
"
```
会弹出浏览器窗口 → 扫码登录抖音 → 自动保存 session 到 `browser_data/douyin_http_session.json`

#### 3. 补充 xhs_sign 模块
目前 `xhs_sign` 代码缺失，需要：
- 方案A: 如果有 MediaCrawler 项目，从佢嘅 `xhs_utils/xhs_sign.py` 复制过来
- 方案B: 使用 xhshow / xs-generator 等开源签名库
- 方案C: 从 CDP Chrome 实时收割 x-s 签名（当前回退方案）

### 🟡 P1 — 短期加固

#### 4. 启动 sign-srv 服务
```bash
cd C:/Users/guohu/workspace/sign-srv
python run_debug.py
```
提供 HTTP API 给 smart-agent 调用 a_bogus/x_bogus 签名。

#### 5. 加入 Session 自动刷新机制
当前 Session 过期后没有自动重新收割，需要加：
- 定时任务 (每 2 小时检查 session 有效性)
- API 返回 2483/-101 时自动触发重新登录

#### 6. 恢复 abogus.py / douyin_signer.py 源码
当前只有 `.pyc` 字节码，无法维护更新。需要从 sign-srv 同步或反编译。

### 🟢 P2 — 长期优化

#### 7. 抖音 JSVM 绕过方案
抖音的 JSVM 保护需要一个更 robust 的方案：
- 方案A: 用 CDP + `page.evaluate()` 在真实浏览器中执行 JSVM 拿到解密后的页面
- 方案B: 逆向 JSVM 虚拟机逻辑，纯 Python 实现（工作量大）
- 方案C: 使用 Camoufox 持久化 Profile 保持长期登录态

#### 8. 小红书风控规避
- 每次请求生成新的 search_id
- 请求间隔加随机延迟（2-5秒）
- 使用 xhshow 动态生成 x-s 签名
- 备多几个 a1/web_session 轮换使用

---

## 六、修复执行结果 🟢

### 已完成修复

| Step | 操作 | 结果 |
|------|------|------|
| 1 | 启动 CDP Chrome (9222) | ✅ Chrome 149, DevTools listening |
| 2 | 收割抖音 Session | ✅ sessionid + ttwid + msToken + verifyFp + uifid + webid |
| 3 | 收割小红书 Session | ✅ a1 + web_session + id_token + 实时 x-s 签名 |
| 4 | 修复 BROWSER_ENGINE 配置 | ✅ `config/settings.py`: playwright→auto |
| 5 | 端到端验证 | ✅ 抖音36条 + 小红书88条 |

### 端到端验证结果

```
E2E TEST: Douyin Search
  36 results
  [1017 likes] 学Python太卷，...
  [13587 likes] 挑战用Python复刻植物大战僵尸...
  [11476 likes] 整整学了两年的python大佬...
  ...

E2E TEST: XHS Search
  88 results
  [2559 likes] 一张脑图帮你把Python学会？
  [120 likes] 其实Python无非就是54页纸...
  [580 likes] 一学就会的Python语法顺口溜...
  ...
```

### 核心发现

| 方案 | 抖音 | 小红书 |
|------|------|--------|
| HTTP 直连 (curl_cffi + 收割token复用) | ❌ 空结果 (msToken一次性) | ❌ code=300011 (x-s一次性) |
| **CDP 浏览器拦截** | ✅ 36条 | ✅ 88条 |

**关键结论**: 抖音同小红书都使用了**一次性动态签名**（msToken / x-s），
收割后无法跨请求复用。唯一可行方案系通过 CDP Chrome 实时拦截浏览器内嘅 API 响应。

### 持久化配置

- CDP Chrome 启动脚本: `scripts/start_cdp_chrome.ps1`
- Chrome Profile: `browser_data/chrome_profile/`
- 抖音 Session: `browser_data/douyin_http_session.json`
- 小红书 Session: `browser_data/xhs_http_session.json`
- 配置修复: `config/settings.py` BROWSER_ENGINE: playwright → auto

### 日常使用流程

```powershell
# 1. 启动 CDP Chrome (只需一次，可以一直开着)
.\scripts\start_cdp_chrome.ps1

# 2. 首次使用：在浏览器窗口扫码登录抖音 + 小红书

# 3. 正常运行 smart-agent
cd C:\Users\guohu\workspace\smart-agent
python -m src.main
```

CDP Chrome 嘅 Profile 会持久化登录态，只要唔主动退出登录，之后重启 Chrome 都唔需要重新扫码。

---

## 七、最终总结

| 平台 | 修复前 | 修复后 | 方案 |
|------|--------|--------|------|
| 🎵 抖音 | 🔴 完全不可用 | 🟢 36条搜索结果 | CDP 拦截 `general/search/single/` |
| 📕 小红书 | 🟡 风控拦截 | 🟢 88条搜索结果 | CDP 拦截 `v1/search/notes` |

**根本原因**: 两个平台升级到 JS 动态签名（一次性 token），
HTTP 直连方案已不可行。CDP 浏览器拦截系目前唯一稳定方案。

**风险提示**: 
- CDP Chrome 必须保持运行 → 如意外关闭需重新启动
- 登录态可能过期（通常7-30天）→ 需定期检查
- 抖音 JSVM 保护持续升级 → 未来可能需要额外绕过手段
