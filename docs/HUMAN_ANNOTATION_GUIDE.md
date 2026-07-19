# Human Annotation 流程指南 — 给 domain expert 用

> **诚实标注**（按 CLAUDE.md「Explicit Uncertainty」原则）：
> AI 模拟 annotator ≠ 真正人类 annotator。呢份指南提供真正 human annotation 嘅标准化流程，但**真正 user-facing RAG quality measure 需要 domain expert + 多人验证**。

---

## 一、点解需要真正 human annotation

| AI 模拟 | 真正 human |
|---------|------------|
| Rule-based（substring match）| Semantic understanding |
| 5/12 intersection 覆盖率 | 9-11/12 intersection 覆盖率 |
| Cohen's kappa 0.629 | Fleiss kappa ≥ 0.6（标准）|
| Deterministic | Context-aware（业务理解）|
| Free | Domain expert 时间成本 |

**真正 RAG quality measure 需要 human annotation**（AI 模拟只系 internal consistency check）。

---

## 二、流程总览

```
1. 选 10-20 query
      ↓
2. 准备 stored memory pool
      ↓
3. 招募 2-3 annotator（domain expert）
      ↓
4. 双盲标注（annotator 唔知对方身份）
      ↓
5. 计算 Fleiss kappa
      ↓
6. Adjudicate disagreements
      ↓
7. 输出真正 ground truth
      ↓
8. 重跑 RAG metrics（P@K, R@K, MRR）
```

---

## 三、Step 1: 选 10-20 query

### Query 来源
- **真实 user query**（从产品 log 提取）
- **典型场景**（业务常见 80% case）
- **边缘 case**（覆盖 5-10% difficult case）

### 选 query 原则
- ✅ 5-7 个 high-frequency query
- ✅ 2-3 个 long-tail query
- ✅ 2-3 个 ambiguity query（测试 semantic 能力）
- ❌ 唔好全部 keyword overlap（测试唔到 semantic）

### 示例
```yaml
# 高频
- "AI Agent"          # generic
- "美妆视频"          # specific domain

# 长尾
- "Python 教程"        # specific
- "AI Agent 2026"      # temporal

# 歧义
- "AI 创业"           # abstract → expected: AI Agent 应用
- "短视频运营"         # abstract → expected: 美妆视频
```

---

## 四、Step 2: 准备 Stored Memory Pool

### 来源
- 跑几次真实 pipeline 累积 18-50 个 stored memory entry
- 每个 entry 有 unique keyword（例如：「AI Agent」/「Python 教程」/「美妆视频」）
- 排除 test entry（避免 noise）

### Quality 要求
- 至少 5 个 unique keyword
- 覆盖多种 semantic 关系（同义 / 上位 / 下位 / 相关）
- 真实场景（唔好 artificially 制造 noise）

---

## 五、Step 3: 招募 2-3 Annotator

### Annotator 要求
- **Domain expert**（熟悉 RAG 应用嘅业务领域）
- **独立判断**（唔好睇其他人嘅标注）
- **充足时间**（5-10 query 约 30 分钟）
- **3 人更佳**（Fleiss kappa vs Cohen's kappa 适用）

### 标注前 brief
- 提供 query list
- 提供 stored memory pool（含 keyword 列表 + description）
- 标注规则：每个 query 标「哪些 stored memory 算 relevant」
- 唔好 communicate（避免 anchoring bias）

---

## 六、Step 4: 双盲标注 Template

### Excel / CSV Template

| Query | annotator_1_relevant | annotator_2_relevant | annotator_3_relevant | 备注 |
|-------|---------------------|---------------------|---------------------|------|
| AI Agent | AI Agent, AI Agent 2026 | AI Agent | AI Agent, AI Agent 2026 | semantic match |
| AI 工具 | AI 工具实战 | AI 工具实战 | AI 工具实战, AI Agent 2026 | loose match |
| ... | ... | ... | ... | ... |

### JSON Template

