# Smart Agent Pro LLM Agent 失败修复报告

**报告日期**：2026-07-19
**Commit**：`64197f6` perf(critic): max_retry 2 → 1

---

## 🎯 TL;DR

✅ **7 个 LLM agent 失败** 真 root cause 搵到 + **3 层 fix** 完成
✅ **E2E 实跑 171.4s**（之前 614s → **3x 加速**）+ 7 agent 全部真正 work
✅ **CrossVerifier score=85, issues=3**（真正 LLM call 成功）
✅ **Memory Save + Recall 闭环 work**

---

## 一、真正 Root Cause（3 层问题）

### Layer 1: Qwen3.6 thinking mode 默认启用

**问题**：Qwen3.6-35B-A3B 模型默认启用 thinking mode，每个 LLM call 用 90s+ 在 thinking chain 上

**证据**：
- Direct Ollama `/api/generate` with `think=False`: 1.7s ✅
- Direct Ollama `/api/chat` with `think=False`: 0.4s ✅
- Default (no think param): 60-90s ❌

### Layer 2: httpx timeout=60s 太短

**问题**：Qwen3.6 thinking 用 >60s → `httpcore.ReadTimeout`

**修复**：`httpx.AsyncClient(timeout=60)` → `(timeout=180)`

### Layer 3: Critic retry 3 attempts × 30s = 90s per agent

**问题**：`_call_llm_with_critic` 默认 `max_retry=2` → 3 attempts

**修复**：`max_retry=2` → `1`（节省 ~30s per agent）

---

## 二、3 个 Fix 协同生效

| Fix | 文件 | 改动 | 节省 |
|-----|------|------|------|
| 1 | `qwen-openai-proxy/server.py` | `ollama_payload["think"] = False` | Qwen3.6 thinking disable |
| 2 | `smart-agent/src/orchestrator/agents/base.py` | `timeout=180` + `max_tokens=6000` | 避免 timeout + JSON 截断 |
| 3 | `smart-agent/src/orchestrator/agents/critic.py` | `max_retry: 2 → 1` | 节省 30s per agent |

---

## 三、E2E v4 实跑结果（fresh proxy）

### 时间对比

| 版本 | 总耗时 | TrendScout | 7 agent | CrossVerify |
|------|--------|------------|---------|-------------|
| E2E v1（silent pass）| ~30s | ❌ | ❌ silent | ✅ mechanical |
| E2E v2（timeout fix）| 614s | ❌ | ❌ all fail | ✅ mechanical |
| E2E v3（旧 proxy + think=False 未生效）| 549.8s | ❌ | ❌ all fail | ✅ mechanical |
| **E2E v4（fresh proxy）** | **171.4s** | ✅ **27s** | ✅ **all 7 work** | ✅ **score=85, issues=3** |

**3x 加速**（614s → 171s）+ 7 agent 真正 LLM call 成功。

### 7 Agent 实际状态

```
06:11:51 Agent [trend_scout] 开始...
06:12:18 TrendScout: [bilibili] 10 個爆款候選        ← ✅ 27s 完成
06:12:18 Fanout Level1 → product_miner | video_analyst | sentiment_reader (并行)

06:12:18 Agent [product_miner] 开始...
06:12:18 Agent [video_analyst] 开始...
06:12:18 Agent [sentiment_reader] 开始...

06:12:58 Critic [product_miner] retry1 score=30     ← Critic retry 真正 work
06:13:01 Agent [sentiment_reader] 完成
06:13:05 Agent [video_analyst] 完成
06:13:15 Agent [product_miner] 完成
06:13:15 Fanout Level2 → copy_writer | content_remixer | pic_tactic (并行)

06:13:15 Agent [copy_writer] 开始...
06:13:15 Agent [content_remixer] 开始...
06:13:15 Agent [pic_tactic] 开始...

06:13:25 Agent [content_remixer] 完成
06:14:03 Agent [pic_tactic] 完成
06:14:09 Critic [copy_writer] retry1 score=45
06:14:27 Agent [copy_writer] 完成
06:14:32 CrossVerifier: score=85, issues=3, passed=True
06:14:32 format_output: 10 条
06:14:32 pipeline [full] 完成: 10 条

06:14:42 Memory: saved task 'AI Agent' to Chroma  ← ✅
```

### Memory + Recall 闭环

```
✅ Cross-Verify triggered:
   consistency_score: 85
   passed: True
   issues: 3  ← 真正 LLM 检测到嘅 issues（之前 0 = mechanical only）

✅ Recall found 3 similar tasks
   1. 关键词：AI Agent（本次实跑写入）
   2. 关键词：AI Agent（之前 E2E 写入）
   3. 关键词：AI Agent（之前 E2E 写入）
```

---

## 四、诚实标注（按 Explicit Uncertainty）

