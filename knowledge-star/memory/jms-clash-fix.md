---
name: jms-clash-fix
description: JMS Clash Verge Rev 节点更新失败的根本原因、修复方案和配置文件路径
metadata: 
  node_type: memory
  type: project
  tags: 
    - clash
    - proxy
    - jms
    - vpn
    - clash-verge-rev
  originSessionId: c0b01e3e-53be-43f5-a67e-6584e221b7ea
---

# JMS Clash 节点更新问题 — 完整记录

## 问题现象
- Clash Verge Rev 2.5.1 远程订阅 JMS-2026 永远刷新失败
- 续费 JMS 后节点 IP 全部变晒，但 Clash 仲用紧旧 IP
- 代理显示中国 IP（所有 PROXY 连接超时 fallback DIRECT）

## 根本原因（3 个层面）

### 1. Clash Verge Rev 解唔到 SIP008 格式
JMS 订阅 URL 返嚟嘅系 `ss://` `vmess://` base64 编码格式（SIP008），
但 Clash Verge Rev 2.5.1 当 YAML 去 parse → "the remote profile data is invalid yaml"
→ 远程订阅永远下载失败 → `file: null` `updated: null`

### 2. proxy-providers 令 Clash Verge 生成空配置
喺 profile 入面加 `proxy-providers:` 会导致 Clash Verge 生成 config.yaml 时
解析失败，全部 proxies/rules 被丢晒，得返个空壳。

### 3. 后台 Service 缓存旧配置
clash-verge-service.exe 后台进程缓存咗旧 config，即使文件更新咗，
核心仲用紧旧 IP（如 65.49.193.187），全部 TCP i/o timeout。

## 最终解决方案

### 配置架构
- **Profile**: `type: local` (唔用 remote，因为 remote 解唔到 SIP008)
- **代理组**: `type: url-test` 自动选最快节点
- **节点格式**: VMess 加 `udp: true`，SS 唔使
- **模式**: `mode: rule`
- **端口**: mixed-port 7897, socks 7898, port 7899 (Clash Verge Rev 默认)
- **Controller**: 127.0.0.1:9097

### 关键文件路径
```
%APPDATA%\io.github.clash-verge-rev.clash-verge-rev\
├── profiles\
│   ├── JMS_renewed.yaml    ← 主配置文件（当前使用）
│   └── Merge.yaml           ← 合并模板（DNS、规则、代理组）
├── config.yaml              ← Clash Verge 生成的运行时配置
├── profiles.yaml            ← Profile 列表（current: JMS_renewed）
├── update_jms.py            ← 自动更新脚本
└── update_jms.log           ← 更新日志
```

### JMS 订阅信息
- 服务商: Just My Socks
- Service ID: 1366451
- UUID: 4992ef43-0c12-4485-a4ab-4a43b909b2a9
- 订阅 URL: `https://jmssub.net/members/getsub.php?service=1366451&id=4992ef43-0c12-4485-a4ab-4a43b909b2a9`
- 节点数: 6（2 SS + 4 VMess）
- 端口: 10195
- SS 密码: bDVLcXyV8aCtebKk
- SS 加密: aes-256-gcm

### 自动更新机制
- 脚本: `update_jms.py`
- 功能: 下载订阅 → 解码 base64 → 解析 ss:// vmess:// → 生成 YAML → 写文件 → API 热加载
- Windows 定时任务: `JMS-Clash-Update`，每日 08:57
- 热加载 API: `PUT http://127.0.0.1:9097/configs?force=true`
  - 需要 `Authorization: Bearer set-your-secret` header
  - 依赖 `enable_external_controller: true`（verge.yaml），默认 false

### 2026-06-09 故障记录
- **现象**: Clash 代理唔通，Google 返 502
- **直接原因**: JMS IP 轮换（6 个 IP 全部换晒），旧 IP 全部 TCP 唔通
- **根因 1**: `verge.yaml` 入面 `enable_external_controller: false` → TCP 9097 冇开 → 脚本热加载一直失败 → 核心 keep 住旧 IP
- **根因 2**: `update_jms.py` 冇 `Authorization: Bearer` header（即使 port 开咗都会 401）
- **修复**: 
  1. `verge.yaml`: `enable_external_controller: true`
  2. `update_jms.py`: 加 `Authorization: Bearer set-your-secret` header
  3. 热加载测试通过，日志显示「已热加载」

### 更新命令（手动）
```powershell
python "%APPDATA%\io.github.clash-verge-rev.clash-verge-rev\update_jms.py"
```

### Clash 安装位置
- 程序: `D:\Clash Verge\clash-verge.exe`
- 数据: `C:\Users\guohu\AppData\Roaming\io.github.clash-verge-rev.clash-verge-rev\`
- 版本: 2.5.1
- 核心: verge-mihomo

## 部署到新电脑
桌面有打包: `C:\Users\guohu\Desktop\JMS-Clash-Config\`
包含: JMS_renewed.yaml, Merge.yaml, update_jms.py, SETUP.md

## 注意事项
- 唔好喺 Clash Verge 界面创建 type: remote 嘅 JMS 订阅（会爆 invalid yaml）
- 唔好喺配置文件加 proxy-providers（Clash Verge 会生成空 config）
- 更新配置后需要重启 Clash Verge（或等 update_jms.py 热加载）
- 如果节点过期，行一次 update_jms.py 即可
