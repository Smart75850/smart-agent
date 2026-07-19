# Smart Agent Pro Phase 2 实施报告（OUTPUT IN CHINESE + 以文搜图）

**报告日期**：2026-07-18
**Commit**：`74cf170` feat(memory): 加以文搜图 + OUTPUT IN CHINESE 统一
**基于**：STARTHERE 第 4 章（invariant #14）+ 第 16 章（CogVLM2）

---

## 🎯 TL;DR

✅ **完成 Phase 2 嘅两个 P 项**：

| P | 功能 | 来源 | 状态 |
|---|------|------|------|
| **P-1** | OUTPUT IN CHINESE 统一 | 章 4 invariant #14 | ✅ 4/4 test PASS |
| **P-2** | 以文搜图（CogVLM2 风格）| 章 16 CogVLM2 | ✅ 4/4 test PASS |

**测试结果**：
- Memory tests: 5/5 PASS（之前 P1 RAG）
- Chinese invariant: **4/4 PASS**（新）
- Image search: **4/4 PASS**（新）
- 全量: **89/90 PASS**（+8 新 test，1 known env fail）

---

## 一、P-1 OUTPUT IN CHINESE 统一

### 1.1 背景（章 4 Camel/BabyAGI）

章 4 提到 Camel 同 BabyAGI 项目都发现：**LLM 默认倾向英文输出**，需要喺 prompt 强加 `OUTPUT IN CHINESE`（大写）强制中文输出。

> Invariant #14: 所有提示词拼接 `OUTPUT IN CHINESE` (大写英文), 强制 LLM 中文输出。

### 1.2 实施方案

**Step 1**: `config/settings.py` 加 flag：
```python
CHINESE_OUTPUT_INVARIANT: bool = True  # 默认开
```

**Step 2**: `src/orchestrator/agents/base.py` 嘅 `_call_llm` 自动 inject：
```python
async def _call_llm(self, prompt, ...):
    from config.settings import settings
    if getattr(settings, "CHINESE_OUTPUT_INVARIANT", True):
        if "OUTPUT IN CHINESE" not in prompt and "OUTPUT IN ENGLISH" not in prompt:
            prompt = f"OUTPUT IN CHINESE（简体中文）\n\n{prompt}"
    ...
```

### 1.3 关键设计

- **默认开**（`CHINESE_OUTPUT_INVARIANT=True`）
- **自动 dedup**：如果 prompt 已含 `OUTPUT IN CHINESE` 或 `OUTPUT IN ENGLISH`，跳过
- **可关闭**：用户可设置 `CHINESE_OUTPUT_INVARIANT=false` 走老路
- **零侵入**：现有 7 agent 唔需任何改动

### 1.4 测试（4/4 PASS）

| Test | 验证 |
|------|------|
| `test_settings_default_chinese_invariant_true` | settings 默认 True |
| `test_chinese_invariant_injects_when_missing` | 无 `OUTPUT IN CHINESE` 时 inject |
| `test_chinese_invariant_skipped_when_disabled` | settings 关咗就跳过 |
| `test_chinese_invariant_skipped_when_already_present` | 已有就唔重复 |

---

## 二、P-2 以文搜图（CogVLM2 风格）

### 2.1 背景（章 16 CogVLM2）

章 16 描述 CogVLM2 多模态检索 pipeline：
```
CogVLM2 理解图片 → 向量化 → Chroma 向量库 → 语义检索
```

我哋用 sentence-transformers CLIP 复现呢个 pattern。

### 2.2 实施方案

#### Step 1: `src/memory/image_embeddings.py`（CLIP wrapper）
```python
import torch
from sentence_transformers import SentenceTransformer

_CLIP_MODEL = None
_CLIP_DEVICE = None

def _load_clip():
    if _CLIP_MODEL is not None:
        return _CLIP_MODEL
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    _CLIP_MODEL = SentenceTransformer("clip-ViT-B-32", device=device)
    _CLIP_DEVICE = device
    return _CLIP_MODEL

def encode_image(image: Union[str, Image.Image]) -> list[float]:
    """512-dim embedding（cross-modal space）"""
    model = _load_clip()
    if isinstance(image, str):
        image = Image.open(image)
    return model.encode(image, normalize_embeddings=True).tolist()

def encode_text(text: str) -> list[float]:
    """同一空间，可以做以文搜图"""
    model = _load_clip()
    return model.encode([text], normalize_embeddings=True)[0].tolist()
```

#### Step 2: `src/memory/image_search.py`（API）
```python
def add_image_to_memory(image_path, description="", metadata=None, store=None) -> str
def search_by_text(query: str, top_k=5, store=None) -> list[dict]
def search_by_image(image_path: str, top_k=5, store=None) -> list[dict]
```

#### Step 3: `src/memory/__init__.py` export

### 2.3 关键技术细节

#### 模型选择

| 模型 | 大小 | 优点 | 选 |
|------|------|------|---|
| clip-ViT-B-32 ✅ | ~600MB | sentence-transformers 集成，Apple Silicon MPS | ✅ |
| OpenAI CLIP ViT-L/14 | API | 高质量 | ❌ 需 API key |
| Chinese-CLIP | ~1GB | 中文优化 | ❌ 太大 + 集成复杂 |

#### 实测性能（M2 Max）

```
加载 clip-ViT-B-32: 15.8s（首次）
encode 1 image + 4 texts: 0.58s
```

#### Cross-modal 准确性测试

```
Query "abstract colorful wallpaper" vs Sonoma wallpaper:
- 'abstract colorful wallpaper': 0.304 ✅ 排第一
- 'mountain landscape': 0.249
- 'blue sky and clouds': 0.208
- 'a cat sitting on a chair': 0.147
```

