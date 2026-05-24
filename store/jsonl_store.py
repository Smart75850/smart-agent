import json
from datetime import datetime
from pathlib import Path


class JSONLStore:
    """JSONL 儲存後端 — 每行一個 JSON object，適合大數據逐條追加。"""

    def save(self, data: list[dict], output_dir: str, platform: str) -> str:
        path = Path(output_dir) / f"{platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for row in data:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return str(path)
