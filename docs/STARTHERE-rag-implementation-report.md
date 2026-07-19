# Smart Agent Pro Memory (RAG) 实施报告

**报告日期**：2026-07-18
**Commit**：`57b7a91` feat(memory): 加 Chroma + sentence-transformers 跨任务记忆
**基于**：STARTHERE 第 6/13/16 章启发 + v3 gap 分析

---

## 🎯 TL;DR

✅ **完成 Smart Agent Pro 嘅「跨任务记忆」（RAG）**：

| 模块 | 文件 | 行数 | 状态 |
|------|------|------|------|
| Embeddings | `src/memory/embeddings.py` | 75 | ✅ Lazy load BAAI/bge-small-zh-v1.5 |
| Store | `src/memory/store.py` | 119 | ✅ Chroma 持久化（cosine） |
| Recall | `src/memory/recall.py` | 84 | ✅ save + recall API |
| 集成 | `pipeline.py` | +26 | ✅ Optional save（默认关） |
| 测试 | `tests/test_memory.py` | 120 | ✅ 5/5 PASS |

**测试结果**：
- Memory tests: **5/5 PASS**
- Smoke: 5/5
- 全量: **81/82** (+5 memory, 1 known env fail)

---

## 一、设计原则（按 smart-agent CLAUDE.md）

### 「最小可信改动」3 原则

1. **Low-Hanging Fruit**：用现成开源工具（Chroma + sentence-transformers），不造轮子
2. **Explicit Uncertainty**：MEMORY_SAVE_ENABLED 默认 False（避免 silent overhead）
3. **测试唔好过设计**：5 个 test 覆盖核心路径（embed + store + recall + save + reset）

### 向后兼容

- ✅ `MEMORY_SAVE_ENABLED=False` 默认——唔影响现有 pipeline
- ✅ Memory 模块独立——graph.py 唔改动（compile 唔会触发 embedding load）
- ✅ Optional integration——run_pipeline 完成后 try/except 包住，唔影响主流程
- ✅ 失败 graceful degradation——Memory save 失败只 warn，唔 throw

---

## 二、关键技术决策

### 1. Embedding 模型选择

| 选项 | 大小 | 维度 | 中文 | 选 |
|------|------|------|------|---|
| BAAI/bge-small-zh-v1.5 ✅ | 93MB | 512 | ✅ SOTA | ✅ 选 |
| shibing624/text2vec-base-chinese | 400MB | 768 | ✅ | ❌ 太大 |
| OpenAI text-embedding-3-small | API | 1536 | ✅ | ❌ 需 API key |
| Ollama nomic-embed-text | 已删除 | 768 | ⚠️ | ❌ 旧模型删咗 |

**最终**：`BAAI/bge-small-zh-v1.5`（参考章 16 CogVLM2 嘅 `shibing624/text2vec-base-chinese` 思路但用更轻量嘅 BGE）

### 2. Vector DB 选择

| 选项 | 优点 | 缺点 |
|------|------|------|
| Chroma ✅ | 纯 Python，零部署，Persistent API | 大规模性能一般 |
| FAISS | 高性能 | 需手动管理持久化 |
| pgvector | 成熟 | 需 PostgreSQL |

**最终**：Chroma（参考章 6 DB-GPT AWEL + 章 13 LlamaIndex 嘅索引思路）

### 3. Apple Silicon 加速

```python
device = "mps" if torch.backends.mps.is_available() else "cpu"
```

M2 Max 实测：
- Model 加载：11.6s（首次）
- Encode 3 句：0.56s

### 4. Lazy Loading 策略

```python
_EMBEDDING_MODEL = None  # 模块级 singleton

def _load_model():
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is not None:
        return _EMBEDDING_MODEL
    _EMBEDDING_MODEL = SentenceTransformer(...)
    return _EMBEDDING_MODEL
```

**好处**：
- `import src.memory` 唔会触发 11s 加载
- Smoke test 5/5 维持 0.02s
- 只有实际用 memory 嘅时候先加载

---

## 三、模块 API

### 3.1 Embeddings

```python
from src.memory.embeddings import encode_texts, get_embedding_dim, get_embedding_device

emb = encode_texts(["你好", "Hello"])  # 2 x 512
print(get_embedding_dim())   # 512
print(get_embedding_device())  # mps
```

### 3.2 MemoryStore

```python
from src.memory.store import MemoryStore

store = MemoryStore()  # 默认 output/chroma/
store.add("id1", "美妆视频好火", {"score": 85})

results = store.query("美妆化妆", n_results=2)
# [{"id": ..., "text": ..., "metadata": ..., "distance": ...}, ...]

print(store.count())  # 1
store.reset()
```

### 3.3 Recall API

```python
from src.memory.recall import save_task_result, recall_similar_tasks, reset_memory

# Save task result
doc_id = save_task_result(
    keyword="AI Agent",
    summary="2026 AI Agent 赛道火热...",
    metadata={"score": 88},
)
print(doc_id)  # "8cc152701ddf0805"

# Recall 同 keyword 相似嘅历史
results = recall_similar_tasks("智能体", top_k=3)
for r in results:
    print(r["metadata"]["keyword"], r["text"][:50])
```

### 3.4 Pipeline 集成

