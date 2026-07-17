# Smart Agent AI 分析质量验收标准

## 硬性指标（必须达标）

| # | 指标 | 标准 | 测量方法 |
|---|---|---|---|
| 1 | 7 Agent 全部产出 | 无 Agent 返回空 | `len(result["xxx_report"]) > 0` |
| 2 | 字数达标 | 每条分析 > 50 字 | 字符数检查 |
| 3 | 中文输出 | 无英文/乱码 | 正则检查 `[一-鿿]` |
| 4 | 结构化 | 返回 dict/list 非纯文本 | `isinstance(result, dict)` |
| 5 | 响应时间 | < 60 秒 (3条数据) | 计时 |

## 软性指标（越高越好）

| # | 指标 | 优秀 | 合格 | 不合格 |
|---|---|---|---|---|
| 6 | 爆款评分合理性 | 50-95 分有明显区分度 | 全是 80-90 分 | 全是 100 分 |
| 7 | 情绪分析准确度 | 正面/负面比例合理 | 有区分 | 全是中性 |
| 8 | 文案可发布性 | 可直接复制粘贴发布 | 需要小改 | 无法使用 |
| 9 | 分析具体性 | 有具体数据/案例支撑 | 有一定分析 | 空话套话 |
| 10 | 相关性 | 紧密围绕关键词 | 基本相关 | 跑题 |

## 模型基准（不同模型的期望分数）

| 模型 | 硬性指标 | 软性指标 |
|---|---|---|
| Claude Opus 4 / Grok 4.5 | 5/5 | 15+/20 |
| DeepSeek V4 Pro | 5/5 | 12-15/20 |
| 豆包 pro-32k / DeepSeek V3 | 4-5/5 | 8-12/20 |
| Ollama qwen3:32b | 3-4/5 | 6-10/20 |

## 运行验收命令

```bash
python -c "
from src.orchestrator import run_pipeline
import asyncio, json, time
async def test():
    r = await run_pipeline(keyword='AI工具', limit=3, llm_filter=True, pipeline_mode='full', platforms=['bilibili'])
    # 检查 5 项硬性指标
    checks = sum(1 for k in ['trend_reports','product_report','video_report','sentiment_report','copy_report'] if r.get(k))
    print(f'硬性指标: {checks}/5')
    # 展示关键Agent样本
    print(json.dumps(r.get('trend_reports',{}), ensure_ascii=False, indent=2)[:500])
asyncio.run(test())
"
```
