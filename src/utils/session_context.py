"""抖音会话上下文 — 纯 HTTP 直连的最小依赖。

从 CDP Chrome 一次性收割 sessionid + ttwid + uifid，
之后 SignSrv 纯 HTTP 调用唔需要开浏览器。
"""
import json, time, random, string, socket
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SESSION_FILE = _PROJECT_ROOT / "browser_data/session_context.json"
HARVEST_FILE = _PROJECT_ROOT / "browser_data/session_context_full.json"


@dataclass
class DouyinSession:
    sessionid: str = ""
    ttwid: str = ""
    uifid: str = ""
    webid: str = ""
    odin_tt: str = ""
    passport_csrf_token: str = ""
    cookies_str: str = ""
    harvested_at: str = ""
    source_port: int = 0

    def is_valid(self) -> bool:
        return bool(self.ttwid)  # ttwid 是最关键的，sessionid/uifid 新版可能不存在

    def to_cookie_header(self) -> str:
        if self.cookies_str:
            return self.cookies_str
        pairs = []
        if self.sessionid:
            pairs.append(f"sessionid={self.sessionid}")
        if self.ttwid:
            pairs.append(f"ttwid={self.ttwid}")
        if self.odin_tt:
            pairs.append(f"odin_tt={self.odin_tt}")
        if self.passport_csrf_token:
            pairs.append(f"passport_csrf_token={self.passport_csrf_token}")
        return "; ".join(pairs)

    def to_dict(self) -> dict:
        return {
            "sessionid": self.sessionid,
            "ttwid": self.ttwid,
            "uifid": self.uifid,
            "webid": self.webid,
            "odin_tt": self.odin_tt,
            "passport_csrf_token": self.passport_csrf_token,
            "harvested_at": self.harvested_at,
            "source_port": self.source_port,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DouyinSession":
        return cls(
            sessionid=d.get("sessionid", ""),
            ttwid=d.get("ttwid", ""),
            uifid=d.get("uifid", ""),
            webid=d.get("webid", ""),
            odin_tt=d.get("odin_tt", ""),
            passport_csrf_token=d.get("passport_csrf_token", ""),
            harvested_at=d.get("harvested_at", ""),
            source_port=d.get("source_port", 0),
        )


class SessionStore:
    """会话上下文持久化存储。"""

    def __init__(self):
        self._session: DouyinSession | None = None

    @property
    def session(self) -> DouyinSession:
        if self._session is None:
            self._session = self.load()
        return self._session

    def load(self) -> DouyinSession:
        if SESSION_FILE.exists():
            try:
                data = json.loads(SESSION_FILE.read_text("utf-8"))
                sess = DouyinSession.from_dict(data)
                # 补充 cookies_str
                sess.cookies_str = data.get("cookies_str", "")
                return sess
            except (json.JSONDecodeError, KeyError):
                pass
        # fallback: 尝试从完整收割文件提取
        if HARVEST_FILE.exists():
            try:
                data = json.loads(HARVEST_FILE.read_text("utf-8"))
                cookies = data.get("cookies", {})
                return DouyinSession(
                    sessionid=cookies.get("sessionid", ""),
                    ttwid=cookies.get("ttwid", ""),
                    uifid=data.get("uifid_request", ""),
                    webid=data.get("webid", "") or "",
                    odin_tt=cookies.get("odin_tt", ""),
                    passport_csrf_token=cookies.get("passport_csrf_token", ""),
                    harvested_at=data.get("harvested_at", ""),
                )
            except (json.JSONDecodeError, KeyError):
                pass
        # fallback 2: 从 douyin_http_session.json 读完整 cookies 字符串
        http_session_file = SESSION_FILE.parent / "douyin_http_session.json"
        if http_session_file.exists():
            try:
                data = json.loads(http_session_file.read_text("utf-8"))
                cookies_str = data.get("cookies_str", "")
                sess = DouyinSession()
                sess.cookies_str = cookies_str
                # 尝试从 cookies_str 提取关键字段
                for part in cookies_str.split("; "):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        if k == "ttwid": sess.ttwid = v
                        elif k == "sessionid": sess.sessionid = v
                        elif k == "uifid": sess.uifid = v
                        elif k == "odin_tt": sess.odin_tt = v
                return sess
            except (json.JSONDecodeError, KeyError):
                pass
        return DouyinSession()

    def save(self, session: DouyinSession):
        session.harvested_at = datetime.now().isoformat()
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_FILE.write_text(
            json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
            "utf-8",
        )
        self._session = session

    async def harvest_from_cdp(self, port: int = 9223) -> DouyinSession:
        """从 CDP Chrome 收割最小会话上下文。"""
        import os
        os.environ["no_proxy"] = "127.0.0.1,localhost"
        os.environ["NO_PROXY"] = "127.0.0.1,localhost"
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            context = browser.contexts[0]
            all_cookies = await context.cookies()

            cookies = {c["name"]: c["value"] for c in all_cookies}

            # 尝试从页面获取 uifid
            page = context.pages[0] if context.pages else await context.new_page()
            uifid = ""
            try:
                uifid = await page.evaluate("""
                    () => {
                        for (let k of Object.keys(localStorage)) {
                            if (k === 'UIFID' || k === 'uifid') return localStorage.getItem(k);
                        }
                        return '';
                    }
                """)
            except Exception:
                pass

            # 如果 localStorage 没有，检查 cookie 中的 UIFID
            if not uifid:
                uifid = cookies.get("UIFID", "") or cookies.get("UIFID_TEMP", "")

            # webid: 从 cookie 中查找或生成
            webid = cookies.get("s_v_web_id", "")
            if webid and webid.startswith("verify_"):
                webid = ""

            session = DouyinSession(
                sessionid=cookies.get("sessionid", ""),
                ttwid=cookies.get("ttwid", ""),
                uifid=uifid,
                webid=webid,
                odin_tt=cookies.get("odin_tt", ""),
                passport_csrf_token=cookies.get("passport_csrf_token", ""),
                source_port=port,
            )
            await browser.close()

        if session.is_valid():
            self.save(session)

        return session


# 全局单例
session_store = SessionStore()
