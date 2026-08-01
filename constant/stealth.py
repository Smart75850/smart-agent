"""constant/stealth.py — 动态浏览器 Headers 生成（供 LightFetcher 使用）。

优先用 browserforge 生成真实浏览器指纹 headers；
未安装时回退到静态 UA。browserforge 未安装则 is_stealth_ready() 返回 False。
"""

try:
    from browserforge.headers import HeaderGenerator
    _HG = HeaderGenerator()
    HAS_BROWSERFORGE = True
except ImportError:
    _HG = None
    HAS_BROWSERFORGE = False

# 回退用的静态 Headers（browserforge 不可用时）
_STATIC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}


def is_stealth_ready() -> bool:
    """browserforge 是否可用（可用时动态生成真实指纹 headers）。"""
    return HAS_BROWSERFORGE


def generate_headers(browser_mode: bool = False) -> dict:
    """生成请求 headers。

    :param browser_mode: True 时生成完整浏览器指纹（含 sec-ch-ua 等）
    :return: headers dict
    """
    if HAS_BROWSERFORGE and _HG is not None:
        try:
            return _HG.generate()
        except Exception:
            pass
    return dict(_STATIC_HEADERS)
