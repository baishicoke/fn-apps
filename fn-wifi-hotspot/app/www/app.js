const $ = (id) => document.getElementById(id);

const statusEl = $("status");
const clientsEl = $("clients");
const msgEl = $("msg");
const toggleBtn = $("toggleHotspot");
const toggleText = $("toggleText");
const form = $("cfg");
const ifaceEl = form.elements["iface"];
const uplinkEl = form.elements["uplinkIface"];
const passwordEl = form.elements["password"];
const pwToggleBtn = $("pwToggle");

let lastRunning = false;

function setRunningUI(running, internetOk) {
  lastRunning = !!running;
  if (!toggleBtn) return;
  toggleBtn.setAttribute("aria-pressed", lastRunning ? "true" : "false");
  let suffix = "";
  if (lastRunning) {
    if (internetOk === true) suffix = "（有网）";
    else if (internetOk === false) suffix = "（无网）";
  }
  const label = `热点：${lastRunning ? "开启" : "关闭"}${suffix}`;
  if (toggleText) toggleText.textContent = label;
  else toggleBtn.textContent = label;
}

let formDirty = false;
const markDirty = () => { formDirty = true; };

let passwordVisible = false;

function setPasswordVisible(visible) {
  passwordVisible = !!visible;
  if (!passwordEl || !pwToggleBtn) return;
  passwordEl.type = passwordVisible ? "text" : "password";
  pwToggleBtn.setAttribute("aria-pressed", passwordVisible ? "true" : "false");
  pwToggleBtn.setAttribute("aria-label", passwordVisible ? "隐藏密码" : "显示密码");
  const eye = pwToggleBtn.querySelector(".icon-eye");
  const eyeOff = pwToggleBtn.querySelector(".icon-eye-off");
  if (eye) eye.style.display = passwordVisible ? "none" : "block";
  if (eyeOff) eyeOff.style.display = passwordVisible ? "block" : "none";
}

if (pwToggleBtn) {
  pwToggleBtn.addEventListener("click", () => setPasswordVisible(!passwordVisible));
  setPasswordVisible(false);
}

// Any manual edits should not be overwritten by refresh() unless forced.
form.addEventListener("input", markDirty);
form.addEventListener("change", markDirty);

let msgTimer = null;
function setMsg(t) {
  if (!msgEl) return;
  if (msgTimer) {
    clearTimeout(msgTimer);
    msgTimer = null;
  }

  const text = (t || "").toString().trim();
  if (!text) {
    msgEl.textContent = "";
    msgEl.classList.remove("show");
    return;
  }

  msgEl.textContent = text;
  msgEl.classList.add("show");
  msgTimer = setTimeout(() => {
    msgEl.classList.remove("show");
  }, 2500);
}

function formatDuration(sec) {
  const n = Number(sec);
  if (!Number.isFinite(n) || n < 0) return "";
  if (n < 60) return `${n}s`;
  const m = Math.floor(n / 60);
  const s = n % 60;
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return `${h}h ${mm}m`;
}

function formatBytes(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n < 0) return "";
  if (n < 1024) return `${n} B`;
  const kb = n / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  const gb = mb / 1024;
  return `${gb.toFixed(2)} GB`;
}

async function kickClient(mac) {
  const m = (mac || "").toString().trim().toLowerCase();
  const url = cgiUrl(`kick.cgi?mac=${encodeURIComponent(m)}`);
  return getJSON(url);
}

