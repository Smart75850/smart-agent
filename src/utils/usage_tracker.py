"""Smart Agent Pro - 使用额度跟踪器。

试用版：50 次搜索额度，用完提示购买永久版。
Pro 激活使用 HMAC-SHA256 签名验证，离线校验无需网络。
"""
import hashlib
import hmac
import json
import os
import time
from base64 import urlsafe_b64encode, urlsafe_b64decode
from pathlib import Path
from datetime import datetime

# 自动加载项目根目录 .env（保证 LICENSE_SECRET / USAGE_FILE 可读，不依赖 import 顺序）
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

USAGE_FILE = os.environ.get("USAGE_FILE", "/app/config/usage.json")

# HMAC 签名密钥 —— 只从环境变量 LICENSE_SECRET 读取，禁止硬编码默认值
# 换密钥后所有旧 key 失效，生成新 key 用 generate_license_key()
# 未设置 LICENSE_SECRET 时，license key 生成/验证全部禁用（已激活的 Pro 不受影响）
_SIGNING_SECRET = os.environ.get("LICENSE_SECRET", "")

DEFAULT_CONFIG = {
    "license": "trial",
    "total_limit": 50,
    "used": 0,
    "first_use": None,
    "last_use": None,
    "wechat": "smart4906",
    "licensed_to": "",
}


def _load() -> dict:
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
    path = Path(USAGE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def check_quota() -> dict:
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


def _sign_hmac(username: str, secret: str | None = None) -> str:
    """对用户名做 HMAC-SHA256 签名，返回 URL-safe base64 字符串。"""
    key = (secret or _SIGNING_SECRET).encode("utf-8")
    sig = hmac.new(key, username.encode("utf-8"), hashlib.sha256).digest()
    return urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")


def generate_license_key(username: str) -> str:
    """生成 license key：base64(username:hmac_signature)。

    在你自己的电脑上运行此函数生成 key，然后发给付费用户。
    示例：
        generate_license_key("zhangsan")
        # → 'emhhbmdzYW46SGVsbG8gV29ybGQ='
    """
    if not _SIGNING_SECRET:
        raise RuntimeError(
            "未设置 LICENSE_SECRET 环境变量，无法生成 license key。"
            "请先在 .env 中配置 LICENSE_SECRET。"
        )
    sig = _sign_hmac(username)
    payload = f"{username}:{sig}"
    return urlsafe_b64encode(payload.encode("utf-8")).rstrip(b"=").decode("ascii")


def verify_license_key(key: str) -> tuple[bool, str]:
    """验证 license key 是否有效。

    Returns:
        (valid: bool, username: str) — 无效时 username 为空字符串。
    """
    if not _SIGNING_SECRET:
        # 未配置签名密钥 → 拒绝一切激活，防止使用公开仓库里的默认密钥伪造
        return False, ""
    if not key or ":" not in key:
        return False, ""

    # 补齐 base64 padding
    padding = 4 - len(key) % 4
    if padding != 4:
        key += "=" * padding

    try:
        decoded = urlsafe_b64decode(key).decode("utf-8")
    except Exception:
        return False, ""

    parts = decoded.split(":", 1)
    if len(parts) != 2:
        return False, ""

    username, provided_sig = parts
    expected_sig = _sign_hmac(username)

    if hmac.compare_digest(provided_sig, expected_sig):
        return True, username
    return False, ""


def activate_pro(key: str) -> bool:
    """激活 Pro 版（HMAC-SHA256 签名验证）。"""
    valid, username = verify_license_key(key)
    if not valid:
        return False

    config = _load()
    config["license"] = "pro"
    config["total_limit"] = 999999
    config["licensed_to"] = username
    _save(config)
    return True


def get_status() -> str:
    config = _load()
    license_type = config.get("license", "trial")
    used = config.get("used", 0)
    total = config.get("total_limit", 50)
    first = config.get("first_use", "未使用")
    last = config.get("last_use", "未使用")
    licensed_to = config.get("licensed_to", "")

    if license_type == "pro":
        who = f"（用户：{licensed_to}）" if licensed_to else ""
        return f"状态：Pro 永久版{who} | 已使用：{used} 次"

    remaining = max(0, total - used)
    return (
        f"状态：试用版 | 已使用：{used}/{total} 次 | 剩余：{remaining} 次\n"
        f"首次使用：{first}\n"
        f"最近使用：{last}\n"
        f"升级联系：微信 smart4906"
    )
