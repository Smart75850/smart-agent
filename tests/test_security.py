"""安全加固 + 平台注册表 + adapter 基类 覆盖测试。

覆盖本轮修复：
1. /api/config 不再泄露任何密钥字段
2. /api/data/{platform} 路径遍历被拦截
3. /api/clone SSRF 域名白名单
4. API_TOKEN 设置后鉴权生效
5. 伪造 license key 被拒绝
6. 平台注册表完整 + 每个平台都有 adapter 且继承 JsonAdapterMixin
"""
import importlib
import unittest

from fastapi.testclient import TestClient


class TestConfigSafety(unittest.TestCase):
    """/api/config 白名单 + 路径遍历 + SSRF 校验。"""

    def test_config_no_secrets(self):
        from api.main import app
        r = TestClient(app).get("/api/config")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        for k in data:
            self.assertFalse(
                any(x in k.upper() for x in ("KEY", "PASSWORD", "SECRET", "TOKEN")),
                f"字段 {k} 不应暴露（含敏感关键字）",
            )
        # 白名单基础字段仍可用（兼容前端）
        for base in ("BROWSER_ENGINE", "CDP_PORT", "STORE_BACKEND"):
            self.assertIn(base, data)

    def test_data_path_traversal_blocked(self):
        from api.main import app
        c = TestClient(app)
        # 反斜杠穿越：正则拦截 → 返回空数据（不读任何文件）
        r = c.get("/api/data/..%5C..%5Cbrowser_data")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("data"), [])
        # URL 编码斜杠：路由层直接 404 或拦截，均不得穿越读取
        r2 = c.get("/api/data/..%2F..%2Fbrowser_data")
        self.assertIn(r2.status_code, (200, 404))

    def test_clone_ssrf_validation(self):
        from api.routers.clone import _is_allowed_clone_url
        # 内网 / 环回 / 链路本地 / 云元数据 → 拒绝
        self.assertFalse(_is_allowed_clone_url("http://127.0.0.1:8000/api/config"))
        self.assertFalse(_is_allowed_clone_url("http://169.254.169.254/latest/meta-data/"))
        self.assertFalse(_is_allowed_clone_url("http://localhost/x"))
        # 危险 scheme → 拒绝
        self.assertFalse(_is_allowed_clone_url("javascript:alert(1)"))
        self.assertFalse(_is_allowed_clone_url("file:///etc/passwd"))
        # 平台白名单域名 → 放行（含短链/子域名）
        self.assertTrue(_is_allowed_clone_url("https://www.douyin.com/video/123"))
        self.assertTrue(_is_allowed_clone_url("https://b23.tv/abc"))
        self.assertTrue(_is_allowed_clone_url("https://www.bilibili.com/video/BV1xx"))


class TestAuthMiddleware(unittest.TestCase):
    """API_TOKEN 设置后鉴权生效；未设置时本机放行。"""

    def test_auth_required_when_token_set(self):
        import api.auth
        old = api.auth.settings.API_TOKEN
        try:
            api.auth.settings.API_TOKEN = "test-secret-token"
            from api.main import app
            c = TestClient(app)
            # 无 token → 401
            self.assertEqual(c.get("/api/usage").status_code, 401)
            # 错误 token → 401
            self.assertEqual(
                c.get("/api/usage", headers={"Authorization": "Bearer wrong"}).status_code,
                401,
            )
            # 正确 token → 200
            r = c.get("/api/usage", headers={"Authorization": "Bearer test-secret-token"})
            self.assertEqual(r.status_code, 200)
            # 白名单路径（/health）无需 token
            self.assertEqual(c.get("/health").status_code, 200)
        finally:
            api.auth.settings.API_TOKEN = old

    def test_ws_token_check(self):
        import api.auth
        old = api.auth.settings.API_TOKEN
        try:
            api.auth.settings.API_TOKEN = "tok-123"
            self.assertFalse(api.auth.check_ws_token(None))
            self.assertFalse(api.auth.check_ws_token("wrong"))
            self.assertTrue(api.auth.check_ws_token("tok-123"))
            api.auth.settings.API_TOKEN = ""
            self.assertTrue(api.auth.check_ws_token(None))  # 未配置 → 放行
        finally:
            api.auth.settings.API_TOKEN = old


class TestLicenseSafety(unittest.TestCase):
    """伪造 / 无效 license key 一律拒绝。"""

    def test_fake_key_rejected(self):
        from src.utils import usage_tracker as ut
        valid, _ = ut.verify_license_key("ZmFrZTpmYWtl")  # base64("fake:fake")
        self.assertFalse(valid)

    def test_malformed_key_rejected(self):
        from src.utils import usage_tracker as ut
        self.assertFalse(ut.verify_license_key("")[0])
        self.assertFalse(ut.verify_license_key("no-colon-here")[0])
        self.assertFalse(ut.verify_license_key("!!!not-base64!!!")[0])


class TestPlatformRegistry(unittest.TestCase):
    """平台注册表 = 唯一权威来源，adapter 全部继承 JsonAdapterMixin。"""

    def test_registry_complete(self):
        from constant.platform import PlatformType
        from constant.platform_registry import PLATFORMS, PLATFORM_IDS
        self.assertEqual(len(PLATFORMS), 7)
        enum_ids = {e.value for e in PlatformType}
        self.assertEqual(set(PLATFORM_IDS), enum_ids)

    def test_every_platform_has_mixin_adapter(self):
        from constant.platform_registry import PLATFORM_IDS
        from src.agents.base_adapter import JsonAdapterMixin
        for pid in PLATFORM_IDS:
            mod = importlib.import_module(f"src.agents.{pid}_adapter")
            cls = getattr(mod, f"{pid.capitalize()}Adapter")
            self.assertTrue(
                issubclass(cls, JsonAdapterMixin),
                f"{pid} adapter 未继承 JsonAdapterMixin",
            )

    def test_pipeline_defaults_match_registry(self):
        from api.routers.pipeline import _DEFAULT_PLATFORMS
        from constant.platform_registry import PLATFORM_ID_LIST
        self.assertEqual(list(_DEFAULT_PLATFORMS), PLATFORM_ID_LIST)

    def test_main_cli_platforms_match_registry(self):
        from constant.platform_registry import PLATFORM_ID_LIST
        import main as main_module
        self.assertEqual(main_module._ALL_PLATFORMS, PLATFORM_ID_LIST)


if __name__ == "__main__":
    unittest.main()
