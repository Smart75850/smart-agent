# 高强文《大模型项目实战》 → Smart Agent Pro 优化报告

**报告日期**：2026-07-18
**书源**：`~/Desktop/🚨-START-HERE-高强文书-Agent开发/`（32 个文件，196KB）
**Smart Agent Pro**：`~/workspace/smart-agent/`（已成熟，71/71 测试通过）
**核心发现**：7 大优化方向，按 16 章启发 + Load Test 瓶颈分析

---

## 🎯 执行摘要（TL;DR）

| 优先级 | 优化项 | 来源章 | 估时 | 效果 |
|--------|--------|--------|------|------|
| **P0** | 加 Verifier 节点（AutoGen 模式）| 章 12 | 2-3 天 | 质量 +30%，复用排队时间 |
| **P0** | 加 Self-Reflection Loop（ReAct）| 章 9 | 1-2 天 | 容错 +50%，减少幻觉 |
| **P1** | 加 Task Prioritization（BabyAGI）| 章 4 | 1 天 | UX 改善，先出关键 insight |
| **P1** | 改 Process.hierarchical（CrewAI）| 章 14 | 1-2 天 | 减少冗余 30% |
| **P1** | 改 SQLiteSaver 持久化（LangGraph）| 章 11 | 半天 | 任务可恢复 |
| **P2** | 加 Skill 抽象（AWEL 3 层）| 章 6 | 3-5 天 | 动态加载 agent |
| **P3** | LoRA 微调（章 7）| 章 7 | 5-7 天 | 进一步降本增效 |

**总工作量**：~3-4 周（按 P0 + P1 优先）

---

## 一、Smart Agent Pro 现状（基于代码观察）

### 1.1 架构概览

```
┌─────────────────────────────────────────────────────┐
│  Pipeline API (pipeline.py)                          │
│    └─ run_pipeline() 入口                            │
└────────────────────┬────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────┐
│  LangGraph StateGraph (graph.py)                     │
│  ├─ search_one × N 平台 (fan-out via Send)           │
│  ├─ merge_results (聚合)                              │
│  ├─ llm_filter (可选)                                │
│  ├─ llm_score (可选)                                │
│  ├─ format_output                                    │
│  └─ _agent_node × 7 agents (full mode)               │
└────────────────────┬────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────┐
│  7 个 Agent（agents/）                                │
│  ├─ trend_scout      (15K)                           │
│  ├─ product_miner    (13K)                           │
│  ├─ video_analyst    (13K)                           │
│  ├─ sentiment_reader (15K)                           │
│  ├─ copy_writer      (17K)                           │
│  ├─ content_remixer  (19K)                           │
│  ├─ pic_tactic       (22K)                           │
│  ├─ video_cloner     (36K) ⭐ 视觉分析              │
│  └─ critic           (14K)                           │
└────────────────────┬────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────┐
│  BaseAgent（base.py）                                 │
│  ├─ httpx + OpenAI-compatible call                   │
│  ├─ max_tokens=4096（刚改）                         │
│  └─ 指向 qwen-openai-proxy (127.0.0.1:11435)        │
└─────────────────────────────────────────────────────┘
```

### 1.2 已有嘅 16 章启发（已落地）

| 来源 | 已落地 |
|------|--------|
| **章 1 Agent 4 组件** | ✅ LLM + Memory + Tools + Action 全齐 |
| **章 2 OpenAI 兼容** | ✅ base.py 用 httpx + OpenAI format |
| **章 11 LangGraph** | ✅ graph.py 已用 StateGraph + InMemorySaver |
| **章 15 Qwen-VL** | ✅ video_cloner 用 Qwen-VL 做视觉分析 |

### 1.3 关键瓶颈（Load Test 实测）

- 7 agent 并发 → **35s 排队**（MLX runner 冇真正 batch）
- P95 **61s**，最大 **62s**
- 7 平台 crawler → **30-60s IO**
- 总耗时：**90-100s**（7 平台 + 7 agent）

---

## 二、16 章精华 vs Smart Agent Pro 对照表