```bash
# 启用（默认关）
export MEMORY_SAVE_ENABLED=true
python main.py  # 自动 save task result
```

```python
# 或代码启用
import os
os.environ["MEMORY_SAVE_ENABLED"] = "true"
```

---

## 四、配置（settings.py）

```python
# Memory (RAG / 跨任务 recall) — 源：高强文书第 6/13/16 章
MEMORY_SAVE_ENABLED: bool = False          # 默认关，避免 silent overhead
MEMORY_CHROMA_PATH: str = "output/chroma"  # Chroma 持久化路径
MEMORY_EMBED_MODEL: str = "BAAI/bge-small-zh-v1.5"  # sentence-transformers model
```

环境变量：
```bash
MEMORY_SAVE_ENABLED=true|false
MEMORY_CHROMA_PATH=/custom/path
MEMORY_EMBED_MODEL=other/model-name
```

---

## 五、测试覆盖

`tests/test_memory.py`（5/5 PASS，11.7s 含首次 model 加载）：

| Test | 验证内容 |
|------|---------|
| `test_embeddings_chinese` | encode 中文 + 英文 + mixed，dim=512，device=mps |
| `test_memory_store_add_and_query` | add + semantic query 准确（"美妆化妆" → "美妆视频好火"）|
| `test_memory_store_empty_query` | 空 store query 返 `[]` 唔 crash |
| `test_save_task_result_and_recall` | save → recall 闭环 work，metadata 保留 |
| `test_reset_memory` | reset 清空 store |

---

## 六、依赖

新增（已装入 venv）：
```
chromadb==1.5.9
sentence-transformers==5.6.0
# PyTorch + MPS（已有）
# Auto-download: BAAI/bge-small-zh-v1.5（93MB，首次 import）
```

---

## 七、未来优化（v3 剩余 Gap）

### 🔴 仍可做（按 STARTHERE-v3-gap-analysis.md）

1. **以文搜图**（章 16 CogVLM2）
   - 复用 Chroma + sentence-transformers 基础设施
   - 加 image embedding（用 CLIP 或 imagebind）
   - video_cloner 出图 → image vector store
   - 估时：2-3 天

2. **MemGPT 5 层虚拟上下文**（章 3）
   - system / core_memory / recall_storage 3 层 → 5 层
   - 短 / 长 / 任务 / 反思 / 项目记忆
   - 估时：5-7 天

### 🟡 中等优先

3. **AWEL 3 层 Skill**（承接 P2）
   - 把现有 7 agent 拆解为 operators
   - 加 DSL + AgentFrame
   - 估时：3-5 天

4. **AutoGen 嵌套对话加深**
   - multi-tier review（per-agent → cross → meta-reviewer）
   - 估时：2-3 天

5. **OUTPUT IN CHINESE 统一**
   - base.py 加统一 prompt 模板
   - 估时：0.5 天

---

## 八、最终 Git 状态

```
57b7a91 feat(memory): 加 Chroma + sentence-transformers 跨任务记忆
a3aa4c5 fix(cross_verifier): 修复 sentiment/trend key 名不匹配 bug
b996b71 feat: 加 CrossVerifier + SQLiteSaver + Skill 抽象
e2e2fe1 docs: AI Agent质量验收标准——硬性5项+软性5项+模型基准
```

### STARTHERE 系列 commits（累计）

| Commit | 模块 | 测试增量 |
|--------|------|----------|
| `b996b71` | CrossVerifier + SQLiteSaver + Skill 抽象 | +6 Skill tests |
| `a3aa4c5` | CrossVerifier bug fix | - |
| `57b7a91` | Memory (RAG) | +5 Memory tests |

**总计**：3 commits，~3000 行新增代码，11 个新 test 全部 PASS

---

## 九、使用流程（开发者指南）

### 默认行为（不启用）

```bash
# 默认 MEMORY_SAVE_ENABLED=False，pipeline 唔触发 memory
python main.py
```

### 启用 Memory

```bash
# 方法 1: 环境变量
export MEMORY_SAVE_ENABLED=true
python main.py

# 方法 2: 在 .env 加
echo "MEMORY_SAVE_ENABLED=true" >> .env

# 方法 3: 临时启用
python -c "
import os
os.environ['MEMORY_SAVE_ENABLED'] = 'true'
import asyncio
from src.orchestrator.pipeline import run_pipeline
result = asyncio.run(run_pipeline('AI Agent', pipeline_mode='full'))
"
```

### 查看 Memory 内容

```python
from src.memory import MemoryStore

store = MemoryStore()
print(f"已记忆任务数: {store.count()}")
for r in store.query("美妆", n_results=5):
    print(f"- {r['metadata']['keyword']}: {r['text'][:80]}")
```

---

**报告生成**：2026-07-18 22:25
**生成者**：Claude Code (MiniMax-M3)
**总耗时**：~1 小时实施（装 deps + 写模块 + 5 test + 集成 + commit）

下一步可做（按 v3 优先级）：
1. **以文搜图**（2-3 天，🔴 衔接 video_cloner）
2. **OUTPUT IN CHINESE 统一**（0.5 天，🟢 最简单）
3. 跑一次 end-to-end pipeline（启用 MEMORY_SAVE_ENABLED，验证 recall）