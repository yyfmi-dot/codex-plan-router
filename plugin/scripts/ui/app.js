"use strict";
const $ = (id) => document.getElementById(id);
let token = location.hash.slice(1) || sessionStorage.getItem("router-token") || "";
if (token) sessionStorage.setItem("router-token", token);
history.replaceState(null, "", "/");
let loginState = null, loginTimer = null;
function notice(message) { $("notice").textContent = message || ""; }
async function api(path, body) {
  const response = await fetch("/api/" + path, {method: body ? "POST" : "GET",
    headers: {"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    ...(body ? {body: JSON.stringify(body)} : {})});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "操作失败");
  return result;
}
function row(label, state, remove) {
  const item = document.createElement("div"), title = document.createElement("span");
  title.textContent = label; item.append(title);
  const right = document.createElement("span"); right.className = "state"; right.textContent = state || "";
  item.append(right);
  if (remove) { const button = document.createElement("button"); button.textContent = "移除"; button.onclick = remove; item.append(button); }
  return item;
}
async function refresh() {
  const status = await api("status");
  $("connection").textContent = status.active ? "已启用自动路由" : "服务已就绪，等待启用";
  $("current").textContent = "当前模型：" + (status.model || "未设置");
  $("mode").value = status.mode;
  const linked = status.credential_source === "cc-switch", cc = status.cc_switch || {};
  $("cc-source").hidden = !linked; $("local-source").hidden = linked;
  $("cc-connection").textContent = cc.connected ? "已连接 CC Switch 联动版" :
    cc.stale ? "CC Switch 连接已断开，已撤下过期的凭据缓存" : "等待 CC Switch 联动版启动";
  $("accounts").replaceChildren(...(linked ? (cc.accounts || []).map((a) => {
    const engine = status.accounts.find((x) => x.email === a.label);
    return row(a.label, a.reauth_required ? "请在 CC Switch 重新认证" : a.error ? a.error :
      !a.leased ? "等待凭据" : engine && engine.recovery_stage === "quota_blocked" ? "额度冷却中，等待恢复" : "已联动");
  }) : status.accounts.map((a) => row(a.email || a.name,
    a.requires_sign_in ? "需要重新登录" : a.disabled ? "已停用" :
      a.recovery_stage === "quota_blocked" ? "额度冷却中，等待恢复" : a.status === "active" ? "可用" : (a.status || "已添加")))));
  $("keys").replaceChildren(...status.api_keys.map((k) => row(k.label, linked ? "CC Switch API 备用" : "已保存", linked ? null : async () => {
    if (!confirm("从本机路由移除此 Key？")) return;
    try { await api("key-remove", {id:k.id}); await refresh(); } catch(e) { notice(e.message); }
  })));
  const options = await api("models"), select = $("model"), prior = select.value;
  select.replaceChildren(new Option(status.model ? "沿用当前模型（" + status.model + "）" : "请选择默认模型", ""),
    ...options.models.map((m) => new Option(m, m)));
  if (options.models.includes(prior)) select.value = prior;
  $("model-note").textContent = status.model && !options.models.includes(status.model) ?
    "当前模型暂不在可用目录中，请更新模型列表或检查账号。用户可选择列表中的模型，账号切换时保持所选模型。" :
    "这里设置默认模型，之后可在 Codex 中自行选择。自动切换账号或 Plan/API 时保持请求中的模型。";
  const h = status.history || {};
  $("history").textContent = h.error || (h.backup ? "历史已备份。最近处理 " + (h.migrated || 0) +
    " 条，等待活动会话关闭后补迁 " + (h.pending || 0) + " 条。" : "首次启用后自动备份并统一历史。");
}
async function action(button, task) {
  button.disabled = true; notice("");
  try { await task(); } catch(e) { notice(e.message); }
  finally { button.disabled = false; }
}
$("refresh").onclick = () => action($("refresh"), refresh);
$("models-refresh").onclick = () => action($("models-refresh"), async () => {
  const result = await api("models-refresh", {});
  if (!result.ok) throw new Error(result.error);
  notice("模型目录已更新。已启用的 Codex 客户端重启后读取新列表。");
  await refresh();
});
$("key-form").onsubmit = (event) => {
  event.preventDefault(); const button = event.submitter || $("key-form").querySelector("button");
  action(button, async () => {
    await api("key-add", {label:$("key-label").value, key:$("key-value").value});
    $("key-value").value = ""; $("key-label").value = ""; notice("Key 已保存到本机。"); await refresh();
  });
};
$("login").onclick = () => action($("login"), async () => {
  const result = await api("login", {}); loginState = result.state;
  const link = $("login-link"); link.href = result.url; link.hidden = false;
  $("login-state").textContent = "请打开登录页面完成授权；完成后将自动显示账号。";
  // An explicit link remains usable when the browser blocks the new window.
  window.open(result.url, "_blank", "noopener,noreferrer");
  if (loginTimer) clearInterval(loginTimer);
  let attempts = 0;
  loginTimer = setInterval(async () => {
    try {
      const state = await api("login-status", {state:loginState});
      if (state.status === "ok" || state.status === "error" || ++attempts > 150) {
        clearInterval(loginTimer); loginTimer = null;
        $("login-state").textContent = state.status === "ok" ? "登录成功。" : "登录未完成，请重试。";
        await refresh();
      }
    } catch(e) { clearInterval(loginTimer); loginTimer = null; notice(e.message); }
  }, 2000);
});
$("mode").onchange = () => action($("mode"), async () => { await api("mode", {mode:$("mode").value}); await refresh(); });
$("activate").onclick = () => action($("activate"), async () => {
  await api("activate", {model:$("model").value});
  notice("已配置。请重启 Codex，之后使用同一组 custom 历史。后台会在活动会话关闭后自动补迁。");
  await refresh();
});
$("restore").onclick = () => action($("restore"), async () => {
  if (!confirm("恢复接管前配置，并按备份账本还原原官方会话分组？新消息保留。")) return;
  const result = await api("restore", {restore_history:true});
  notice(result.history && result.history.pending ? "配置已恢复；仍有活动会话，关闭后请再运行插件的恢复操作。" : "已恢复原配置。请重启 Codex。");
  await refresh();
});
refresh().catch((e) => notice(e.message));
setInterval(() => refresh().catch(() => {}), 10000);
