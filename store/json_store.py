"""JSON 儲存後端"""
import json
from pathlib import Path
from datetime import datetime
from typing import Any


class JSONStore:
    """將數據儲存為 JSON 檔案"""

    def save(self, data: list[dict], output_dir: str, platform: str) -> str:
        path = Path(output_dir) / f"{platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return str(path)
