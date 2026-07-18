# STARTHERE → Smart Agent Pro 剩余 Gap 分析（v3 完整审计）

**报告日期**：2026-07-18
**基于**：完整读 4 份 mavis 视角分析（覆盖 16 章 + 30 invariant）+ Smart Agent Pro 代码审计
**前轮已落地**：P0' CrossVerifier + P1.3 SQLiteSaver + P2 Skill 抽象
**本报告**：剩余 missed 优化机会 + 优先级 + 实施路径

---

## 🎯 TL;DR

本轮审计（完整读 4 份 mavis 视角分析）发现 **3 个大 Gap**（未实现）+ **4 个中 Gap**（部分实现）+ **1 个小 Gap**：

| 优先级 | 缺口 | 来源 invariant | 估时 | 价值 |
|--------|------|----------------|------|------|
| 🔴 P1 | **RAG / 长期记忆 + Embeddings** | #13, #16, #23 | 3-5 天 | **极大**（跨任务 recall + 知识积累）|
| 🔴 P1 | **MemGPT 5 层虚拟上下文** | #13 | 5-7 天 | **大**（长任务 context 保持）|
| 🔴 P2 | **以文搜图（CogVLM2 风格）** | #26 | 2-3 天 | 中（video_cloner 闭环）|
| 🟡 P3 | **AWEL 3 层 Skill 抽象** | #15 | 3-5 天 | 中（承接 P2 Skill）|
| 🟡 P4 | **AutoGen 嵌套对话加深** | #22 | 2-3 天 | 中（质量把关）|
| 🟡 P5 | **Plan-and-Execute 显式化** | #20 | 2-3 天 | 中（流程清晰）|
| 🟢 P6 | **OUTPUT IN CHINESE 强制 invariant** | #14 | 0.5 天 | 小（统一中文）|

---

## 一、完整 gap 分析（按 16 章启发）

### 🔴 Gap 1: RAG / 长期记忆 + Embeddings（最大缺口）

**来源 invariant**：
- **#13**: MemGPT 虚拟上下文 = mavis 5 层记忆
- **#16**: 两阶段检索（向量 + rerank）
- **#23**: LlamaIndex 4 步索引 = mavis memory

**Smart Agent Pro 现状**：
- ❌ **冇向量数据库**（Chroma / FAISS / pgvector）
- ❌ **冇 Embeddings 集成**（虽然 Qwen proxy 支持 `/v1/embeddings`，但冇 agent 用）
- ❌ **冇两阶段检索**（向量粗排 + cross-encoder rerank）
- ❌ **冇 4 步索引 pipeline**（装载 → 切分 → 向量化 → 存储）
- ❌ **冇跨任务 recall**（每次 pipeline 独立，无历史知识积累）

**借鉴范例**：
- **章 6 DB-GPT AWEL**：3 层架构（算子/DSL/AgentFrame）
- **章 6 QAnything**：两阶段检索（向量 + rerank）
- **章 13 LlamaIndex**：4 步索引（load → split → embed → store）
- **章 16 CogVLM2**：图片向量化 → 语义检索

**实施方案**：
```python
# 最小实现
1. 集成 Chroma（轻量向量数据库）
2. 用 Qwen proxy 嘅 /v1/embeddings endpoint
3. 加 src/memory/ 模块：
   - recall.py（两阶段检索）
   - index.py（4 步索引）
   - store.py（Chroma wrapper）
4. 集成入 pipeline：每个任务完成后写入历史，关键任务先 recall
```

**价值**：
- 跨任务 recall 类似分析结果
- 避免重复爬虫
- 知识累积（同一 topic 嘅历史分析可对比）
- 智能 deduplication

---

### 🔴 Gap 2: MemGPT 5 层虚拟上下文

**来源 invariant**：
- **#13**: MemGPT 虚拟上下文 = mavis 5 层记忆

**Smart Agent Pro 现状**：
- ⚠️ 短期 context：有（context length）
- ❌ 长期记忆：冇
- ❌ 任务记忆：冇
- ❌ 反思记忆：冇
- ❌ 项目记忆：冇

