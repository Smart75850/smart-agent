---
name: cdp-anti-bot-strategy
description: 反爬架构决策：CDP浏览器拦截优先，抖音/小红书已弃用HTTP逆向方案
metadata: 
  node_type: memory
  type: project
  related_files: 
    - workspace/smart-agent/docs/ADR-001-CDP优先策略.md
    - workspace/smart-agent/config/settings.py
    - workspace/smart-agent/scripts/start_cdp_chrome.ps1
    - workspace/smart-agent/src/agents/douyin_adapter.py
    - workspace/smart-agent/src/utils/xhs_http.py
    - workspace/diagnostic-report-2026-06-19.md
  knowledge_star_nodes: 
    - 95 (抖音反爬 JSVM + 动态签名)
    - 96 (小红书反爬 x-s 动态签名)
    - 97 (CDP浏览器拦截通用方案)
    - 98 (反爬架构决策：CDP优先策略)
  originSessionId: 0823178f-adc7-4f42-8415-25341d0abf95
---

# CDP 浏览器拦截优先策略

## 核心决策（2026-06-20）

**抖音、小红书正式废弃纯 HTTP 逆向方案（a_bogus/x-s 签名），全面采用 CDP Chrome 浏览器拦截方案。**

## 为什么

1. 抖音新增 JSVM 保护 (`_$jsvmprt`)，首页不返回真实 HTML
2. 抖音新增 msToken/verifyFp/uifid/webid 一次性 JS 动态签名
3. 小红书 x-s/x-s-common 为一次性签名，收割复用触发 code 300011 风控
4. HTTP 直连每 1-4 周需重新逆向，维护成本极高
5. CDP Chrome 真实 TLS 指纹 + JS 环境，无需关心签名变更

## 架构

```
请求优先级: CDP浏览器拦截 → curl_cffi HTTP → anti_bot_escalator
```

## 操作流程

1. 启动 CDP Chrome: `.\scripts\start_cdp_chrome.ps1`
2. 首次扫码登录抖音 + 小红书（Profile 持久化，7-30天有效）
3. 之后 smart-agent 自动使用 CDP 拦截（BROWSER_ENGINE=auto）

## 关键配置

- `config/settings.py`: BROWSER_ENGINE 默认值改为 `auto`
- CDP Chrome 端口: 9222
- Chrome Profile: `browser_data/chrome_profile/`
- 抖音 Session: `browser_data/douyin_http_session.json`
- 小红书 Session: `browser_data/xhs_http_session.json`

## 验证结果

- 抖音搜索 "AI": 9条, 25+字段（点赞/评论/分享/收藏/时长/分辨率/音乐/标签）
- 小红书搜索 "AI": 22条, 18字段（点赞/收藏/评论/分享/笔记类型/图片数）

## 相关记忆

- [[jms-clash-fix]] — Clash 代理对 CDP Chrome 也生效

**Why:** 2026年6月抖音小红书同时升级反爬，发现 HTTP 签名方案对一次性动态 token 彻底失效。经过 7 项实际 HTTP 测试 + CDP 拦截对比验证，确认只有 CDP 方案稳定可用。维护成本从每次 1-4 周逆向降为零。

**How to apply:** 所有新平台默认走 CDP 拦截。HTTP 直连仅作 lightweight fallback（用于无 JS 签名平台）。anti_bot_escalator 自动检测封阻并升级到 CDP。
