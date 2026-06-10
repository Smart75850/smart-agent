#!/usr/bin/env python3
"""
元素指紋提取與相似度計算 — 移植自 Scrapling core/storage.py _StorageTools

核心概念：
  提取 HTML 元素嘅「不變特徵」—即使網站改 CSS class、改結構，
  呢啲特徵仍有較高概率保持不變：
    - 標籤名 (tag)
    - 文本內容 (text, 前 100 字)
    - 關鍵屬性 (id, name, data-*, aria-*, role, type, placeholder)
    - DOM 路徑 (tag path, 例如 body>div>ul>li)
    - 父元素標籤 (parent tag)
    - 深度 (depth)
    - class 關鍵詞 (不完整匹配)

用法:
  from src.adaptive.fingerprint import extract_fingerprint, similarity_score
  fp = extract_fingerprint(element_dict)
  score = similarity_score(fp1, fp2)
"""

import re
from typing import Optional

# 需要保留嘅屬性（即使 class/id 變咗，呢啲屬性仍有識別價值）
STABLE_ATTRS = {
    "id", "name", "role", "type", "placeholder", "aria-label",
    "data-testid", "data-id", "data-type", "data-key",
    "href", "src", "alt", "title", "for", "value",
}

# 提取 text 時要 skip 嘅元素
SKIP_TAGS = {"script", "style", "noscript", "iframe", "svg"}


def extract_fingerprint(element: dict) -> dict:
    """從元素 dict 提取不變指紋。

    :param element: {"tag": "div", "attrib": {...}, "text": "...", "parent_tag": "...", "depth": 3, ...}
    :return: 標準化指紋 dict
    """
    tag = (element.get("tag") or "").lower().strip()
    text = (element.get("text") or element.get("text_content") or "")[:200].strip()
    attrib = element.get("attrib") or element.get("attributes") or {}

    # 只保留穩定屬性
    stable_attrib = {}
    for k, v in attrib.items():
        k_lower = k.lower().strip()
        if k_lower in STABLE_ATTRS or k_lower.startswith("data-") or k_lower.startswith("aria-"):
            stable_attrib[k_lower] = str(v).strip()[:100]

    # class 關鍵詞（分拆單詞，用於模糊匹配）
    class_raw = stable_attrib.pop("class", "") or attrib.get("class", "")
    class_tokens = set(re.findall(r"[a-zA-Z0-9_-]+", str(class_raw)))

    parent_tag = (element.get("parent_tag") or element.get("parent") or "").lower().strip()
    depth = element.get("depth") or element.get("tree_depth") or 0
    if isinstance(depth, str):
        try: depth = int(depth)
        except: depth = 0

    # DOM 路徑中的關鍵節點（不含 index）
    tag_path = element.get("tag_path") or element.get("path") or ""

    return {
        "tag": tag,
        "text_preview": text[:100],
        "text_hash": _text_hash(text),
        "stable_attrs": stable_attrib,
        "class_tokens": list(class_tokens)[:20],  # 最多 20 個 class tokens
        "parent_tag": parent_tag,
        "depth": depth,
        "tag_path": tag_path,
    }


def _text_hash(text: str) -> str:
    """文本內容輕量哈希（用於快速比對）"""
    import hashlib
    cleaned = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.md5(cleaned.encode()).hexdigest()[:8] if cleaned else ""