**借鉴范例**（章 3 MemGPT）：
- system（系统提示）
- core_memory（核心属性，可读写）
- recall_storage（向量数据库，外部检索）

**实施方案**：
```python
# 5 层记忆体系
1. 短期 (short_term): LangGraph state.context
2. 长期 (long_term): Chroma 向量库（历史 task + output）
3. 任务 (task): 当前 pipeline 嘅 task state
4. 反思 (reflection): Critic 历史反馈
5. 项目 (project): 同一 topic 嘅跨 session 累积
```

**价值**：
- 长任务保持 context（避免 token 爆）
- 跨 session 记忆（同一用户多次跑 pipeline 累积）
- 自反思（基于历史 Critic 反馈改进）

---

### 🔴 Gap 3: 以文搜图（CogVLM2 风格）

**来源 invariant**：
- **#26**: CogVLM2 以文搜图

**Smart Agent Pro 现状**：
- ✅ video_cloner 已经生成 pic（Midjourney/SD prompt）
- ❌ 但冇 recall「之前生成过咩 pic」
- ❌ 冇「睇图搜相似」功能
- ❌ 冇 image embedding 集成

**借鉴范例**（章 16 CogVLM2）：
- 图片理解 → 向量化 → Chroma 语义检索
- 用 text2vec-base-chinese 做 embedding

**实施方案**：
```python
1. video_cloner 出图后自动写入 image vector store
2. 加 image_recall skill：以文搜图
3. 新 Agent: image_searcher（接 trend_scout output，找相似爆款图）
```

**价值**：
- video_cloner 出图 recall（避免重复）
- 找历史相似爆款（做参考）
- 闭环：分析 → 出图 → recall 相似图

---

### 🟡 Gap 4: AWEL 3 层 Skill 抽象

**来源 invariant**：
- **#15**: AWEL 3 层架构（算子 / DSL / AgentFrame）

**Smart Agent Pro 现状**：
- ✅ P2 Skill ABC（基础，1 层）
- ❌ 算子层（atomic sub-skill operations）
- ❌ DSL 层（standardized syntax for skill invocation）
- ❌ AgentFrame 层（skill composition）

**借鉴范例**（章 6 DB-GPT AWEL）：
```python
# 算子层（atomic）
class LLMOperator: ...        # LLM 调用原子
class SearchOperator: ...     # 搜索原子
class FilterOperator: ...     # 过滤原子

# DSL 层（syntax）
skill_call("llm", prompt=..., model="qwen")
skill_call("search", query=..., platform="bilibili")

# AgentFrame 层（composition）
class AgentFrame:
    def __init__(self, operators: list): ...
    def compose(self) -> Workflow: ...
```

**实施方案**：
1. 把现有 7 agent 拆解为 operators
2. 加 DSL parser
3. 加 AgentFrame composition engine

**价值**：
- 可组合 skill（而唔系 hardcoded 7 agent）
- 动态 workflow
- 用户自定义 pipeline

---

### 🟡 Gap 5: AutoGen 嵌套对话加深

**来源 invariant**：
- **#22**: AutoGen 嵌套对话 = mavis verifier 反思

**Smart Agent Pro 现状**：
- ✅ CriticAgent（per-agent，1 层）
- ✅ CrossVerifier（全局，1 层）
- ❌ **冇嵌套**（AutoGen 嘅 multi-tier review）

**借鉴范例**（章 12 AutoGen）：
```
programer → reviewer → meta-reviewer → programer
   ↓          ↓            ↓
  生成      审核        meta 审核
```

**实施方案**：
```python
# 嵌套层级
Level 1: agent 自评 (CriticAgent 已有)
Level 2: 跨 agent 审核 (CrossVerifier 已有)
Level 3: meta-review（基于历史 trend + 当前 output）
Level 4: user_feedback loop（如有反馈历史）
```

**价值**：
- 更深入质量把关
- meta-level 错误检测（agent 自己 review 唔到的盲点）

---

### 🟡 Gap 6: Plan-and-Execute 显式化