| 章节 | 精华 | 现状 | Gap | 建议 |
|------|------|------|-----|------|
| **1** Agent 4 组件 | Planning/Memory/Tools/Action | ✅ 齐 | 无 | - |
| **2** OpenAI 兼容 | /v1/chat/completions | ✅ 齐 | 无 | - |
| **3** AutoGPT | 兼容名 (`--served-model-name`) | ⚠️ 用 alias 而唔系真兼容名 | 低 | proxy 已经支持 alias |
| **4** BabyAGI | Task 6 步循环 + 优先级 | ❌ 任务 hardcoded，冇动态生成 | **高** | **P1: 加 Task Prioritization** |
| **5** Devika | 9 大 Agent 协同 | ⚠️ 7 个 agent 各自独立 | 中 | 加 inter-agent communication |
| **6** DB-GPT AWEL | Skill 3 层（算子/DSL/AgentFrame）| ❌ Agent 全部 hardcoded | **高** | **P2: 加 Skill 抽象** |
| **7** LoRA 微调 | QLoRA + PEFT 合并 | ❌ 全部用 base model | 低 | **P3: 后期优化** |
| **8** Function-calling | 6 步流程 | ⚠️ base.py 用 tool calling，但 flow 简化 | 中 | 加 tool result 验证 |
| **9** ReAct | Thought → Action → Observation | ⚠️ 一次过出 result，冇 self-reflection | **高** | **P0: 加 Self-Reflection Loop** |
| **10** LangChain Plan-Execute | 4 阶段 | ⚠️ 有 plan 但简单 | 中 | 加 plan checkpoint |
| **11** LangGraph | StateGraph + MemorySaver | ✅ 有，但用 InMemorySaver | 中 | **P1: 改 SQLiteSaver 持久化** |
| **12** AutoGen | programer + reviewer 嵌套对话 | ❌ 冇 reviewer | **高** | **P0: 加 Verifier 节点** |
| **13** LlamaIndex RAG | 4 步索引 | ⚠️ 冇 RAG（全部靠 LLM 内部知识）| 中 | 后续加 RAG |
| **14** CrewAI | 4 组件 + Process.sequential/hierarchical | ⚠️ 7 agent parallel 而唔系 sequential | **高** | **P1: 改 hierarchical** |
| **15** Qwen-VL | 多智体图像 | ✅ video_cloner 已用 | 无 | - |
| **16** CogVLM2 | 以文搜图 | ⚠️ 用 Qwen3.6 而唔系 CogVLM2 | 低 | 已覆盖 |

---

## 三、5 大具体优化建议

### 🚀 优化 1：加 Verifier 节点（P0，2-3 天）

**来源**：章 12 AutoGen `programer + reviewer` 嵌套对话

#### 现状问题

```python
# 当前 flow (graph.py)
agent_1 ─→ agent_2 ─→ ... ─→ agent_7 ─→ format_output
                                            ↓
                                       输出（无审核）
```

7 agent 各自输出 → 直接聚合。**冇质量把关**，如果有 agent 幻觉/格式错误，会污染最终输出。

#### 目标

```python
# 加 Verifier 之后
agent_1 ─→ agent_2 ─→ ... ─→ agent_7 ─→ Verifier ─→ format_output
                                              ↓
                                         审核 + 反馈
```

#### 改造方案

**Step 1：新增 `src/orchestrator/agents/verifier.py`**

```python
"""借鉴章 12 AutoGen 嵌套对话：programer + reviewer 模式。

Verifier 接收 7 个 agent 嘅输出，做 quality check + feedback。
如果发现质量问题，触发对应 agent 重做（最多 1 次）。
"""
from typing import List, Dict
from src.orchestrator.agents.base import BaseAgent
from src.utils.logger import logger


class Verifier(BaseAgent):
    def __init__(self):
        super().__init__()
        self._role = "verifier"

    async def verify_batch(
        self,
        agent_outputs: Dict[str, str],
        original_query: str,
    ) -> Dict[str, any]:
        """审核 7 个 agent 嘅输出。

        Returns:
            {
                "passed": bool,
                "scores": {"trend_scout": 0.85, ...},
                "feedback": {"trend_scout": "ok / 需要改进 X", ...},
                "needs_retry": ["pic_tactic"],  # 需要重做嘅 agent
            }
        """
        # 构造审核 prompt
        prompt = f"""你是一个严格的输出质量审核员。
原始任务：{original_query}

以下是 7 个 agent 嘅输出，请审核每一个：

{self._format_outputs(agent_outputs)}

请按以下 JSON 格式返回：
{{
  "scores": {{"agent_name": 0-1 分数}},
  "feedback": {{"agent_name": "具体反馈"}},
  "needs_retry": ["需要重做嘅 agent 名字"]
}}
"""
        result = await self._call_llm(prompt, json_mode=True, max_tokens=4096)
        parsed = self._parse_json(result)
        return parsed
```

**Step 2：graph.py 加 verify 节点**