function renderClients(list) {
  if (!clientsEl) return;
  clientsEl.innerHTML = "";

  const clients = Array.isArray(list) ? list : [];
  if (clients.length === 0) {
    const empty = document.createElement("div");
    empty.className = "clients-empty";
    empty.textContent = "暂无客户端";
    clientsEl.appendChild(empty);
    return;
  }

  const table = document.createElement("table");
  table.className = "clients";

  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  for (const name of ["主机名", "MAC", "IP", "信号", "在线", "流量", "操作"]) {
    const th = document.createElement("th");
    th.textContent = name;
    hr.appendChild(th);
  }
  thead.appendChild(hr);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const c of clients) {
    const tr = document.createElement("tr");

    const mac = (c && c.mac) ? String(c.mac).trim().toLowerCase() : "";
    const hostname = (c && c.hostname) ? String(c.hostname) : "";
    const ip = (c && c.ip) ? String(c.ip) : "";
    const sig = (c && (c.signalDbm ?? c.signal))
      ? `${String(c.signalDbm ?? c.signal)} dBm`
      : "";
    const dur = (c && c.connectedSeconds != null)
      ? formatDuration(c.connectedSeconds)
      : "";

    const rx = (c && c.rxBytes != null) ? formatBytes(c.rxBytes) : "";
    const tx = (c && c.txBytes != null) ? formatBytes(c.txBytes) : "";
    const traffic = (rx || tx) ? `↓${rx || "0 B"} ↑${tx || "0 B"}` : "";

    for (const txt of [hostname, mac, ip, sig, dur, traffic]) {
      const td = document.createElement("td");
      td.textContent = txt;
      tr.appendChild(td);
    }

    const tdAct = document.createElement("td");
    tdAct.className = "clients-actions";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = "下线";
    btn.disabled = !/^[0-9a-f]{2}(:[0-9a-f]{2}){5}$/.test(mac);
    btn.onclick = async () => {
      if (!mac) return;
      if (!confirm(`确定要让客户端下线？\n${mac}${ip ? `\n${ip}` : ""}`)) return;
      btn.disabled = true;
      try {
        await kickClient(mac);
        setMsg("已下线");
        await refresh({ withConfig: false });
      } catch (e) {
        setMsg(e.message);
      } finally {
        btn.disabled = false;
      }
    };
    tdAct.appendChild(btn);
    tr.appendChild(tdAct);

    tbody.appendChild(tr);
  }

  table.appendChild(tbody);
  clientsEl.appendChild(table);
}

// Determine CGI path prefix based on current URL.
// - When hosted via /.../index.cgi/index.html, static files come from /.../index.cgi/...
//   and executable CGIs are exposed under ../www/cgi-bin/.
// - When hosted directly from /.../www/index.html, use ./cgi-bin/.
const CGI_PREFIX = location.pathname.includes("index.cgi") ? "../www/cgi-bin/" : "cgi-bin/";
const cgiUrl = (p) => new URL(CGI_PREFIX + p, location.href).toString();

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  const text = await r.text();
  const j = (() => {
    try { return text ? JSON.parse(text) : {}; }
    catch { return null; }
  })();
  if (!r.ok) throw new Error((j && j.error) || r.statusText);
  if (!j) throw new Error("响应不是有效 JSON");
  if (j.ok === false) throw new Error(j.error || r.statusText);
  return j;
}

async function postForm(url, dataObj) {
  const body = new URLSearchParams(dataObj).toString();
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || j.ok === false) throw new Error(j.error || r.statusText);
  return j;
}

function readForm() {
  const fd = new FormData(form);
  return {
    iface: (fd.get("iface") || "").toString().trim(),
    uplinkIface: (fd.get("uplinkIface") || "").toString().trim(),
    ipCidr: (fd.get("ipCidr") || "").toString().trim(),
    allowPorts: (fd.get("allowPorts") || "").toString().trim(),
    ssid: (fd.get("ssid") || "").toString().trim(),
    password: (fd.get("password") || "").toString(),
    band: (fd.get("band") || "bg").toString(),
    channel: (fd.get("channel") || "6").toString()
  };
}

function fillForm(cfg) {
  if (!cfg || typeof cfg !== "object") return;
  for (const [k, v] of Object.entries(cfg)) {
    const el = form.elements[k];
    if (el) el.value = v ?? "";
  }
}

function setIfaceOptions(ifaces, selected) {
  if (!ifaceEl || !ifaceEl.options) return;

  const list = Array.isArray(ifaces) ? ifaces.map(String) : [];
  const uniq = Array.from(new Set(list.filter(Boolean)));

  const keep = (selected ?? "").toString();
  const needsUnknown = keep && !uniq.includes(keep);

  ifaceEl.innerHTML = '';
  const autoOpt = document.createElement('option');
  autoOpt.value = '';
  autoOpt.textContent = '自动选择';
  ifaceEl.appendChild(autoOpt);

  for (const d of uniq) {
    const opt = document.createElement('option');
    opt.value = d;
    opt.textContent = d;
    ifaceEl.appendChild(opt);
  }

  if (needsUnknown) {
    const opt = document.createElement('option');
    opt.value = keep;
    opt.textContent = `${keep}（不可用/未检测到）`;
    ifaceEl.appendChild(opt);
  }

  ifaceEl.value = keep;
}

