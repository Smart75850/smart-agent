"""Copy Writer Agent — 生成營銷文案。

Flow:
  1. 接收 Trend Scout / Product Miner / Video Analyst 結果
  2. DeepSeek LLM 根據分析生成多版本營銷文案
  3. 輸出文案列表

用法:
  writer = CopyWriter()
  report = await writer.run(trend_items=trends, products=products, video_breakdowns=breakdowns)
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Literal

from pydantic import BaseModel, Field

from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger


# ── Pydantic 结构化输出模型 ─────────────────────────────────

class CopyVariantOutput(BaseModel):
    variant: Literal["headline", "short", "medium", "long"] = Field(description="变体类型")
    text: str = Field(min_length=8, description="完整文案")
    tone: str = Field(min_length=4, description="语气风格")
    target_platform: Literal["douyin", "xiaohongshu", "bilibili", "zhihu", "kuaishou"] = Field(description="目标平台")
    hook: str = Field(min_length=6, description="具体钩子手法，15字以上，如'时间锚定+价格反差'")
    cta: str = Field(min_length=4, description="行动号召")
    why_it_works: str = Field(min_length=20, description="在此平台的传播机制解释，含平台用户行为特征")


class CopyWriterOutput(BaseModel):
    summary: str = Field(min_length=20, description="文案策略，40字以上")
    variants: list[CopyVariantOutput] = Field(min_length=2, description="文案变体列表（至少2个）")


@dataclass
class CopyVariant:
    variant: str = ""
    text: str = ""
    tone: str = ""
    target_platform: str = ""
    hook: str = ""
    cta: str = ""
    why_it_works: str = ""


@dataclass
class CopyReport:
    keyword: str
    total_variants: int
    variants: list[CopyVariant] = field(default_factory=list)
    summary: str = ""


class CopyWriter(BaseAgent):
    """營銷文案生成 Agent。"""

    async def run(
        self,
        keyword: str = "",
        trend_items: list = None,
        products: list = None,
        video_breakdowns: list = None,
    ) -> CopyReport:
        if not self._api_key:
            return self._fallback(keyword or "通用")

        return await self._llm_generate(
            keyword=keyword,
            trend_items=trend_items or [],
            products=products or [],
            video_breakdowns=video_breakdowns or [],
        )

    async def as_node(self, state: dict) -> dict:
        keyword = state.get("keyword", "")
        trend_data = state.get("trend_reports", {})
        product_data = state.get("product_report", {})
        video_data = state.get("video_report", {})

        report = await self.run(
            keyword=keyword,
            trend_items=[it for r in trend_data.values() for it in (r.get("items", []) if isinstance(r, dict) else [])],
            products=product_data.get("items", []) if isinstance(product_data, dict) else [],
            video_breakdowns=video_data.get("items", []) if isinstance(video_data, dict) else [],
        )

        return {"copy_report": asdict(report)}

    # ── Few-Shot 示例庫（8 好 + 2 壞）──────────────────────

    _FEWSHOT_GOOD = [
        # -- headline 变体 --
        {"variant": "headline", "target_platform": "douyin", "topic": "蓝芽耳机",
         "hook": "时间锚定（3年）+价格反差（59 vs AirPods千元）",
         "output": "用了3年AirPods，这个59块的居然更好用",
         "why_it_works": "抖音用户0.5秒决定划走，数字对比+品牌锚定制造认知缺口，时间锚定增加可信度"},
        {"variant": "headline", "target_platform": "xiaohongshu", "topic": "平价护肤品",
         "hook": "效果承诺+成分背书+人群精准",
         "output": "学生党必看！成分党扒完这瓶50块的面霜，成分居然和300块的一样",
         "why_it_works": "小红书用户偏好'成分党''扒皮'等专业感词汇+价格对比，学生党精准人群标签触发共鸣"},

        # -- short 变体 --
        {"variant": "short", "target_platform": "douyin", "topic": "AI效率工具",
         "hook": "效率对比+社交证明+结果承诺",
         "output": "这个AI工具让我1小时干完3天活🔥 同事全都跑来问我用的什么…\n#AI工具 #效率提升 #打工人",
         "why_it_works": "抖音效率类高互动公式：具体数字对比+社交证明+'打工人'情绪标签触发共鸣转发"},

        # -- medium 变体 --
        {"variant": "medium", "target_platform": "xiaohongshu", "topic": "居家健身",
         "hook": "痛点场景+低成本方案+前后对比",
         "output": "🏠 不用去健身房！我在家练了30天，体态变化太明显了\n\n每天就15分钟，一个瑜伽垫+两根弹力带就够了。\n重点练这3个动作，圆肩驼背真的能改善…\n\n📌 动作教程放最后一张图了，记得截图保存！\n\n#居家健身 #体态矫正 #不用器械",
         "why_it_works": "小红书收藏型内容公式：低成本方案+具体天数+可保存的教程，'最后一张图'驱动完播+收藏"},

        # -- long 变体 --
        {"variant": "long", "target_platform": "bilibili", "topic": "AI工具测评",
         "hook": "反常识结论+实测数据+信息差",
         "output": "【深度测评】我花了200小时测了10款AI写作工具，结果出乎意料\n\n先说结论：200元/月的不一定比免费的好用。\n\n我测试了：ChatGPT / Claude / DeepSeek / Kimi / 豆包 / 文心一言 / 通义千问 / 智谱清言 / Coze / Copilot\n\n测评维度：中文流畅度、逻辑深度、创意能力、格式规范、长文稳定性…\n\n最大的发现是：对于中文长文写作，排名第一的居然是[悬念]\n\n具体数据和对比表格在视频里，建议1.5倍速观看。\n\n#AI工具 #写作 #测评",
         "why_it_works": "B站用户偏爱'硬核测评'类内容，数字列举+反常识结论+悬念设计驱动完播，信息密度高满足知识需求"},

        # -- 更多变体 --
        {"variant": "short", "target_platform": "douyin", "topic": "美食教程",
         "hook": "数字简化+对比锚定+低门槛承诺",
         "output": "3种食材5分钟！做出比餐厅还好吃的早餐🍳\n厨房小白也能一次成功，详细步骤在最后！",
         "why_it_works": "抖音美食爆款公式：极低门槛承诺+时间锚定+对比引发好奇，'最后'驱动完播"},

        {"variant": "medium", "target_platform": "bilibili", "topic": "科技数码",
         "hook": "技术拆解+避坑指南+行业洞察",
         "output": "【揭秘】为什么你买的充电器这么容易坏？充电头工厂老师傅说了实话\n\n市面上90%的快充头都在偷工减料。我去了趟深圳充电头工厂，聊了3位做了十年的老师傅。\n\n他们告诉我：判断一个充电头好坏，看这3个地方就够了…\n\n#数码科普 #充电器 #避坑",
         "why_it_works": "B站'行业揭秘'类内容天然高点击，工厂实地探访增加真实感，3点判断提供收藏价值"},

        {"variant": "long", "target_platform": "zhihu", "topic": "职场成长",
         "hook": "亲身经历+数据支撑+方法论提炼",
         "output": "30岁从大厂裸辞创业一年，我复盘了5个关键决策\n\n一年前我从字节跳动离职，all in自己的项目。\n\n这一年经历了：\n- 前3个月0收入\n- 第4个月找到第一个客户\n- 第8个月月利润突破10万\n- 现在稳定在15-20万/月\n\n回头看，最关键的5个决策与大多数人想的不一样…\n\n#创业 #职场 #复盘",
         "why_it_works": "知乎偏好'亲身经历+方法论'类内容，年龄/公司等具体标签建立可信度，数字时间线增强说服力"},
    ]

    _FEWSHOT_BAD = [
        {"variant": "headline", "why_bad": "❌ 无差异化信息——'好用的耳机推荐'没有说为什么好用、对谁好用、多少钱。标题需要包含至少一个差异化锚点（价格/人群/场景/效果）",
         "output": "好用的耳机推荐"},
        {"variant": "short", "why_bad": "❌ 跨平台仅加emoji——从抖音改小红书不能只是加几个emoji就完事。不同平台需要调整：语言节奏（快→慢）、信息密度（低→高）、情绪基调（兴奋→精致）、互动方式（关注→收藏）。这个改写完全没有体现平台差异",
         "output": "用了3年AirPods，这个59块的居然更好用✨✨ #好物分享"},
    ]

    async def _llm_generate(
        self,
        keyword: str,
        trend_items: list,
        products: list,
        video_breakdowns: list,
    ) -> CopyReport:
        context_parts = [f"核心關鍵詞: {keyword or '爆款內容'}"]
        if trend_items:
            titles = [it.get("title", it.title if hasattr(it, 'title') else "")[:40] for it in trend_items[:5]]
            context_parts.append(f"爆款趨勢: {', '.join(titles)}")
        if products:
            names = [p.get("name", p.name if hasattr(p, 'name') else "")[:30] for p in products[:5]]
            context_parts.append(f"選品: {', '.join(names)}")
        if video_breakdowns:
            hooks = [v.get("hook_type", v.hook_type if hasattr(v, 'hook_type') else "")[:20] for v in video_breakdowns[:3]]
            context_parts.append(f"爆款鉤子: {', '.join(hooks)}")

        good_examples_text = "\n".join(
            f"  ✅ [{ex['variant']}] {ex.get('target_platform','')} | {ex.get('topic','')}\n     钩子: {ex['hook']}\n     文案: {ex['output'][:100]}\n     传播机制: {ex['why_it_works']}"
            for ex in self._FEWSHOT_GOOD
        )
        bad_examples_text = "\n".join(
            f"  ❌ [{ex['variant']}]\n     {ex['why_bad']}\n     示例: {ex['output'][:60]}"
            for ex in self._FEWSHOT_BAD
        )

        # 4-Block Prompt
        prompt = f"""<instructions>