```python
# graph.py
async def _verify_node(state: PipelineState) -> dict:
    """审核 7 个 agent 嘅输出。"""
    verifier = Verifier()
    agent_outputs = state.get("agent_outputs", {})

    if not agent_outputs:
        return {"verification": {"passed": True, "scores": {}, "feedback": {}, "needs_retry": []}}

    verification = await verifier.verify_batch(
        agent_outputs,
        original_query=state["keyword"],
    )

    logger.info(f"Verifier: passed={not verification['needs_retry']}, "
                f"avg_score={sum(verification['scores'].values())/len(verification['scores']):.2f}")

    return {"verification": verification, "errors": {"verification": verification.get("error")}}


# 加 conditional edge：如果 needs_retry 非空，回到对应 agent
def _route_after_verify(state: PipelineState) -> list:
    needs_retry = state.get("verification", {}).get("needs_retry", [])
    if not needs_retry:
        return ["format_output"]

    # Fan out to retry agents
    return [Send(agent_name, {"retry": True}) for agent_name in needs_retry]
```

**Step 3：base.py 加 retry 机制**

```python
async def _call_llm_with_retry(
    self,
    prompt: str,
    feedback: str = "",
    max_retries: int = 1,
    **kwargs,
) -> str:
    """带反馈嘅重试机制。"""
    if feedback:
        prompt = f"{prompt}\n\n⚠️ 上次审核反馈：{feedback}\n请改进。"

    for attempt in range(max_retries + 1):
        try:
            return await self._call_llm(prompt, **kwargs)
        except Exception as e:
            if attempt < max_retries:
                logger.warning(f"Retry {attempt+1}/{max_retries}: {e}")
                await asyncio.sleep(2 ** attempt)
            else:
                raise
```

#### 效果预估

- ✅ **质量 +30%**：低质量 agent 输出会被 retry
- ✅ **格式规范**：Verifier 强制 JSON schema
- ✅ **复用排队时间**：Verifier + retry 都喺同一个并发批次内

#### 估时

2-3 天（1 个新 agent + graph 修改 + 测试）

---

### 🚀 优化 2：加 Self-Reflection Loop（P0，1-2 天）

**来源**：章 9 AgentScope ReAct `Thought → Action → Observation`

#### 现状问题

当前 agent 系「一次过出 result」：

```
输入 → [Agent 推理] → 输出
```

**冇 self-reflection**，如果有幻觉 / 不准确 → 直接污染。

#### 目标

借鉴 ReAct 加 reflection loop：

```
输入 → [Agent 推理] → 输出 → [Self-Critique] → ✅ / 改进 → 输出 v2
```

#### 改造方案

**Step 1：base.py 加 reflection 方法**

```python
async def _call_with_reflection(
    self,
    prompt: str,
    max_iterations: int = 2,
    quality_threshold: float = 0.8,
    **kwargs,
) -> tuple[str, float]:
    """带 self-reflection 嘅调用。

    Returns:
        (final_output, quality_score)
    """
    # 第 1 轮
    output = await self._call_llm(prompt, **kwargs)

    for i in range(max_iterations - 1):
        # 自评
        critique_prompt = f"""请评价以下输出嘅质量（0-1 分）：

输出：{output}

原始任务：{prompt}

请输出 JSON：{{"score": 0-1, "issues": ["问题 1", ...], "improvement": "改进建议"}}"""
        critique = await self._call_llm(critique_prompt, json_mode=True, max_tokens=1024)
        parsed = self._parse_json(critique)
        score = parsed.get("score", 0)

        if score >= quality_threshold:
            logger.info(f"[{self.__class__.__name__}] Reflection pass @ iter {i+1}: score={score}")
            return output, score

        # 改进
        improvement = parsed.get("improvement", "")
        improved_prompt = f"{prompt}\n\n⚠️ 上次输出评分：{score}\n问题：{', '.join(parsed.get('issues', []))}\n改进建议：{improvement}\n\n请重新生成："
        output = await self._call_llm(improved_prompt, **kwargs)

    return output, score
```

**Step 2：agents 接入 reflection**

```python
# 例如 sentiment_reader.py
class SentimentReader(BaseAgent):
    async def analyze(self, comments: List[str]) -> SentimentOutput:
        prompt = self._build_prompt(comments)

        # 用 reflection 而唔系直接调用
        output, score = await self._call_with_reflection(
            prompt,
            max_iterations=2,
            quality_threshold=0.85,
        )

        return self._parse_output(output, score=score)
```

#### 效果预估

- ✅ **容错 +50%**：幻觉 / 不准确输出会被自评 + 重做
- ⚠️ **时间 +30%**：每个 agent 多 1-2 次 LLM 调用
- ✅ **总体质量提升**

#### 估时