**来源 invariant**：
- **#20**: Plan-and-Execute 4 阶段

**Smart Agent Pro 现状**：
- ⚠️ 隐式 plan（graph 有 search → analyze → format）
- ❌ **冇显式 Planner node**

**借鉴范例**（章 10 LangChain Plan-and-Execute）：
```
阶段 1: 理解任务（输入 → 意图）
阶段 2: 制订计划（任务分解 + 依赖）
阶段 3: 执行计划（按依赖顺序跑 agent）
阶段 4: 结果总结（聚合 + critic）
```

**实施方案**：
```python
# 加 Planner node
async def planner(state) -> dict:
    # 1. 理解 keyword（query rewriting）
    # 2. 制订计划（agent 依赖图）
    # 3. 选择哪些 agent（动态）
    # 4. 输出 execution plan
```

**价值**：
- 任务分解更清晰
- 动态选择 agent（唔系全部跑）
- 节省 token（唔需要嘅 agent 唔跑）

---

### 🟢 Gap 7: OUTPUT IN CHINESE 强制 invariant

**来源 invariant**：
- **#14**: OUTPUT IN CHINESE 强制中文

**Smart Agent Pro 现状**：
- ⚠️ 部分 prompt 有 `OUTPUT IN CHINESE`
- ❌ 冇统一 enforcing

**实施方案**：
```python
# base.py 加
DEFAULT_SYSTEM_PROMPT = "你必须用中文（简体）回答所有问题。"
# 自动 inject 到每个 prompt 末尾
```

**价值**：小改动（0.5 天），统一性 + 减少英文输出概率。

---

## 二、按 16 章 invariant 完整对照表

| Invariant | 来源章 | Smart Agent 现状 | Gap 严重性 |
|-----------|--------|------------------|------------|
| #9 Agent 4 组件 | 1 | ✅ Planning/Memory/Tools/Action 部分 | Memory 缺口 |
| #10 LLM 服务 3 选 1 | 2 | ✅ Ollama + proxy | 无 |
| #11 OpenAI 3 大端点 | 2 | ⚠️ Chat ✅ Models ✅ **Embeddings ❌** | 🔴 |
| #12 AutoGPT 兼容名 | 3 | ✅ 已用 alias | 无 |
| #13 MemGPT 5 层记忆 | 3 | ❌ 冇 5 层体系 | 🔴 |
| #14 OUTPUT IN CHINESE | 4 | ⚠️ 部分 | 🟢 |
| #15 AWEL 3 层 | 6 | ⚠️ Skill 1 层，缺算子/DSL/AgentFrame | 🟡 |
| #16 两阶段检索 | 6 | ❌ 冇 RAG | 🔴 |
| #17 LoRA 微调 | 7 | ❌ 已决定跳过 | — |
| #18 Function-calling 6 步 | 8 | ✅ base.py 有 | 无 |
| #19 ReAct 3 要素 + 自我批评 | 9 | ✅ Critic + retry | 无 |
| #20 Plan-and-Execute 4 阶段 | 10 | ⚠️ 隐式，冇显式 Planner | 🟡 |
| #21 LangGraph StateGraph | 11 | ✅ graph.py 已用 | 无 |
| #22 AutoGen 嵌套对话 | 12 | ⚠️ 2 层（per-agent + cross），缺 meta-review | 🟡 |
| #23 LlamaIndex 4 步索引 | 13 | ❌ 冇 RAG | 🔴 |
| #24 CrewAI 4 组件 | 14 | ✅ Process + Agent + Task + Crew 对齐 | 无 |
| #25 Qwen-VL 流式推理 | 15 | ✅ video_cloner 已用 | 无 |
| #26 CogVLM2 以文搜图 | 16 | ❌ 冇 image embedding | 🔴 |

---

## 三、推荐实施顺序

按"价值 / 成本"比：

### 第一优先（🔴）：RAG + Embeddings

**理由**：
- 价值最高（跨任务 recall + 知识累积）
- 依赖 Qwen proxy 已经支持 /v1/embeddings（基础设施 ready）
- 3-5 天可完成
- 衔接未来 MemGPT / 以文搜图（共享基础设施）