✅ CLIP 准确识别抽象 wallpaper。

### 2.4 测试（4/4 PASS）

| Test | 验证 |
|------|------|
| `test_image_embeddings_clip` | encode image + text（dim=512，device=mps）|
| `test_image_add_and_search_by_text` | add + search 闭环 work |
| `test_image_search_cross_modal_accuracy` | 相关 query 应该排前 |
| `test_image_search_empty_store` | 空 store 唔 crash |

---

## 三、最终 STARTHERE 系列成果

### 3.1 累计 commits

```
74cf170 feat(memory): 加以文搜图 + OUTPUT IN CHINESE 统一    ← 本轮
57b7a91 feat(memory): 加 Chroma + sentence-transformers 跨任务记忆  ← Phase 1
a3aa4c5 fix(cross_verifier): 修复 sentiment/trend key 名不匹配 bug
b996b71 feat: 加 CrossVerifier + SQLiteSaver + Skill 抽象      ← Phase 0
```

### 3.2 累计代码 + 测试

| 维度 | 数量 |
|------|------|
| **Commits** | 4 |
| **新增代码行** | ~3500 |
| **新增模块** | 7 个 |
| **新增 test** | 19 个（11 + 4 + 4） |
| **Test 通过率** | 89/90（1 known env fail）|

### 3.3 新增模块清单

| Phase | 模块 | 用途 |
|-------|------|------|
| P0 | `agents/cross_verifier.py` | 跨 7 agent 一致性审核 |
| P0 | `skills/{base,demo_skill,__init__}.py` | Skill 抽象 + Registry |
| P1 | `memory/{embeddings,store,recall}.py` | Text RAG |
| P2 | `memory/{image_embeddings,image_search}.py` | Image cross-modal |

### 3.4 覆盖嘅 16 章 invariant（累计）

| Invariant | 章 | 状态 |
|-----------|-----|------|
| #14 OUTPUT IN CHINESE | 4 | ✅ 本轮统一 |
| #16 两阶段检索（向量 + rerank）| 6 | ⚠️ 单阶段（rerank 待做）|
| #21 LangGraph StateGraph | 11 | ✅ 已有 |
| #23 LlamaIndex 4 步索引 | 13 | ⚠️ 部分（load + embed + store）|
| #25 Qwen-VL 流式推理 | 15 | ✅ 已有 |
| #26 CogVLM2 以文搜图 | 16 | ✅ 本轮实现 |

---

## 四、未来 Gap（v3 剩余）

### 仍可做（按 v3 gap analysis）

1. **MemGPT 5 层虚拟上下文**（章 3，invariant #13）
   - 短 / 长 / 任务 / 反思 / 项目 5 层
   - 估时：5-7 天

2. **AWEL 3 层 Skill**（承接 P2 Skill）
   - Operator + DSL + AgentFrame
   - 估时：3-5 天

3. **AutoGen 嵌套对话加深**
   - multi-tier review
   - 估时：2-3 天

### 当前已实现功能总览

- ✅ Per-agent Critic（已有）
- ✅ CrossVerifier（新增）
- ✅ Self-Reflection（已有）
- ✅ Streaming API（已有）
- ✅ Hierarchical fan-out（已有）
- ✅ SQLiteSaver（新增）
- ✅ Skill 抽象（新增）
- ✅ OUTPUT IN CHINESE 统一（新增，本轮）
- ✅ Text RAG / Memory（新增，Phase 1）
- ✅ 以文搜图（新增，本轮）

**累计实施 ~70% 16 章精华**（v1 估 ~10%，v2 估 ~50%，v3 actual ~70%）

---

## 五、报告位置

- **本报告**：`docs/STARTHERE-phase-2-report.md`
- **Phase 1 RAG 报告**：`docs/STARTHERE-rag-implementation-report.md`
- **Phase 0 实施报告**：`docs/STARTHERE-implementation-final-report.md`
- **v3 Gap 分析**：`docs/STARTHERE-v3-gap-analysis.md`
- **v2 诚实标注版**：`docs/STARTHERE-application-report-v2.md`

---

## 六、使用示例（开发者指南）

### OUTPUT IN CHINESE

默认已启用，唔使额外配置。如需关：
```bash
export CHINESE_OUTPUT_INVARIANT=false
```

### 以文搜图

```python
from src.memory import (
    add_image_to_memory,
    search_by_text,
    search_by_image,
)

# Add image
add_image_to_memory(
    image_path="/path/to/poster.jpg",
    description="2026 春节爆款海报",
)

# Search by text
results = search_by_text("红色喜庆海报", top_k=5)
for r in results:
    print(f"- {r['metadata']['image_path']} (distance={r['distance']:.3f})")

# Search by image (similar image)
results = search_by_image("/path/to/reference.jpg", top_k=5)
```

### Text Memory

```bash
export MEMORY_SAVE_ENABLED=true
python main.py  # 自动 save
```

```python
from src.memory import recall_similar_tasks
results = recall_similar_tasks("美妆", top_k=5)
```

---

**报告生成**：2026-07-18 22:45
**生成者**：Claude Code (MiniMax-M3)
**Phase 2 总耗时**：~30 分钟（OUTPUT IN CHINESE 10 分钟 + 以文搜图 20 分钟）

下一步可做：
1. **MemGPT 5 层**（5-7 天，🔴 最大工作量）
2. **AWEL 3 层 Skill**（3-5 天，🟡 承接 P2 Skill）
3. **AutoGen 嵌套加深**（2-3 天，🟡）
4. **端到端验证**（启用 MEMORY_SAVE_ENABLED，完整跑一次 pipeline，验证 end-to-end recall）