```json
{
  "annotator_1": {
    "AI Agent": ["AI Agent", "AI Agent 2026"],
    "AI 工具": ["AI 工具实战"],
    "美妆视频": ["美妆视频"]
  },
  "annotator_2": {
    "AI Agent": ["AI Agent"],
    "AI 工具": ["AI 工具实战"],
    "美妆视频": ["美妆视频"]
  },
  "annotator_3": {
    "AI Agent": ["AI Agent", "AI Agent 2026"],
    "AI 工具": ["AI 工具实战", "AI Agent 2026"],
    "美妆视频": ["美妆视频"]
  }
}
```

---

## 七、Step 5: 计算 Fleiss Kappa

### Cohen's kappa（2 annotators）

```python
def cohens_kappa(a_yes: Set[str], b_yes: Set[str], all_items: Set[str]) -> float:
    """计算 2-annotator agreement。"""
    a_no = all_items - a_yes
    b_no = all_items - b_yes

    n11 = len(a_yes & b_yes)  # both relevant
    n10 = len(a_yes & b_no)   # only A
    n01 = len(a_no & b_yes)   # only B
    n00 = len(a_no & b_no)   # both not

    n = len(all_items)
    p_o = (n11 + n00) / n

    p_a_yes = (n11 + n10) / n
    p_b_yes = (n11 + n01) / n
    p_e = p_a_yes * p_b_yes + (1 - p_a_yes) * (1 - p_b_yes)

    return (p_o - p_e) / (1 - p_e) if p_e != 1 else 1.0
```

### Fleiss kappa（3+ annotators）

**适用于多个 annotator 同時标注多个 query 嘅 generalisation**：

```python
def fleiss_kappa(annotations: List[List[int]], n_categories: int) -> float:
    """
    annotations: List of N queries, 每个 inner list 系 M annotator 嘅 0/1 label
    n_categories: 类别数 (binary = 2)
    """
    N = len(annotations)  # number of queries
    M = len(annotations[0])  # number of annotators (per query)
    k = n_categories  # 2 (binary: relevant / not relevant)

    # p_j: proportion of "relevant" labels for query j
    p_j = [sum(labels) / M for labels in annotations]

    # P_i_bar: mean agreement for query i
    P_i_bar = [
        (sum(labels)**2 - M) / (M * (M - 1)) if M > 1 else 0
        for labels in annotations
    ]

    # P_bar: mean of P_i_bar
    P_bar = sum(P_i_bar) / N

    # P_e_bar: expected agreement by chance
    p_bar = sum(p_j) / N
    P_e_bar = p_bar ** 2 + (1 - p_bar) ** 2

    return (P_bar - P_e_bar) / (1 - P_e_bar) if P_e_bar != 1 else 1.0
```

### Interpretation (Landis & Koch 1977)

| Kappa | Interpretation |
|-------|----------------|
| < 0 | Poor agreement |
| 0.0 - 0.2 | Slight agreement |
| 0.2 - 0.4 | Fair agreement |
| 0.4 - 0.6 | Moderate agreement |
| 0.6 - 0.8 | Substantial agreement |
| 0.8 - 1.0 | Almost perfect agreement |

**目标**：Fleiss kappa ≥ 0.6（Substantial agreement）

---

## 八、Step 6: Adjudicate Disagreements

### 3 种 Adjudication Modes

| Mode | Strategy | Use Case |
|------|----------|----------|
| **Conservative** | Intersection (A ∩ B) | High precision, low recall |
| **Aggressive** | Union (A ∪ B) | Low precision, high recall |
| **Balanced** | Intersection + 边界 fuzzy match | Default |

**推荐**：Conservative mode + Fleiss kappa ≥ 0.6（避免 disagreement 太多）。

### Adjudication 模板

```python
def adjudicate(annotators: List[Set[str]], mode: str = "conservative") -> Set[str]:
    if mode == "conservative":
        # 全部 annotator 同意 → 真正 relevant
        result = annotators[0]
        for ann in annotators[1:]:
            result = result & ann
        return result
    elif mode == "aggressive":
        # 任何一个 annotator 同意 → 可能 relevant
        result = annotators[0]
        for ann in annotators[1:]:
            result = result | ann
        return result
    else:  # balanced
        # Majority vote + edge cases
        return ...  # custom logic
```

