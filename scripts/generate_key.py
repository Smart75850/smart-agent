"""Smart Agent Pro - License Key 生成工具。

仅供你自己使用，不要把这个脚本发布出去。
运行方式：
    python generate_key.py 用户名
    python generate_key.py zhangsan
    python generate_key.py --batch users.txt
"""
import hashlib
import hmac
import os
import sys
from base64 import urlsafe_b64encode
from pathlib import Path

# 自动加载项目根目录 .env（与 config/settings.py 保持一致）
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# 必须跟 src/utils/usage_tracker.py 的 _SIGNING_SECRET 一致 —— 只从环境变量读取
_SIGNING_SECRET = os.environ.get("LICENSE_SECRET", "")


def generate_license_key(username: str) -> str:
    if not _SIGNING_SECRET:
        print("错误：未设置 LICENSE_SECRET 环境变量，无法生成 license key。", file=sys.stderr)
        print("请先在项目 .env 中配置 LICENSE_SECRET（可用如下命令生成随机密钥）：", file=sys.stderr)
        print("  python -c \"import secrets; print(secrets.token_hex(32))\"", file=sys.stderr)
        sys.exit(1)
    sig = hmac.new(
        _SIGNING_SECRET.encode("utf-8"),
        username.encode("utf-8"),
        hashlib.sha256
    ).digest()
    sig_b64 = urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    payload = f"{username}:{sig_b64}"
    return urlsafe_b64encode(payload.encode("utf-8")).rstrip(b"=").decode("ascii")


def main():
    if len(sys.argv) < 2:
        print("用法: python generate_key.py <用户名>")
        print("       python generate_key.py --batch users.txt")
        print()
        print("示例: python generate_key.py zhangsan")
        sys.exit(1)

    if sys.argv[1] == "--batch":
        if len(sys.argv) < 3:
            print("请指定用户列表文件: python generate_key.py --batch users.txt")
            sys.exit(1)
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            names = [line.strip() for line in f if line.strip()]
        print(f"批量生成 {len(names)} 个 key:\n")
        for name in names:
            key = generate_license_key(name)
            print(f"  {name:20s}  {key}")
    else:
        username = sys.argv[1]
        key = generate_license_key(username)
        print(f"用户名: {username}")
        print(f"License Key: {key}")
        print()
        print("将此 key 发给用户，用户在 WebUI 或 API /api/activate 输入即可激活 Pro 版。")


if __name__ == "__main__":
    main()
