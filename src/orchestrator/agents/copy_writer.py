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

from pydantic import BaseModel, Field

from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger


# ── Pydantic 结构化输出模型 ─────────────────────────────────

class CopyVariantOutput(BaseModel):
    variant: str = Field(description="文案类型：headline/short/medium/long")
    text: str = Field(description="完整文案内容")
    tone: str = Field(description="语气风格：热血/温情/专业/幽默/悬念/警告/惊喜")
    target_platform: str = Field(description="目标平台：douyin/xiaohongshu/bilibili")
    hook: str = Field(min_length=10, description="开头钩子设计说明，20字以上，含具体手法")
    cta: str = Field(description="行动号召，具体可执行的下一步")
    why_it_works: str = Field(min_length=15, description="传播机制解释，30字以上")


class CopyWriterOutput(BaseModel):
    summary: str = Field(min_length=25, description="文案策略总结，50字以上，含目标受众+核心卖点+情感调性+分发策略")
    variants: list[CopyVariantOutput] = Field(description="文案变体列表")


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

    # ── internal ──────────────────────────────────────────────

    # ── Few-Shot 示例庫（4 variant × 2 platform） ──────────
    _FEWSHOT_GOOD = [
        {"variant": "headline", "platform": "douyin",
         "text": "用了3年藍牙耳機，這個59塊的居然最好用",
         "tone": "反直覺", "hook": "時間錨定（3年）+ 價格反差（59 vs 千元）",
         "cta": "點擊購物車看看",
         "why": "數字對比建立信任+低價降低決策門檻，適合抖音衝動消費場景"},
        {"variant": "headline", "platform": "xiaohongshu",
         "text": "✨ 挖到寶了！這個小眾耳機美到犯規",
         "tone": "驚喜分享", "hook": "emoji視覺引導+小眾稀缺感+情緒詞（美到犯規）",
         "cta": "連結在主頁",
         "why": "小紅書用戶偏好'挖寶'敘事+emoji增加親切感，情緒詞驅動點擊"},
        {"variant": "short", "platform": "douyin",
         "text": "告別續航焦慮！這款耳機充一次用一週🎧\n我實測了7天，通勤+健身+追劇全場景續航測試\n結果出乎意料…點擊看完整測評👇",
         "tone": "真實測評", "hook": "痛點共鳴（續航焦慮）+ 實測承諾（7天）",
         "cta": "點擊看完整測評",
         "why": "場景化（通勤+健身+追劇）覆蓋多人群+實測增加可信度，抖音用戶信任'實測'標籤"},
        {"variant": "short", "platform": "bilibili",
         "text": "【硬核】市面10款耳機頻響曲線實測，數據不會騙人\n結果在置頂評論，建議先收藏再看",
         "tone": "專業理性", "hook": "【硬核】B站標配前綴+數據驅動（頻響曲線）+ 收藏引導",
         "cta": "結果在置頂評論",
         "why": "B站用戶偏好深度內容+數據背書，收藏引導提升互動數據"},
        {"variant": "medium", "platform": "xiaohongshu",
         "text": "🎧 百元內耳機天梯榜｜親測8款終於找到真命天子\n\n先說結論：XX款綜合最佳，但如果你預算有限，YY款性價比炸裂\n\n我從音質、續航、舒適度、通話降噪四個維度打分，整理成表格在最後一張圖\n\n先收藏⭐免得找不到！\n\n#藍牙耳機推薦 #平價好物 #數碼测评",
         "tone": "攻略乾貨", "hook": "榜單框架（天梯榜）+ 結論先行 + 四維度打分",
         "cta": "先收藏免得找不到 + 查看最後一張圖",
         "why": "攻略型內容在小紅書天然高收藏+表格圖增加保存率，hashtag覆蓋長尾搜索"},
        {"variant": "medium", "platform": "douyin",
         "text": "⚠️ 買耳機前必看！這3個參數比品牌重要100倍\n\n1️⃣ 頻響範圍 → 決定音質天花板\n2️⃣ 藍牙版本 → 5.3以上才穩\n3️⃣ 續航實測 → 別信官方數字\n\n記不住的截圖保存📸 轉發給你正要買耳機的朋友",
         "tone": "警告+教學", "hook": "⚠️警告語氣+反直覺（參數>品牌）+ 數字列舉（3個）",
         "cta": "截圖保存+轉發朋友",
         "why": "抖音用戶對'避坑'類內容互動率高，轉發引導擴大傳播"},
        {"variant": "long", "platform": "bilibili",
         "text": "【深度】我拆了5款熱門耳機，發現了廠商不說的秘密\n\n開頭：為什麼同一首歌在不同耳機裡聽起來完全不一樣？不是你的耳朵問題。\n\n主體：逐一拆解5款耳機的單元/腔體/調音棉，顯微鏡級對比。每個環節附測試數據+聽感評價。\n\n結論：200元和2000元耳機的差距到底在哪？哪些溢價是智商稅？哪些地方值得花錢？\n\n下期預告：自己DIY一條耳機到底難不難？關注不錯過。\n\n#硬核拆解 #HiFi #數碼科技",
         "tone": "深度科普", "hook": "拆解（物理破壞）+ 廠商秘密（信息不對稱）+ 問題式開場",
         "cta": "關注不錯過+評論區討論",
         "why": "B站長視頻觀眾偏好'顯微鏡級'深度+拆解有視覺衝擊，系列化提升關注率"},
        {"variant": "long", "platform": "xiaohongshu",
         "text": "💡 做了3年數碼博主，我總結了5條選耳機的底層邏輯\n\n1. 先定場景，再選耳機\n通勤→降噪優先｜運動→防水+穩固｜遊戲→低延遲\n\n2. 別被'Hi-Res'金標騙了\n那只是入場券，不代表好聽。真正要看的是…（展開500字深度分析）\n\n3-5. （篇幅限制，略）\n\n完整版圖文已整理在主頁置頂📌\n\n#數碼科普 #消費避坑 #耳機推薦",
         "tone": "行業揭秘", "hook": "身份背書（3年博主）+ 系統方法論（5條邏輯）+ 行業內幕",
         "cta": "主頁置頂看完整版",
         "why": "長圖文在小紅書的收藏率極高+系統方法論建立專家形象+系列化引導主頁流量"},
    ]

    _FEWSHOT_BAD = [
        {"variant": "headline", "platform": "douyin",
         "text": "好用的耳機推薦給大家", "tone": "平淡",
         "hook": "無", "cta": "無",
         "why": "❌ 錯誤示範：標題無差異化信息（哪款？為什麼好？對誰好？），在抖音0.5秒內就會被滑走"},
        {"variant": "medium", "platform": "bilibili",
         "text": "這款耳機音質不錯外觀也好看續航也可以總之挺好的推薦大家購買",
         "tone": "敷衍", "hook": "無", "cta": "無",
         "why": "❌ 錯誤示範：流水帳式堆砌優點無層次、無數據支撐、無具體對比對象、CTA缺失，B站用戶對'挺好''不錯'這類模糊詞零容忍"},
    ]

    async def _llm_generate(
        self,
        keyword: str,
        trend_items: list,
        products: list,
        video_breakdowns: list,
    ) -> CopyReport:
        """DeepSeek LLM 生成營銷文案（v2 增強 prompt）。"""
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
            f"  ✅ variant={ex['variant']} | {ex['platform']}\n     文案: {ex['text'][:80]}\n     語氣: {ex['tone']} | 鉤子: {ex['hook']} | CTA: {ex['cta']}\n     為何有效: {ex['why']}"
            for ex in self._FEWSHOT_GOOD
        )
        bad_examples_text = "\n".join(
            f"  ❌ variant={ex['variant']} | {ex['platform']}\n     文案: {ex['text'][:80]}\n     為何失敗: {ex['why']}"
            for ex in self._FEWSHOT_BAD
        )

        prompt = f"""你是資深營銷文案專家（CopyWriter），精通短視頻標題、小紅書種草文案、B站稿件標題的撰寫。

## 任務
基於分析結果，生成 4 個版本的營銷文案（headline/short/medium/long），每個版本針對不同平台特點，要可直接發佈的質量。

## 品質標準
- 好的文案：含具體數字/品牌名/價格對比（如「59元 vs 千元」而不是「平價」「便宜」）、鈎子設計可直接套用（如「用了3年XX，這個59塊的居然更好用」）、CTA 有明確行動（點擊/收藏/轉發）、語氣風格與平台一致（抖音=接地氣、小紅書=精緻、B站=硬核）
- 差的文案：無具體數字或品牌名（如「好用的耳機推薦」）、鈎子模糊無法套用（如「這個產品很好」）、CTA 缺失、堆砌關鍵詞無節奏、跨平台通用文案

## 具體性強制要求
- 每條文案的 why_it_works 必須包含：①目標人群描述（如「小紅書女性用戶25-35歲」）②具體數字（如「點擊率提升30%」）③平台特徵（如「抖音前3秒決定留存」）
- 每條文案的 text 中至少出現 1 個具體數字或品牌名

## 平台特徵速查
| 特徵 | 抖音 | 小紅書 | B站 |
|------|------|--------|-----|
| 節奏 | 快節奏，前3秒定生死 | 中等，標題+封面圖雙重吸引 | 慢節奏，深度內容為王 |
| 語言 | 口語化、接地氣、不裝 | 精緻、真實感、emoji豐富 | 深度、幽默、圈層共鳴 |
| 情緒基調 | 強情緒（驚/怒/喜/悲） | 溫馨真誠、分享型 | 理性+幽默並存 |
| 用戶預期 | 娛樂+快速獲取信息 | 種草+審美+生活靈感 | 深度學習+圈層認同 |
| 文案長度偏好 | 短（20-80字） | 中（80-300字） | 長（200-1000字） |

## 文案類型定義
- **headline**：純標題，20字內，用於視頻封面/縮略圖
- **short**：短文案，50-80字，用於抖音描述/小紅書標題欄
- **medium**：中等文案，80-150字，用於小紅書正文/抖音圖文
- **long**：長文案，150-300字，用於B站專欄/公眾號/小紅書深度筆記

## Few-Shot 正例（4 variant × 2 platform = 8 例）
{good_examples_text}

## Few-Shot 負例（避免以下錯誤）
{bad_examples_text}

## 邊界情況處理
- 無趨勢/選品數據：基於關鍵詞獨立創作，標註「獨立創作模式」
- 跨平台通用：不要生成「通用」文案，每條必須明確 target_platform
- 敏感品類（醫療/金融）：避開功效承諾，以科普/體驗角度撰寫

## 背景數據
{chr(10).join(context_parts)}"""

        try:
            output = await self._call_llm_with_critic(prompt, CopyWriterOutput, "copy_writer", temperature=0.7, max_tokens=4000)

            variants = [
                CopyVariant(
                    variant=v.variant,
                    text=v.text,
                    tone=v.tone,
                    target_platform=v.target_platform,
                    hook=v.hook,
                    cta=v.cta,
                    why_it_works=v.why_it_works,
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
            return self._fallback(keyword)

    def _fallback(self, keyword: str) -> CopyReport:
        return CopyReport(
            keyword=keyword,
            total_variants=1,
            variants=[CopyVariant(
                variant="short",
                text=f"🔥 爆款趨勢: {keyword}\n熱度持續上升中，把握機會！",
                tone="熱情",
                target_platform="xiaohongshu",
            )],
            summary="LLM 不可用，降級為模板文案",
        )