function setUplinkOptions(uplinks, selected) {
  if (!uplinkEl || !uplinkEl.options) return;

  const list = Array.isArray(uplinks) ? uplinks.map(String) : [];
  const uniq = Array.from(new Set(list.filter(Boolean)));

  const keep = (selected ?? "").toString();
  const needsUnknown = keep && !uniq.includes(keep);

  uplinkEl.innerHTML = '';
  const autoOpt = document.createElement('option');
  autoOpt.value = '';
  autoOpt.textContent = '自动（系统默认路由）';
  uplinkEl.appendChild(autoOpt);

  for (const d of uniq) {
    const opt = document.createElement('option');
    opt.value = d;
    opt.textContent = d;
    uplinkEl.appendChild(opt);
  }

  if (needsUnknown) {
    const opt = document.createElement('option');
    opt.value = keep;
    opt.textContent = `${keep}（不可用/未检测到）`;
    uplinkEl.appendChild(opt);
  }

  uplinkEl.value = keep;
}

async function refresh({ force = false, withConfig = true } = {}) {
  const baseline = readForm();

  if (withConfig) {
    const [cfg, st, cl, ifs, ups] = await Promise.all([
      getJSON(cgiUrl("config_get.cgi")),
      getJSON(cgiUrl("status.cgi")),
      getJSON(cgiUrl("clients.cgi")),
      getJSON(cgiUrl("ifaces.cgi")),
      getJSON(cgiUrl("uplinks.cgi")),
    ]);

    const cfgObj = cfg && cfg.config;
    const current = (!force && formDirty) ? baseline : null;
    setIfaceOptions(ifs && ifs.ifaces, current ? current.iface : (cfgObj && cfgObj.iface));
    setUplinkOptions(ups && ups.uplinks, current ? current.uplinkIface : (cfgObj && cfgObj.uplinkIface));

    if (cfgObj && (force || !formDirty)) {
      fillForm(cfgObj);
      formDirty = false;
    }

    setRunningUI(
      st && st.status && st.status.running === true,
      st && st.status ? st.status.internetOk : undefined
    );
    if (statusEl) statusEl.textContent = JSON.stringify(st.status, null, 2);
    renderClients(cl.clients);
    return;
  }

  const [st, cl, ifs, ups] = await Promise.all([
    getJSON(cgiUrl("status.cgi")),
    getJSON(cgiUrl("clients.cgi")),
    getJSON(cgiUrl("ifaces.cgi")),
    getJSON(cgiUrl("uplinks.cgi")),
  ]);

  // No config fetch: keep current form values while refreshing option lists.
  setIfaceOptions(ifs && ifs.ifaces, baseline.iface);
  setUplinkOptions(ups && ups.uplinks, baseline.uplinkIface);
  setRunningUI(
    st && st.status && st.status.running === true,
    st && st.status ? st.status.internetOk : undefined
  );
  if (statusEl) statusEl.textContent = JSON.stringify(st.status, null, 2);
  renderClients(cl.clients);
}

$("save").onclick = async (ev) => {
  if (ev && typeof ev.preventDefault === "function") ev.preventDefault();
  const saveBtn = $("save");
  try {
    if (saveBtn) saveBtn.disabled = true;
    await postForm(cgiUrl("config_set.cgi"), readForm());

    if (lastRunning) {
      setMsg("已保存，正在重启热点…");
      await getJSON(cgiUrl("stop.cgi"));
      await getJSON(cgiUrl("start.cgi"));
      setMsg("已保存并重启热点");
      await refresh({ withConfig: false });
    } else {
      setMsg("已保存");
      await refresh({ force: true });
    }
  } catch (e) {
    setMsg(e.message);
  } finally {
    if (saveBtn) saveBtn.disabled = false;
  }
};
if (toggleBtn) {
  toggleBtn.onclick = async () => {
    try {
      toggleBtn.disabled = true;
      if (lastRunning) {
        await getJSON(cgiUrl("stop.cgi"));
        setMsg("已关闭热点");
      } else {
        await getJSON(cgiUrl("start.cgi"));
        setMsg("已开启热点");
      }
      await refresh({ withConfig: false });
    } catch (e) {
      setMsg(e.message);
    } finally {
      toggleBtn.disabled = false;
    }
  };
}

refresh({ force: true }).catch(e => setMsg(e.message));

// Auto refresh clients (and running state) every 5 seconds.
let autoRefreshInFlight = false;
async function refreshClientsOnly() {
  if (autoRefreshInFlight) return;
  autoRefreshInFlight = true;
  try {
    const [st, cl] = await Promise.all([
      getJSON(cgiUrl("status.cgi")),
      getJSON(cgiUrl("clients.cgi")),
    ]);
    setRunningUI(
      st && st.status && st.status.running === true,
      st && st.status ? st.status.internetOk : undefined
    );
    renderClients(cl && cl.clients);
  } finally {
    autoRefreshInFlight = false;
  }
}

setInterval(() => {
  refreshClientsOnly().catch(() => { /* keep UI quiet */ });
}, 5000);