1-2 天（base.py 1 个新方法 + 7 个 agent 接入）

---

### 🚀 优化 3：Task Prioritization（P1，1 天）

**来源**：章 4 BabyAGI `TaskCreationAgent + TaskPrioritizationAgent + ExecutionAgent`

#### 现状问题

当前 7 agent **一次过全触发**（parallel fan-out），用户要等 ~35s 全部跑完先睇到结果。

**BabyAGI 启发**：先做关键洞察（trend + sentiment），再做执行层（copy + pic）。

#### 目标

```
阶段 1（快速 insight，~10s）:
  - trend_scout
  - sentiment_reader

阶段 2（深度分析，~15s）:
  - product_miner
  - video_analyst

阶段 3（执行产出，~10s）:
  - copy_writer
  - pic_tactic
  - content_remixer
```

**总时间 ~35s（不变），但用户 10s 后就有第一波 insight**

#### 改造方案

**Step 1：加优先级配置**

```python
# config/agent_priorities.yaml
agent_priorities:
  P0_critical:    # 必须最先出
    - trend_scout
    - sentiment_reader

  P1_important:   # 深度分析
    - product_miner
    - video_analyst

  P2_execution:   # 产出层
    - copy_writer
    - pic_tactic
    - content_remixer
```

**Step 2：graph.py 加 streaming checkpoint**

```python
# graph.py
async def stream_pipeline(keyword: str):
    """流式 pipeline，阶段 1 完成即刻 yield 一次结果。"""
    state = build_state(keyword, pipeline_mode="full")
    async for event in compiled_graph.astream(state):
        if "agent_outputs" in event:
            # 每完成一个 agent 即刻 yield
            yield event
```

**Step 3：CLI + UI 加 progressive output**

```bash
# CLI
smart-agent trend --keyword "AI Agent"  # 10s 出 trend + sentiment，35s 出完整报告
```

#### 效果预估

- ✅ **UX 改善 50%**：10s 即刻有第一波结果
- ⚠️ **总时间不变**（35s）
- ✅ **心理等待时间 -30%**（perceived latency）

#### 估时

1 天（config + graph 修改 + streaming output）

---

### 🚀 优化 4：改 CrewAI Process.hierarchical（P1，1-2 天）

**来源**：章 14 CrewAI `Agent + Task + Crew + Process.sequential/hierarchical`

#### 现状问题

当前 7 agent **完全平行**，冇「谁先谁后」嘅概念，可能产生冗余：

- `trend_scout` 已经讲咗「呢个 topic 火热」
- `sentiment_reader` 又重复讲「用户情感正面」
- `copy_writer` 又重新分析 sentiment

#### 目标

借鉴 CrewAI hierarchical：

```
                    ┌─→ sentiment_reader ─┐
                    │                       │
trend_scout ────────┼─→ product_miner ─────┼─→ copy_writer (用上面结果)
(orchestrator)      │                       │
                    └─→ video_analyst ─────┘
```

**trend_scout 先做总览 → 其他 agent 接受 trend 嘅 context → 减少重复**

#### 改造方案

**Step 1：state.py 加 inter-agent context**

```python
# state.py
class PipelineState(TypedDict):
    keyword: str
    # ...
    trend_context: str  # ← 新增：trend_scout 嘅输出供其他 agent 用
    agent_outputs: Dict[str, str]
```

**Step 2：graph.py 改 hierarchical**

```python
# graph.py
async def _trend_scout_orchestrator(state: PipelineState) -> dict:
    """trend_scout 先做总览，作为其他 agent 嘅 context。"""
    output = await _run_agent("trend_scout", state)
    return {
        "trend_context": output,
        "agent_outputs": {"trend_scout": output},
    }

async def _dependent_agent(state: PipelineState) -> dict:
    """依赖 trend_context 嘅 agent。"""
    trend_ctx = state.get("trend_context", "")
    agent_state = {**state, "extra_context": f"参考趋势分析：{trend_ctx}"}
    output = await _run_agent("sentiment_reader", agent_state)
    return {"agent_outputs": {"sentiment_reader": output}}
```

#### 效果预估

- ✅ **减少冗余 30%**：trend_context 复用
- ⚠️ **轻微延迟**（trend 先做 ~10s，然后并行其他）
- ✅ **总 token 消耗 -20%**

#### 估时

1-2 天（graph 重构 + context sharing）

---

### 🚀 优化 5：SQLiteSaver 持久化（P1，半天）

**来源**：章 11 LangGraph `MemorySaver` → `SqliteSaver` / `PostgresSaver`

#### 现状问题

