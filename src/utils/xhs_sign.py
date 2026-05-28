"""小红书纯 Python 签名生成 — 基于 xhshow 库。"""
from src.utils.logger import logger


def _extract_a1(cookies_str: str) -> str:
    """从 cookie 字符串中提取 a1 值。"""
    for part in cookies_str.split(";"):
        part = part.strip()
        if part.startswith("a1="):
            return part[3:]
    return ""


def generate_xs_headers(method: str, uri: str, cookies_str: str,
                        payload: dict | None = None,
                        params: dict | None = None) -> dict:
    """生成小红书签名头：x-s, x-t, x-s-common, x-b3-traceid。

    若无 a1 cookie 或 xhshow 不可用，返回空 dict（调用方应 fallback）。
    """
    a1 = _extract_a1(cookies_str)
    if not a1:
        return {}

    try:
        from xhshow import Xhshow
        client = Xhshow()
        headers = client.sign_headers(
            method=method,
            uri=uri,
            cookies=cookies_str,
            params=params,
            payload=payload,
        )
        return headers
    except ImportError:
        logger.debug("[xhs_sign] xhshow 未安装，跳过签名")
        return {}
    except Exception as e:
        logger.warning(f"[xhs_sign] 签名生成失败: {e}")
        return {}