**实施路径**：
1. Day 1-2: 集成 Chroma + embeddings endpoint
2. Day 2-3: 加 src/memory/ 模块（recall + index + store）
3. Day 3-4: pipeline 集成（task 完成 → 自动写入；新 task → 先 recall）
4. Day 4-5: 测试 + 文档

### 第二优先（🔴）：以文搜图

**理由**：
- 衔接 video_cloner（闭环）
- 2-3 天可完成
- 复用 RAG 基础设施（Chroma + embeddings）

**实施路径**：
1. Day 1: image embedding pipeline（CogVLM2 → vector）
2. Day 2: 加 image_recall skill + 新 Agent
3. Day 3: 集成测试

### 第三优先（🟡）：AWEL 3 层 Skill（承接 P2）

**理由**：
- P2 Skill 抽象已经就绪（向后兼容）
- 3-5 天可完成
- 但需要 refactor 现有 7 agent → operators

**实施路径**：
1. Day 1-2: 定义 Operator ABC
2. Day 2-3: 把现有 7 agent 拆解为 operators
3. Day 3-4: 加 DSL parser
4. Day 4-5: AgentFrame composition

### 第四优先（🟡）：Plan-and-Execute 显式化

**理由**：
- 2-3 天
- 改善 UX（更快得到结果）
- 节省 token

**实施路径**：
1. Day 1: Planner node（query rewriting + agent 选择）
2. Day 2: 动态 execution plan
3. Day 3: 测试

### 第五优先（🟢）：OUTPUT IN CHINESE 统一

**理由**：
- 0.5 天
- 最低风险

### 第六优先（🟡）：AutoGen 嵌套加深

**理由**：
- 2-3 天
- 但需要更深入嘅 state management
- 风险较高（可能影响现有 quality）

### 第七优先（🔴）：MemGPT 5 层记忆

**理由**：
- 5-7 天（最大工作量）
- 但价值难以短期量化
- 可以分阶段做（先 2 层，逐步加）

---

## 四、本报告 vs 之前 v1/v2 报告

| 报告 | 假设 | 实际发现 |
|------|------|----------|
| v1 | Smart Agent 冇任何 16 章精华落地 | ❌ 错估（实际 ~50%）|
| v2 | Smart Agent 已应用 ~50% 16 章精华 | ⚠️ 部分准确（缺 RAG/MemGPT/CogVLM2 三大块）|
| **v3（本报告）** | Smart Agent 已应用 ~50% 16 章精华，**剩余 3 大 Gap** | ✅ 准确 |

**v3 关键 insight**：之前嘅「诚实标注」仍然准确，但忽略了 **3 个真正大 Gap**（RAG / MemGPT / CogVLM2），呢啲系 book 入面**重点讲解**嘅主题，遗漏咗系 audit 嘅盲点。

---

## 五、最终建议

按 smart-agent CLAUDE.md 嘅 Low-Hanging Fruit + 最小可信改动原则：

### 推荐下个做（按价值/成本排序）：
1. **RAG / Embeddings**（3-5 天，🔴 价值最高，基础设施 ready）
2. **以文搜图**（2-3 天，🔴 衔接 video_cloner）
3. **OUTPUT IN CHINESE 统一**（0.5 天，🟢 小改动高收益）

### 唔建议即刻做（高成本 / 低 ROI）：
- MemGPT 5 层（5-7 天，价值难量化）
- AWEL 3 层 refactor（3-5 天，破坏性改动）
- AutoGen 嵌套加深（2-3 天，可能影响现有 quality）

---

**报告生成**：2026-07-18 22:05
**生成者**：Claude Code (MiniMax-M3)
**基于**：完整 4 份 mavis 视角分析 + Smart Agent Pro 代码审计 + 本轮已落地模块

下一步：
1. 决定下个 P 嘅范围（建议做 RAG + Embeddings）
2. 预估工作量（3-5 天）
3. 开 P1 RAG 实施
4. 同时做 P5 OUTPUT IN CHINESE（0.5 天，性价比高）