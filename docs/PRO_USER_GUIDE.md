# Smart Agent Pro — 使用指南

## 目录

1. [功能介绍](#功能介绍)
2. [安装部署](#安装部署)
3. [WebUI 使用](#webui-使用)
4. [CLI 命令行](#cli-命令行)
5. [AI 分析详解](#ai-分析详解)
6. [配置说明](#配置说明)
7. [常见问题](#常见问题)

---

## 功能介绍

Smart Agent Pro 集成三大核心能力：

### 🔐 数据采集引擎

| 平台 | 搜索 | 热榜 | 详情 | 评论 | 用户 |
|------|:---:|:---:|:---:|:---:|:---:|
| B站 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 抖音 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 小红书 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 知乎 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 快手 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 微博 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 贴吧 | ✅ | ✅ | ✅ | ✅ | ✅ |

### 🤖 AI 智能分析（7 个 Agent）

| Agent | 功能 | 输出 |
|------|------|------|
| 🔥 爆款识别 | 自动识别高传播潜力内容 | 爆款评分 + 流行原因 |
| 📦 选品分析 | 挖掘可带货商品 | 变现潜力 + 竞争优势 |
| 🎬 视频拆解 | 拆解视频结构与钩子 | 结构模板 + 转化点 |
| 💬 评论情绪 | 分析评论正负面情绪 | 情绪占比 + 受众反应 |
| ✍️ 营销文案 | 生成多平台营销文案 | 标题/正文/CTA |
| 🔄 内容改写 | 跨平台内容适配 | 改写文案 + 赛道分析 |
| 🖼️ 配图策略 | AI 生成封面设计策略 | 风格/配色/绘画提示词 |

### ⚡ 高性能引擎

- **Go 高性能版**：6.7MB 单文件，零依赖
- **Docker 一键部署**：一行命令启动
- **纯 HTTP 采集**：无需浏览器，毫秒级响应

---

## 安装部署

### Docker（推荐）

```bash
# 1. 解压项目文件
unzip smart-agent-pro.zip
cd smart-agent-pro

# 2. 配置 DeepSeek API Key
cp .env.example .env
# 编辑 .env，填入你的 DEEPSEEK_API_KEY

# 3. 启动
docker compose up -d

# 4. 访问
# WebUI: http://localhost:8000
# API文档: http://localhost:8000/docs
```

### 更新

```bash
docker compose pull
docker compose up -d
```

---

## WebUI 使用

### 多平台采集

1. 选择目标平台（可多选）
2. 选择操作类型：搜索 / 热榜 / 详情 / 评论 / 用户
3. 输入关键词
4. 点击「开始采集」
5. 结果导出：JSON / CSV

### 全流程 AI 分析

1. 切换到「全流程分析」标签
2. 选择分析模式：关键词分析 / 对标账号 / 舆情分析
3. 输入分析关键词（如「AI绘画」「蓝牙耳机」）
4. 选择分析深度：深度分析 / 快速搜索
5. 点击「开始分析」
6. 等待 30-90 秒，查看 AI 分析报告

### 结果操作

- **点击行**：查看详情弹窗
- **筛选栏**：按关键词/平台过滤
- **列排序**：点击表头排序
- **分页**：每页 50 条，底部翻页

---

## CLI 命令行

```bash
# 进入容器
docker exec -it smart-agent bash

# 单平台搜索
python main.py --platform bilibili --keyword "AI绘画" --limit 20

# 全平台搜索
python main.py --platform all --keyword "美食"

# 热榜
python main.py --platform zhihu --type hot

# 全流程 AI 分析
python main.py --platform bilibili --keyword "AI绘画" --pipeline full

# 导出 CSV
STORE_BACKEND=csv python main.py --platform bilibili --keyword "Python"
```

---

## AI 分析详解

### 工作流程

```
输入关键词 → 7平台并发搜索 → 结果合并去重
    ↓
趋势分析 → 选品/视频/情绪并行分析 → 文案/改写/配图并行生成
    ↓
结构化报告输出
```

### 费用说明

AI 分析使用 DeepSeek API，由用户自行申请：

- 每次完整分析（7 Agent）：约 ¥0.01-0.05
- 充值 ¥10 可用数百次
- 申请地址：https://platform.deepseek.com

---

## 配置说明

### .env 文件

| 变量 | 必填 | 说明 |
|------|:--:|------|
| `DEEPSEEK_API_KEY` | ✅ | AI 分析必须 |
| `PROXY_URL` | ❌ | 代理 IP（大规模采集建议） |
| `STORE_BACKEND` | ❌ | 输出格式：csv/json/excel |
| `BROWSER_ENGINE` | ❌ | playwright / cdp / camoufox |

### 端口

| 服务 | 端口 | 说明 |
|------|:--:|------|
| WebUI + API | 8000 | Web 界面 |
| SignSrv | 9001 | 签名引擎（内部） |

---

## 常见问题

### 抖音/小红书搜不到数据？

首次使用需要在浏览器登录对应平台。操作：
1. 打开 WebUI → 右上角「会话管理」
2. 点击「收割全部平台」
3. 在弹出的 Chrome 中扫码登录
4. 等待收割完成后即可使用

### AI 分析报错？

1. 检查 `.env` 中 `DEEPSEEK_API_KEY` 是否正确
2. 确认 DeepSeek 账户有余额
3. 查看 `logs/` 目录下的日志文件

### 如何查看运行日志？

```bash
docker logs -f smart-agent
```

或 WebUI 中的「运行日志」面板。

### 如何备份数据？

```bash
# 数据存储在以下目录
./output/       # 采集结果
./browser_data/ # 登录会话
./logs/         # 运行日志

# 备份整个目录即可
tar -czf backup.tar.gz ./output ./browser_data
```

---

*如有问题，请联系微信：smart4906*
