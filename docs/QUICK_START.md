# Smart Agent Pro — 快速开始

## 1. 安装 Docker

Windows / Mac 下载 Docker Desktop: https://www.docker.com/products/docker-desktop

## 2. 启动

```bash
docker compose up -d
```

首次启动会下载镜像并安装依赖，约 2-5 分钟。

## 3. 配置 DeepSeek API Key

编辑项目目录下的 `.env` 文件：

```
DEEPSEEK_API_KEY=sk-你的key
```

> 💡 去 https://platform.deepseek.com 注册，充值 ¥10 即可。每次 AI 分析约 ¥0.01。

## 4. 打开 WebUI

浏览器访问：**http://localhost:8000**

## 5. 开始使用

- **采集数据**：选平台 → 输入关键词 → 点「开始采集」
- **AI 分析**：切换到「全流程分析」→ 输入关键词 → 点「开始分析」

---

## 常见问题

**Q: 抖音/小红书搜不到数据？**
A: 首次使用需要登录。点 WebUI 右上角「会话管理」→「收割全部平台」。

**Q: AI 分析提示「模型调用失败」？**
A: 检查 `.env` 中 `DEEPSEEK_API_KEY` 是否正确。

**Q: 如何更新？**
A: `docker compose pull && docker compose up -d`
