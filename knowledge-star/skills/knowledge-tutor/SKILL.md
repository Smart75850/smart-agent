---
name: knowledge-tutor
description: "自动教学系统：读取知识星图，匹配当前任务相关知识点，主动提供参考并更新学习进度。Use when: session starts, task involves learning, user asks about knowledge points."
triggers:
  - 知识
  - 学习
  - 教学
  - 星图
  - knowledge
  - learn
---

# 知识星图自动教学系统

## 概述

自动读取知识星图，分析当前任务相关知识点，主动提供参考并更新学习进度。

## 工作流程

### 1. 会话开始时自动触发

每次会话开始，执行以下步骤：

```bash
# 读取知识星图数据
python scripts/match-knowledge.py --init
```

### 2. 任务分析与知识匹配

当用户提供任务或问题时：

1. 提取任务关键词
2. 匹配知识星图中的相关知识点
3. 主动提供知识参考

```bash
# 匹配相关知识点
python scripts/match-knowledge.py --match "任务描述或关键词"
```

### 3. 知识点展示格式

匹配到知识点后，按以下格式展示：

```
📚 相关知识参考：

【知识点标题】
- 摘要：xxx
- 掌握度：⭐⭐⭐⭐
- 相关项目：xxx

💡 要了解更多？输入「详细」查看完整内容。
```

### 4. 学习进度更新

任务完成后，自动更新学习进度：

```bash
# 更新学习进度
python scripts/match-knowledge.py --update <知识ID> --mastery +1
```

### 5. 学习路径推荐

根据当前掌握度，推荐下一步学习：

```bash
# 获取学习路径推荐
python scripts/match-knowledge.py --recommend
```

### 6. 周报生成

每周生成学习周报：

```bash
# 生成周报
python scripts/match-knowledge.py --report
```

## 主动教学模式

当检测到以下情况时，主动提供教学：

1. **任务涉及未掌握的知识点**（mastery < 3）
2. **任务涉及高影响力知识点**（vc > 10）
3. **任务涉及相关依赖知识点**（pre 字段）

教学提示格式：

```
🎓 教学提示：

你正在处理的任务涉及「XXX」知识点。
该知识点的前置依赖是：[A, B, C]
建议先了解这些前置知识。

要我现在解释吗？
```

## 学习路径引擎

基于前置依赖完成度 + 影响力评分，推荐最优学习路径：

```bash
# 获取推荐路径
python scripts/match-knowledge.py --recommend-path
```

输出格式：

```
🗺️ 推荐学习路径：

1. [已完成] FastAPI项目结构 (mastery: 4)
2. [已完成] httpx Windows代理避坑 (mastery: 5)
3. [推荐学习] Sentinel走地引擎 (mastery: 2, 影响力: 8)
   ↳ 原因：前置依赖已完成，影响力高
4. [可选] DeepSeek提示词设计 (mastery: 3)
```

## 配置

知识星图路径：
- JSON数据：C:\Users\guohu\Saved Games\knowledge-galaxy-data.json
- HTML可视化：C:\Users\guohu\Saved Games\knowledge-galaxy.html

## 注意事项

1. 每次会话只自动触发一次初始化
2. 匹配结果按相关度排序，最多显示5个
3. 更新进度时，mastery 最高为5，最低为1
4. 周报每周日生成，包含学习统计 + 推荐路径
