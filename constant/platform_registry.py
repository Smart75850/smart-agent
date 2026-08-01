"""constant/platform_registry.py — 平台注册表（唯一权威来源）。

所有平台元数据集中于此，新增平台只需改本文件。
各层（API / CLI 编排 / adapter 工厂 / 路径白名单）应引用本注册表，
避免平台列表在 8+ 个文件里各自硬编码造成分叉。

字段说明：
    id         平台唯一标识（小写英文）
    name       中文展示名
    hot_type   热榜类型（rank/feed/keyword/question/video/topic/post）
    hot_label  热榜展示标签
    need_login 是否需要登录 cookie
    types      支持的采集类型
"""

PLATFORMS = [
    {"id": "bilibili", "name": "B站", "hot_type": "rank", "hot_label": "排行榜",
     "need_login": False, "types": ["search", "rank", "detail", "comment", "user"]},
    {"id": "xiaohongshu", "name": "小红书", "hot_type": "feed", "hot_label": "推荐热门",
     "need_login": True, "types": ["search", "hot", "detail", "comment", "user"]},
    {"id": "douyin", "name": "抖音", "hot_type": "keyword", "hot_label": "热搜关键词",
     "need_login": True, "types": ["search", "hot", "detail", "comment", "user"]},
    {"id": "zhihu", "name": "知乎", "hot_type": "question", "hot_label": "热榜问题",
     "need_login": True, "types": ["search", "hot", "detail", "comment", "user"]},
    {"id": "kuaishou", "name": "快手", "hot_type": "video", "hot_label": "热播视频",
     "need_login": False, "types": ["search", "hot", "detail", "comment", "user"]},
    {"id": "weibo", "name": "微博", "hot_type": "topic", "hot_label": "热搜话题",
     "need_login": True, "types": ["search", "hot", "detail", "comment", "user"]},
    {"id": "tieba", "name": "贴吧", "hot_type": "post", "hot_label": "热门帖子",
     "need_login": False, "types": ["search", "hot", "detail", "comment", "user"]},
]

# 平台 id 顺序列表（供 CLI 默认平台 / 编排默认参数）
PLATFORM_ID_LIST = [p["id"] for p in PLATFORMS]

# 平台 id 集合（供路径白名单 / 校验用）
PLATFORM_IDS = frozenset(PLATFORM_ID_LIST)
