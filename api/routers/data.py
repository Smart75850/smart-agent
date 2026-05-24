import json
from pathlib import Path

from fastapi import APIRouter

from config.settings import settings

router = APIRouter()


@router.get("/api/data/{platform}")
async def get_platform_data(platform: str):
    out_dir = Path(settings.OUTPUT_DIR)
    files = sorted(out_dir.glob(f"{platform}_*.json"))
    latest = files[-1] if files else None
    if not latest:
        return {"data": []}
    with open(latest, encoding="utf-8") as f:
        data = json.load(f)
    return {"data": data}


@router.get("/api/data")
async def list_all_data():
    out_dir = Path(settings.OUTPUT_DIR)
    result = {}
    for fpath in sorted(out_dir.glob("*_*.json")):
        if fpath.name.startswith("result_"):
            continue
        key = fpath.stem
        with open(fpath, encoding="utf-8") as f:
            result[key] = json.load(f)
    return result
