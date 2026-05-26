// CookieBridge popup — 读取 Chrome cookies 并 POST 到本地服务

const BRIDGE_URL = "http://localhost:18920";
const PLATFORM_DOMAINS = {
  bilibili: ".bilibili.com",
  douyin: ".douyin.com",
  xiaohongshu: ".xiaohongshu.com",
  zhihu: ".zhihu.com",
  kuaishou: ".kuaishou.com",
};

const statusEl = document.getElementById("status");
const syncBtn = document.getElementById("btn-sync");

function setStatus(text, cls) {
  statusEl.textContent = text;
  statusEl.className = "status " + (cls || "info");
}

// 全选 / 全不选
document.getElementById("btn-all").addEventListener("click", () => {
  document.querySelectorAll("#platforms input").forEach(cb => cb.checked = true);
});
document.getElementById("btn-none").addEventListener("click", () => {
  document.querySelectorAll("#platforms input").forEach(cb => cb.checked = false);
});

// 同步
syncBtn.addEventListener("click", async () => {
  const selected = [...document.querySelectorAll("#platforms input:checked")]
    .map(cb => cb.value);

  if (selected.length === 0) {
    setStatus("请至少选择一个平台", "err");
    return;
  }

  // 检测服务是否在线
  try {
    const healthResp = await fetch(BRIDGE_URL + "/health");
    if (!healthResp.ok) throw new Error("服务未就绪");
  } catch {
    setStatus("❌ 连接失败，请确认 python main.py --cookie-bridge 已启动", "err");
    return;
  }

  syncBtn.disabled = true;
  let success = 0;
  let fail = 0;

  for (const platform of selected) {
    const domain = PLATFORM_DOMAINS[platform];
    if (!domain) continue;

    setStatus(`同步中: ${platform}...`, "info");

    try {
      const cookies = await chrome.cookies.getAll({ domain });
      if (cookies.length === 0) {
        setStatus(`⚠️ ${platform}: 该域名无 cookie，请确认已登录`, "err");
        fail++;
        continue;
      }

      const resp = await fetch(BRIDGE_URL + "/cookies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform, cookies }),
      });

      const data = await resp.json();
      if (data.ok) {
        success++;
      } else {
        fail++;
        setStatus(`❌ ${platform}: ${data.error}`, "err");
      }
    } catch (e) {
      fail++;
      setStatus(`❌ ${platform}: 发送失败`, "err");
    }
  }

  syncBtn.disabled = false;
  if (fail === 0) {
    setStatus(`✅ 同步成功 (${success} 个平台)`, "ok");
  } else if (success > 0) {
    setStatus(`⚠️ 部分成功 (${success} 成功, ${fail} 失败)`, "err");
  } else {
    setStatus(`❌ 同步失败 (${fail} 个平台)`, "err");
  }
});
