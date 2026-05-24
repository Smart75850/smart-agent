"""CSV 儲存後端"""
import csv
from pathlib import Path
from datetime import datetime


class CSVStore:
    """將數據儲存為 CSV 檔案（Excel 友好）"""

    def save(self, data: list[dict], output_dir: str, platform: str) -> str:
        if not data:
            return ""
        path = Path(output_dir) / f"{platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        return str(path)