---

## 九、Step 7: 输出真正 Ground Truth

### Format

```json
{
  "_meta": {
    "annotators": ["expert_1", "expert_2", "expert_3"],
    "adjudicate_mode": "conservative",
    "fleiss_kappa": 0.65,
    "stored_memory_pool": ["AI Agent", "AI 工具实战", "AI Agent 2026", "美妆视频", "Python 教程"],
    "limitations": ["3 annotator 有限", "业务理解可能有 bias"]
  },
  "ground_truth": {
    "AI Agent": ["AI Agent", "AI Agent 2026"],
    "AI 工具": ["AI 工具实战"],
    "美妆视频": ["美妆视频"],
    "Python 教程": ["Python 教程"]
  }
}
```

### 储存位置

```bash
mkdir -p data/human_annotations
cp human_annotation_results_2026-07-19.json data/human_annotations/
```

---

## 十、Step 8: 重跑 RAG Metrics

```python
# scripts/evaluate_rag_with_human_gt.py
from src.memory.recall import recall_similar_tasks
from src.memory.store import MemoryStore

# Load truly human-annotated GT
with open("data/human_annotations/human_annotation_results_2026-07-19.json") as f:
    gt = json.load(f)

# Calculate metrics (P@K, R@K, MRR)
for query, relevant_kws in gt["ground_truth"].items():
    results = recall_similar_tasks(query, top_k=5, rerank=True)
    # ... compute P@K, R@K, MRR
```

### Quality Target

| Metric | Target | Current (AI mock) |
|--------|--------|---------------------|
| P@1 | ≥ 0.8 | 0.42 (fake GT) / 待 verify (human GT) |
| MRR | ≥ 0.8 | 0.42 (fake GT) / 待 verify |
| Fleiss kappa | ≥ 0.6 | 0.629 (AI mock) / 待 verify (human) |

---

## 十一、Annotator 招募 Checklist

| 维度 | 要求 |
|------|------|
| **领域知识** | 熟悉 RAG 应用嘅业务领域 ≥ 1 年 |
| **独立判断** | 唔好睇其他人标注 |
| **充足时间** | 30-60 分钟（10-20 query）|
| **沟通** | 标注前有 brief（不暴露其他人标注）|
| **质量控制** | 完成 1-2 个 sample query 嘅 calibration |

### 招募途径
- **公司内部**：domain expert（产品 / 运营 / 客服）
- **外包**：Upwork / Fiverr（标注 per query 收费）
- **学术合作**：research lab 标注 student

---

## 十二、诚实标注：已知 Limitation

按 CLAUDE.md「Explicit Uncertainty」原则：

- **真正 human annotation 成本高**（$1-5/query × 3 annotator × 20 query = $60-300）
- **Inter-annotator agreement 难达 0.6**（尤其 abstract query）
- **Domain bias 难避免**（不同 expert 理解可能冲突）
- **时间衰减**（标注标准可能随业务变化）

### 何时用真正 human annotation
- ✅ Production RAG quality measure
- ✅ Marketing / PR 报告
- ✅ Regulatory compliance
- ❌ 内部 consistency check（AI 模拟足够）
- ❌ 早期 prototype

---

## 十三、参考资源

- **Cohen's kappa (1960)**: 原始 paper
- **Fleiss kappa (1971)**: Multi-rater extension
- **Landis & Koch (1977)**: Interpretation guidelines
- **Labelbox / Scale AI**: 商业标注平台
- **Snorkel (Stanford)**: Weak supervision 框架
- **Prodigy**: NLP 标注工具
- **Doccano**: 开源标注平台

---

**按 smart-agent CLAUDE.md「Explicit Uncertainty」原则 + 「唔过设计」**：
- 真正 human annotation 需要 domain expert + 多人 + 时间
- 当前 AI 模拟 dual_annotate 适合 internal consistency 验证
- 真正 user-facing RAG quality measure 仍需真正 human annotation 流程
