from datetime import datetime
from pathlib import Path


class ExcelStore:
    """Excel 儲存後端 — 用 openpyxl 寫 .xlsx 檔案。"""

    def save(self, data: list[dict], output_dir: str, platform: str) -> str:
        from openpyxl import Workbook

        path = Path(output_dir) / f"{platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        path.parent.mkdir(parents=True, exist_ok=True)
        wb = Workbook()
        ws = wb.active
        if data:
            headers = list(data[0].keys())
            ws.append(headers)
            for row in data:
                ws.append([str(row.get(h, "")) for h in headers])
        wb.save(str(path))
        return str(path)
