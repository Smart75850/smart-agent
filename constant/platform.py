from enum import Enum


class PlatformType(str, Enum):
    BILIBILI = "bilibili"
    XIAOHONGSHU = "xiaohongshu"
    DOUYIN = "douyin"
    ZHIHU = "zhihu"
    KUAISHOU = "kuaishou"


class CrawlType(str, Enum):
    SEARCH = "search"
    HOT = "hot"
    RANK = "rank"
    DETAIL = "detail"
    COMMENT = "comment"
    USER = "user"


class ErrorCode(str, Enum):
    PLATFORM_NOT_SUPPORTED = "platform_not_supported"
    TYPE_NOT_SUPPORTED = "type_not_supported"
    BROWSER_ERROR = "browser_error"
    LOGIN_REQUIRED = "login_required"
    NO_RESULTS = "no_results"