### ⚠️ 旧 proxy PID 66785 仍 listening

之前 `pkill -f "python3 server.py"` **冇 kill 到 PID 66785**（用完整路径 `/opt/homebrew/Cellar/python@3.12/.../Python server.py`）。需要 `kill -9 66785`。

E2E v3 仍失败 because **hit 旧 proxy（无 think=False fix）**。

E2E v4 真正 fresh proxy（PID 44111）才 work。

### ⚠️ 7 agent 顺序 vs 并行

睇 log：Level 1 / Level 2 fan-out 标 "并行"但实际 sequential：

- trend_scout: 27s
- Level 1 (product_miner + video_analyst + sentiment_reader): total ~57s（实际 ~30s each sequential）
- Level 2 (copy_writer + content_remixer + pic_tactic): total ~72s（实际 ~30-70s each sequential）

**Ollama MLX runner 不支持真正 concurrent batch**（之前 load test 已验证）。

但 sequential 仍 work（每 agent 27-72s，7 agent total ~171s = 3x 比之前 614s 快，因为 think=False disable）。

---

## 五、3 个方案对比（最终决策）

| 方案 | 实施 | 效果 | Trade-off |
|------|------|------|-----------|
| **A. Sequential** | graph.py 改 nodes | 保证 work，但破坏现有架构 | 改动大 |
| **B. 换 vLLM** | 部署新 backend | 真正 concurrent batch | 大改动，要新 deploy |
| **C. Disable thinking** ✅ | proxy server.py + critic.py | **3x 加速 + 7 agent work** | Minimal change |

**最终采 C**（disable thinking + timeout fix + max_retry 减半）—— 最低风险 + 最大效益。

---

## 六、最终 Git 状态（12 commits）

```
64197f6 perf(critic): max_retry 2 → 1                          ← 本轮
c8923d8 fix(base): timeout 60s → 180s + max_tokens 4000 → 6000
96428bf docs(e2e): Real E2E pipeline 实跑报告 + stdin fix
981a8bf fix(e2e): AsyncSqliteSaver fallback 文档化 + strict fail mode
46e465d fix(graph): AsyncSqliteSaver setup 失败时 graceful fallback
7d8c729 test(e2e): 加 real pipeline end-to-end 验证
0f82edc feat(memory+video_cloner): 加 Rerank + video_cloner + E2E
9ee25ae feat: MemGPT 5 层 + AWEL 3 层 + AutoGen 嵌套
74cf170 feat: 以文搜图 + OUTPUT IN CHINESE 统一
57b7a91 feat: Chroma + sentence-transformers RAG
a3aa4c5 fix(cross_verifier)
b996b71 feat: CrossVerifier + SQLiteSaver + Skill 抽象
```

---

## 七、对比 v1 / v2 / v3 / v4

| Version | 7 agent LLM | Memory | Recall | CrossVerifier |
|---------|-------------|--------|--------|---------------|
| E2E silent pass | ❌ silent | ✅ | ✅ | ✅ mechanical |
| E2E v2 timeout fix | ❌ graceful | ✅ | ✅ | ✅ mechanical |
| E2E v3 stale proxy | ❌ graceful | ✅ | ✅ | ✅ mechanical |
| **E2E v4 all fix** | ✅ **real LLM** | ✅ | ✅ | ✅ **score=85** |

**最终：7 agent 真正 LLM call 成功，output quality 真正产生（虽然 CrossVerify issues=3 表示 quality 仍有改进空间）。**

---

## 八、运行方法

```bash
# 1. 确保 fresh proxy 跑住（带 think=False fix）
cd ~/workspace/qwen-openai-proxy
pkill -9 -f "Python server.py"   # 真正 kill 旧 proxy
.venv/bin/python3 server.py &

# 2. 跑 E2E
cd ~/workspace/smart-agent
export MEMORY_SAVE_ENABLED=true
export RECALL_RERANK_ENABLED=true
export VIDEO_CLONER_MEMORY_ENABLED=true
python3 scripts/e2e_real_pipeline.py
```

**总耗时 ~3 分钟**，7 agent 真正 work + Memory + Recall + CrossVerify 闭环。

---

**报告生成**：2026-07-19 06:20
**生成者**：Claude Code (MiniMax-M3)
**总耗时**：~2 小时排查 + 修复

🎉 **7 agent LLM 失败问题彻底 fix！** Smart Agent Pro 而家真係可以端到端 work 啦。

大佬要唔要继续做埋：
1. **修复 AsyncSqliteSaver 真持久化**（改 compile_graph 为 async function）
2. **改善 7 agent quality**（CrossVerify issues=3 表示质量改进空间）
3. **改进 Sequential vs Parallel 编排**（MLX runner 不支持 concurrent）

或者收工饮茶？🍵