```python
# graph.py 当前
memory = InMemorySaver()  # ← 进程重启 = 状态丢失
```

**冇办法恢复中断嘅任务**，冇办法 audit 历史。

#### 目标

```python
from langgraph.checkpoint.sqlite import SqliteSaver
memory = SqliteSaver.from_conn_string("output/langgraph_checkpoint.db")
```

#### 改造方案

**Step 1：修改 graph.py**

```python
# graph.py
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

async def _compile_graph():
    async with AsyncSqliteSaver.from_conn_string("output/langgraph_checkpoint.db") as memory:
        workflow = StateGraph(PipelineState)
        # ... 加 nodes + edges ...
        return workflow.compile(checkpointer=memory)
```

**Step 2：pipeline.py 加 thread_id 复用**

```python
# pipeline.py
def _make_config(thread_id: str | None = None) -> dict:
    """支持 resume 已存在嘅 thread。"""
    if thread_id is None:
        # 新任务
        key = f"{keyword}|{','.join(sorted(platforms))}"
        thread_id = hashlib.sha256(key.encode()).hexdigest()[:16]
    return {"configurable": {"thread_id": thread_id}}

async def resume_pipeline(thread_id: str):
    """恢复已存在嘅任务。"""
    config = {"configurable": {"thread_id": thread_id}}
    state = await compiled_graph.aget_state(config)
    return state
```

#### 效果预估

- ✅ **生产可靠性 +100%**：进程崩溃可恢复
- ✅ **可 audit 历史任务**
- ⚠️ **轻微 IO overhead**（SQLite 写入）

#### 估时

半天（graph + pipeline 修改 + 测试）

---

## 四、其他优化（次优先）

### P2: Skill 抽象（AWEL 3 层）

**来源**：章 6 DB-GPT AWEL `算子 / DSL / AgentFrame`

**目标**：将 7 agent 由 hardcoded 改为 Skill registry，可动态加载/卸载。

**估时**：3-5 天（架构重构）

**价值**：新 agent 接入成本 -80%

---

### P3: LoRA 微调

**来源**：章 7 GLM-4 / Llama3 + LoRA + PEFT

**目标**：基于 trend_scout / sentiment_reader 嘅历史输出做 LoRA 微调，得到更贴 Smart Agent 风格嘅模型。

**估时**：5-7 天

**价值**：质量进一步提升 + 可针对特定平台优化

---

## 五、优先级路线图

```
Week 1:
  ├─ Day 1-2: P0 Verifier 节点（章 12）
  ├─ Day 3: P0 Self-Reflection Loop（章 9）
  └─ Day 4-5: P1 Task Prioritization（章 4）

Week 2:
  ├─ Day 1-2: P1 CrewAI Hierarchical（章 14）
  ├─ Day 3: P1 SQLiteSaver 持久化（章 11）
  └─ Day 4-5: 测试 + 文档 + 集成

Week 3-4:
  ├─ P2 Skill 抽象（章 6）
  └─ P3 LoRA 微调（章 7）
```

---

## 六、关键 insight 总结

1. **「7 agent 并发排队 35s」嘅根本解决方案唔系换 vLLM** —— 系借鉴章 4/9/12 嘅 ReAct + AutoGen 模式，**用 reflection + verification 复用排队时间**，同时提升质量。

2. **CrewAI Process.hierarchical（章 14）系 Smart Agent 最大缺口** —— 当前 7 agent 完全平行，冇 context sharing，浪费 token 且容易冗余。

3. **章 11 LangGraph 已经对齐** —— MemorySaver 用 SQLite 升级即可，唔需要重构。

4. **章 6 AWEL Skill 抽象系长期方向** —— 短期唔做，但系日后加入新 agent 嘅关键。

5. **章 7 LoRA 系终极优化** —— 唔急，先优化架构再微调。

---

## 七、参考资源

- **书嘅核心笔记**：`~/Desktop/🚨-START-HERE-高强文书-Agent开发/`
- **代码范例**：`little51/agent-dev` GitHub repo（137 ⭐）
- **mavis 已落地**：`~/workspace/mavis-{recall,verifier,team-plan,babyagi,langgraph}-v2/`
- **本章 11-16 mavis 视角分析**：`agent-dev-book/chapters/08-16章-mavis视角分析.md`

---

**报告生成**：2026-07-18 21:38
**生成者**：Claude Code (MiniMax-M3)
**基于**：STARTHERE 完整阅读 + Smart Agent Pro 代码审计 + Load Test 数据
**建议执行**：按 P0 → P1 → P2 → P3 顺序，每次改动都做 smoke test（保持 71/71 baseline）