你是资深营销文案专家。为给定关键词生成4个可直接发布的文案变体（headline/short/medium/long），每个针对不同平台。

强制规则：
1. headline: 20字内纯标题 | short: 50-80字 | medium: 80-150字 | long: 150-300字
2. 每个变体必须明确 target_platform，必须不同（禁止所有变体同一平台），不可用"通用"
3. 平台特征必须体现：
   抖音=快节奏口語+强情绪+数字+悬念驱动
   小红书=精致真实+emoji丰富+种草感+收藏驱动
   B站=深度+幽默+圈层共鸣+完播驱动
   知乎=理性分析+方法论+亲身经历+赞同驱动
   快手=真实接地气+方言亲切+直播预告+老铁互动
4. hook必须用具体手法描述（如"时间锚定+价格反差"），禁用"引人注意""吸引眼球"等空泛词
5. why_it_works必须引用该平台的用户行为特征（如"抖音用户0.5秒决定划走""小红书用户收藏即认同"）
6. cta必须是具体行动（如"截图保存""@你需要的朋友""评论区说说你的看法"），禁用"关注""点赞"等通用CTA
</instructions>

<context>
{" | ".join(context_parts)}
</context>

<examples>
## 正例
{good_examples_text}

## 负例
{bad_examples_text}
</examples>

