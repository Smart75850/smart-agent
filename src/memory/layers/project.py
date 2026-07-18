"""MemGPT Project Layer — 同 keyword 累积分析（多次跑同一 topic 嘅聚合）。

源：高强文《大模型项目实战》第 3 章 MemGPT 嘅 core_memory + project 级累积。

设计：
- 按 keyword（同 topic）累积多次 pipeline run 嘅结果
- 提供 project 级摘要 + trend analysis
- 用 Chroma store 嘅 metadata 过滤 + 聚合

用法：
  layer = ProjectLayer()
  layer.write_run(keyword="AI Agent", summary="...", run_id="...")
  summary = layer.get_project_summary(keyword="AI Agent")  # 聚合所有历史 run
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional

from src.memory.store import MemoryStore
from src.memory.recall import recall_similar_tasks


_PROJECT_COLLECTION = "smart_agent_projects"


class ProjectLayer:
    """项目层（同 keyword 累积）。

    设计：
    - 用独立 collection（smart_agent_projects）
    - 每次 pipeline run 写入一条 project entry
    - Recall 返该项目所有历史 run
    - get_project_summary() 聚合 summary
    """

    def __init__(self, store: Optional[MemoryStore] = None):
        self._store = store or MemoryStore(collection_name=_PROJECT_COLLECTION)

    def write_run(
        self,
        keyword: str,
        run_id: str,
        summary: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """记录一次 pipeline run 到 project layer。

        Args:
            keyword: topic / 项目关键词
            run_id: pipeline run ID（thread_id）
            summary: 呢次 run 嘅摘要
            metadata: 附加 metadata

        Returns:
            doc_id
        """
        import hashlib

        doc_id = hashlib.sha256(f"{keyword}|{run_id}".encode()).hexdigest()[:16]
        text = f"Project: {keyword}\nRun: {run_id}\n\n{summary}"

        # 编码 + 写入（用 store.collection 直接，避免 save_task_result 嘅 keyword 前缀）
        from src.memory.embeddings import encode_texts

        embedding = encode_texts([text])[0]

        full_metadata = {
            "keyword": keyword,
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            **(metadata or {}),
        }

        self._store.collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[full_metadata],
        )
        return doc_id

    def list_runs(self, keyword: str, top_k: int = 50) -> list[dict]:
        """列出同 keyword 嘅所有历史 run。"""
        if self._store.count() == 0:
            return []

        results = recall_similar_tasks(keyword, top_k=top_k, store=self._store)
        return results

    def get_project_summary(self, keyword: str) -> dict:
        """聚合项目摘要。

        Returns:
            {
              "keyword": "AI Agent",
              "run_count": 5,
              "first_run": "2026-07-10T...",
              "latest_run": "2026-07-18T...",
              "summaries": ["run1 summary", "run2 summary", ...]
            }
        """
        runs = self.list_runs(keyword, top_k=100)
        if not runs:
            return {
                "keyword": keyword,
                "run_count": 0,
                "summaries": [],
            }

        # 提取时间戳
        timestamps = [
            r["metadata"].get("timestamp")
            for r in runs
            if r["metadata"].get("timestamp")
        ]
        timestamps.sort()

        return {
            "keyword": keyword,
            "run_count": len(runs),
            "first_run": timestamps[0] if timestamps else None,
            "latest_run": timestamps[-1] if timestamps else None,
            "summaries": [r["text"] for r in runs],
        }