"""直接从 Chromium Cookies SQLite DB 读取 cookie 并导出到 JSON"""
import json
import sqlite3
import sys
from pathlib import Path

COOKIE_DB = Path("browser_data/profile/Default/Network/Cookies")
COOKIE_DIR = Path("browser_data")

PLATFORM_DOMAINS = {
    "douyin":      ["douyin.com"],
    "xiaohongshu": ["xiaohongshu.com"],
    "kuaishou":    ["kuaishou.com"],
    "tieba":       ["tieba.baidu.com"],
    "bilibili":    ["bilibili.com"],
    "zhihu":       ["zhihu.com"],
    "weibo":       ["weibo.com"],
}


def read_chromium_cookies(db_path: Path) -> list[dict]:
    """读取 Chromium Cookies SQLite 数据库"""
    if not db_path.exists():
        print(f"Cookie DB 不存在: {db_path}")
        return []

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT host_key, name, value, encrypted_value, path, expires_utc, "
            "is_secure, is_httponly, samesite "
            "FROM cookies"
        ).fetchall()
    finally:
        conn.close()

    cookies = []
    for row in rows:
        host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite = row
        # 优先用明文 value；如果只有 encrypted_value 则跳过（无法解密）
        if not value and encrypted_value:
            continue
        if expires_utc and expires_utc > 0:
            expires_unix = (expires_utc / 1000000) - 11644473600
        else:
            expires_unix = -1

        # samesite: -1=unspecified, 0=None, 1=Lax, 2=Strict
        same_site_map = {-1: "Lax", 0: "None", 1: "Lax", 2: "Strict"}
        same_site_str = same_site_map.get(samesite, "Lax")

        cookies.append({
            "name": name,
            "value": value,
            "domain": host_key,
            "path": path,
            "expires": expires_unix,
            "httpOnly": bool(is_httponly),
            "secure": bool(is_secure),
            "sameSite": same_site_str,
        })

    return cookies


def classify_cookies(cookies):
    result = {p: [] for p in PLATFORM_DOMAINS}
    for c in cookies:
        domain = c.get("domain", "")
        for platform, domains in PLATFORM_DOMAINS.items():
            if any(d in domain for d in domains):
                result[platform].append(c)
                break
    return result


def main():
    print(f"读取 Cookie DB: {COOKIE_DB}")
    cookies = read_chromium_cookies(COOKIE_DB)
    print(f"共读取 {len(cookies)} 个 cookie")

    platform_cookies = classify_cookies(cookies)

    saved = 0
    for platform, pc in platform_cookies.items():
        path = COOKIE_DIR / f"cookies_{platform}.json"
        path.write_text(json.dumps(pc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [OK] {platform}: {len(pc)} cookies → {path}")
        saved += 1

    # 统计各平台关键 cookie
    SESSION_KEYS = {"sessionid", "SESSIONID", "login", "token", "sid", "uid", "user_id", "WEBID"}
    for platform, pc in platform_cookies.items():
        names = {c["name"] for c in pc}
        session_cookies = names & SESSION_KEYS
        if session_cookies:
            print(f"  [>>] {platform} 含关键 session cookie: {session_cookies}")

    print(f"\n完成！{saved} 个平台 cookie 已导出。")


if __name__ == "__main__":
    main()