<task>
基于以上分析结果，生成4个营销文案变体（headline/short/medium/long），每个必须针对不同平台。
</task>

<output_format>
返回纯JSON，严格按以下Schema：
{{"summary": "文案策略概述（40字以上）",
 "variants": [{{"variant": "headline/short/medium/long",
   "text": "完整文案（headline 20字内/short 50-80字/medium 80-150字/long 150-300字）",
   "tone": "语气风格",
   "target_platform": "douyin/xiaohongshu/bilibili/zhihu/kuaishou",
   "hook": "具体钩子手法（15字以上）",
   "cta": "行动号召",
   "why_it_works": "在此平台的传播机制（20字以上，含平台用户行为特征）"}}]}}
</output_format>"""

        try:
            output = await self._call_llm_with_critic(prompt, CopyWriterOutput, "copy_writer", temperature=0.7, max_tokens=4000)

            variants = [
                CopyVariant(
                    variant=v.variant, text=v.text, tone=v.tone,
                    target_platform=v.target_platform, hook=v.hook,
                    cta=v.cta, why_it_works=v.why_it_works,
                )
                for v in output.variants
            ]

            return CopyReport(
                keyword=keyword or "通用",
                total_variants=len(variants),
                variants=variants,
                summary=output.summary,
            )
        except Exception as exc:
            logger.warning(f"CopyWriter LLM 失敗: {exc}")
            return self._fallback(keyword, trend_items, products, video_breakdowns)

    def _fallback(
        self,
        keyword: str,
        trend_items: list = None,
        products: list = None,
        video_breakdowns: list = None,
    ) -> CopyReport:
        """降级模式：基于输入数据生成多平台差异化模板文案。"""
        trend_hint = ""
        if trend_items:
            titles = [it.get("title", it.title if hasattr(it, 'title') else "")[:30] for it in trend_items[:3]]
            trend_hint = "、".join(titles) if titles else keyword

        product_hint = ""
        if products:
            names = [p.get("name", p.name if hasattr(p, 'name') else "")[:20] for p in products[:3]]
            product_hint = "、".join(names) if names else ""

        hook_hint = ""
        if video_breakdowns:
            hooks = [v.get("hook_type", v.hook_type if hasattr(v, 'hook_type') else "")[:15] for v in video_breakdowns[:2]]
            hook_hint = "、".join(hooks) if hooks else ""

        topic = product_hint or trend_hint or keyword or "爆款内容"
        hook_ref = f"（爆款鉤子: {hook_hint}）" if hook_hint else ""

        variants = [
            CopyVariant(
                variant="headline",
                text=f"{topic}，结果出乎意料！"[:20],
                tone="悬念式",
                target_platform="douyin",
                hook=f"反常识+结果悬念{hook_ref}",
                cta="看到最后有彩蛋",
                why_it_works="抖音悬念类标题0.5秒制造好奇，驱动完播率",
            ),
            CopyVariant(
                variant="short",
                text=f"终于有人把{topic}说清楚了🔥\n收藏起来慢慢看，真的好用！\n#干货分享 #避坑指南",
                tone="热情实用",
                target_platform="xiaohongshu",
                hook=f"信息不对称打破+收藏价值{hook_ref}",
                cta="收藏+@你需要的朋友",
                why_it_works="小红书收藏型内容长尾流量好，话题标签提升搜索曝光",
            ),
            CopyVariant(
                variant="medium",
                text=f"【揭秘】{topic}背后的真相\n\n我研究了这个领域一个月，发现3个大多数人不知道的关键点：\n1. ...\n2. ...\n3. ...\n\n建议1.5倍速观看，干货密度很高。\n\n#深度解析 #行业洞察",
                tone="深度理性",
                target_platform="bilibili",
                hook=f"数据支撑+信息差+数字列举{hook_ref}",
                cta="评论区说说你的看法",
                why_it_works="B站用户偏好深度内容，弹幕互动率高，数字列举适合分段解说",
            ),
            CopyVariant(
                variant="long",
                text=f"我研究了{topic}后，总结了一套方法论\n\n先说结论：这个领域最核心的规律只有3条。\n\n第一条：...\n第二条：...\n第三条：...\n\n为什么大多数人做不到？因为…\n\n这套方法论我实践了3个月，数据如下：...\n\n希望对你有帮助。\n\n#方法论 #实战复盘",
                tone="理性真诚",
                target_platform="zhihu",
                hook=f"亲身实践+方法论提炼+结果展示{hook_ref}",
                cta="觉得有用请赞同让更多人看到",
                why_it_works="知乎偏好方法论+亲身经历，赞同机制让高质量内容持续获得长尾流量",
            ),
        ]

        return CopyReport(
            keyword=keyword or "通用",
            total_variants=len(variants),
            variants=variants,
            summary="LLM 不可用，降级为多平台差异化模板文案",
        )