def similarity_score(fp1: dict, fp2: dict) -> float:
    """計算兩個元素指紋嘅相似度（0.0 ~ 1.0）。

    加權規則（移植自 Scrapling __are_alike）：
      - tag 匹配: +0.30
      - 文本相似: +0.25
      - 穩定屬性匹配: +0.20
      - class tokens 交集: +0.15
      - parent_tag 匹配: +0.10

    :param fp1: 原始指紋
    :param fp2: 候選指紋
    :return: 0.0（完全唔似）~ 1.0（完全一致）
    """
    score = 0.0

    # 1. Tag 匹配（最重要） — 30%
    if fp1.get("tag") == fp2.get("tag"):
        score += 0.30

    # 2. 文本相似 — 25%
    h1 = fp1.get("text_hash", "")
    h2 = fp2.get("text_hash", "")
    if h1 and h2 and h1 == h2:
        score += 0.25
    elif h1 and h2:
        # 部分匹配：文本預覽重疊
        t1 = fp1.get("text_preview", "")[:50]
        t2 = fp2.get("text_preview", "")[:50]
        if t1 and t2:
            common = len(set(t1) & set(t2))
            score += 0.25 * (common / max(len(set(t1)), 1))

    # 3. 穩定屬性匹配 — 20%
    attrs1 = fp1.get("stable_attrs", {})
    attrs2 = fp2.get("stable_attrs", {})
    if attrs1 and attrs2:
        all_keys = set(attrs1.keys()) | set(attrs2.keys())
        if all_keys:
            matches = sum(1 for k in all_keys
                         if k in attrs1 and k in attrs2 and attrs1[k] == attrs2[k])
            score += 0.20 * (matches / len(all_keys))

    # 4. Class tokens 交集 — 15%
    tokens1 = set(fp1.get("class_tokens", []))
    tokens2 = set(fp2.get("class_tokens", []))
    if tokens1 and tokens2:
        jaccard = len(tokens1 & tokens2) / max(len(tokens1 | tokens2), 1)
        score += 0.15 * jaccard

    # 5. Parent tag 匹配 — 10%
    if fp1.get("parent_tag") and fp2.get("parent_tag"):
        if fp1["parent_tag"] == fp2["parent_tag"]:
            score += 0.10

    return min(score, 1.0)


def element_to_dict(element) -> dict:
    """從 Playwright Locator / lxml Element / BS4 Tag 提取原始元素 dict。

    支援多種元素類型，統一轉換為標準化 dict。
    """
    result = {"tag": "", "attrib": {}, "text": "", "parent_tag": "", "depth": 0, "tag_path": ""}

    try:
        # Playwright Locator (JSHandle)
        if hasattr(element, 'evaluate'):
            import asyncio
            try:
                async def _eval():
                    return await element.evaluate("""el => ({
                        tag: el.tagName?.toLowerCase() || '',
                        attrib: Object.fromEntries([...el.attributes].map(a => [a.name, a.value])),
                        text: el.textContent?.trim().substring(0, 200) || '',
                        parent_tag: el.parentElement?.tagName?.toLowerCase() || '',
                        depth: (function(e,d){while(e){d++;e=e.parentElement}return d})(el,0),
                        tag_path: (function(e,p){while(e&&e!==document.body){p.unshift(e.tagName?.toLowerCase());e=e.parentElement}return p.join('>')})(el,[])
                    })""")
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as ex:
                        future = ex.submit(asyncio.run, _eval())
                        return future.result(timeout=10)
                else:
                    return asyncio.run(_eval())
            except Exception:
                pass

        # lxml Element
        if hasattr(element, 'tag') and hasattr(element, 'attrib'):
            result["tag"] = str(element.tag).lower()
            result["attrib"] = dict(element.attrib)
            result["text"] = (element.text or "").strip()[:200]
            parent = element.getparent()
            if parent is not None:
                result["parent_tag"] = str(parent.tag).lower()
            result["depth"] = len(list(element.iterancestors()))
            ancestors = [a.tag for a in reversed(list(element.iterancestors()))]
            result["tag_path"] = ">".join(str(a) for a in ancestors[-5:])
            return result

        # BS4 Tag
        if hasattr(element, 'name') and hasattr(element, 'attrs'):
            result["tag"] = str(element.name).lower()
            result["attrib"] = dict(element.attrs)
            result["text"] = (element.get_text() or "").strip()[:200]
            parent = element.parent
            if parent and hasattr(parent, 'name'):
                result["parent_tag"] = str(parent.name).lower()
            result["depth"] = len(list(element.parents)) if hasattr(element, 'parents') else 0
            return result

        # dict（已處理）
        if isinstance(element, dict):
            return element

    except Exception:
        pass

    return result
