"""Smart Agent Pro - 使用额度跟踪器。

试用版：50 次搜索额度，用完提示购买永久版。
"""
import json
import os
import time
from pathlib import Path
from datetime import datetime

USAGE_FILE = os.environ.get("USAGE_FILE", "/app/config/usage.json")

DEFAULT_CONFIG = {
    "license": "trial",          # trial / pro
    "total_limit": 50,           # trial 限 50 次，pro 限 999999
    "used": 0,
    "first_use": None,
    "last_use": None,
    "wechat": "smart4906",
}


def _load() -> dict:
    """加载使用记录。"""
    path = Path(USAGE_FILE)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        config = DEFAULT_CONFIG.copy()
        _save(config)
        return config
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return DEFAULT_CONFIG.copy()


def _save(config: dict):
    """保存使用记录。"""
    path = Path(USAGE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def check_quota() -> dict:
    """检查剩余额度。

    Returns:
        {
            "allowed": bool,       # 是否允许使用
            "remaining": int,      # 剩余次数
            "total": int,          # 总额度
            "license": str,        # trial / pro
            "message": str         # 提示信息
        }
    """
    config = _load()
    license_type = config.get("license", "trial")
    total = config.get("total_limit", 50)
    used = config.get("used", 0)
    remaining = max(0, total - used)

    if license_type == "pro":
        return {
            "allowed": True,
            "remaining": 999999,
            "total": 999999,
            "license": "pro",
            "message": "Pro 版 - 无限制使用"
        }

    if remaining > 0:
        return {
            "allowed": True,
            "remaining": remaining,
            "total": total,
            "license": "trial",
            "message": f"试用版：剩余 {remaining}/{total} 次"
        }
    else:
        return {
            "allowed": False,
            "remaining": 0,
            "total": total,
            "license": "trial",
            "message": (
                f"\n{'='*50}\n"
                f"试用额度已用完（{total}次）\n"
                f"\n"
                f"如需继续使用，请购买永久版：\n"
                f"微信：smart4906（备注：Pro 版本）\n"
                f"价格：¥499（永久无限次使用）\n"
                f"{'='*50}"
            )
        }


def consume_one() -> dict:
    """消耗一次额度，返回检查结果。"""
    config = _load()
    license_type = config.get("license", "trial")

    if license_type == "pro":
        return {"allowed": True, "remaining": 999999, "license": "pro"}

    used = config.get("used", 0)
    total = config.get("total_limit", 50)

    if used >= total:
        return check_quota()

    config["used"] = used + 1
    if config.get("first_use") is None:
        config["first_use"] = datetime.now().isoformat()
    config["last_use"] = datetime.now().isoformat()
    _save(config)

    remaining = total - config["used"]
    return {
        "allowed": True,
        "remaining": remaining,
        "total": total,
        "license": "trial",
        "message": f"试用版：剩余 {remaining}/{total} 次"
    }


def activate_pro(key: str) -> bool:
    """激活 Pro 版（简单验证）。"""
    if key and len(key) >= 6:
        config = _load()
        config["license"] = "pro"
        config["total_limit"] = 999999
        _save(config)
        return True
    return False


def get_status() -> str:
    """获取当前状态摘要。"""
    config = _load()
    license_type = config.get("license", "trial")
    used = config.get("used", 0)
    total = config.get("total_limit", 50)
    first = config.get("first_use", "未使用")
    last = config.get("last_use", "未使用")

    if license_type == "pro":
        return f"状态：Pro 永久版 | 已使用：{used} 次"

    remaining = max(0, total - used)
    return (
        f"状态：试用版 | 已使用：{used}/{total} 次 | 剩余：{remaining} 次\n"
        f"首次使用：{first}\n"
        f"最近使用：{last}\n"
        f"升级联系：微信 smart4906"
    )
