# PoC 验证：抖音搜索反爬破解

## 目标

验证两条路线能否突破抖音搜索 API 的 verify_check/2483 封杀，翻 3 页以上算通过。

---

## 路线 A：execjs + bdms.js（CSDN 2026-05-21 验证）

### 步骤

1. 安装依赖
   ```
   pip install pyexecjs
   ```

2. 获取 bdms.js
   - 从 https://github.com/zycheung/douyin_sign 下载 bdms.js
   - 或直接从 CSDN 文章附件获取

3. 编写测试脚本 `test_bdms.py`：
   - 用 execjs 加载 bdms.js
   - 补环境：`navigator.userAgent`、`document`、`window` 等
   - 调用 `bdms.sign_url(url)` 生成 a_bogus
   - 用 curl_cffi 的 impersonate 发请求
   - 搜索关键词：`"美食"` 或 `"搞笑"`（确保有大量结果）
   - 翻页 3 次以上（offset=0, 10, 20, 30）
   - API: `https://www.douyin.com/aweme/v1/web/search/item/?...&a_bogus={签名}`

4. 通过标准
   - 返回 status_code=0（非 verify_check）
   - 3 页以上，每页 10+ 条结果
   - has_more=1

5. 可能的坑
   - cookies 缺失（需要 msToken 等）
   - UA 必须与 bdms.js 签名时一致
   - 翻页时 a_bogus 需要重新生成

---

## 路线 B：MediaCrawler 直跑（GitHub 持续维护）

### 步骤

1. 克隆项目
   ```
   git clone https://github.com/NanmiCoder/MediaCrawler.git
   cd MediaCrawler
   ```

2. 按文档配好 douyin 搜索

3. 直接跑，看返回结果

4. 通过标准
   - 能搜到结果
   - 翻页正常（3 页以上）

---

## 期望产出

- 两条路线的测试结果：通过 / 不通过
- 如果通过：完整的可执行代码
- 如果失败：完整错误信息 + 日志（不要只说 "不行"）

---

## 参考

- CSDN a_bogus 破解教程（2026-05-21）：XHR 断点 + 补环境 + execjs
- MediaCrawler 搜索思路：浏览器上下文拿签名，不搞纯算法
- 我们现有的 `src/utils/abogus.py` 是旧版算法，已被抖音封杀，不要用
