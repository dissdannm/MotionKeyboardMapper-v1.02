/* MotionKeyboardMapper - Web 控制面板前端逻辑 */

const API = {
  async get(url) {
    const r = await fetch(url);
    return r.json();
  },
  async post(url, data = {}) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return r.json();
  },
};

// ─── UI 状态 ────────────────────────────────────────────────────────
let running = false;
let paused = false;
let eventSource = null;

const $ = (id) => document.getElementById(id);
const btnStart = $("btn-start");
const btnStop = $("btn-stop");
const btnPause = $("btn-pause");
const statusBadge = $("status-badge");

// ─── 初始化 ─────────────────────────────────────────────────────────
async function init() {
  await loadProfiles();
  await loadMappingTable();

  // 摄像头类型切换
  $("cam-type").addEventListener("change", onCamTypeChange);
  onCamTypeChange();

  // 按钮事件
  btnStart.addEventListener("click", onStart);
  btnStop.addEventListener("click", onStop);
  btnPause.addEventListener("click", onPause);

  // 配置变更时更新映射表
  $("profile-select").addEventListener("change", loadMappingTable);
}

async function loadProfiles() {
  try {
    const data = await API.get("/api/profiles");
    const sel = $("profile-select");
    sel.innerHTML = "";
    for (const p of data.profiles) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = `${p.name} (${p.player_count}P)`;
      if (p.id === "naruto_fighting") opt.selected = true;
      sel.appendChild(opt);
    }
  } catch (e) {
    console.error("加载档案失败:", e);
  }
}

async function loadMappingTable() {
  try {
    const profile = $("profile-select").value;
    // 直接从服务器配置中获取（简化处理：用 start 时的配置）
    const data = await API.get("/api/gestures");
    const tbody = document.querySelector("#mapping-table tbody");
    tbody.innerHTML = "";

    const profiles = await API.get("/api/profiles");
    // 加载当前选中 profile 的完整映射
    const resp = await fetch(`/api/status`);
    const status = await resp.json();

    // 从 gestures 构建映射表展示
    const gestures = data.gestures || [];
    for (const g of gestures) {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${g.name}</td>
        <td>${g.type}</td>
        <td>—</td>
        <td>—</td>
      `;
      tbody.appendChild(row);
    }
  } catch (e) {
    console.error("加载映射表失败:", e);
  }
}

// ─── 摄像头类型 ─────────────────────────────────────────────────────
function onCamTypeChange() {
  const type = $("cam-type").value;
  $("row-cam-index").classList.toggle("hidden", type === "ip");
  $("row-ip-url").classList.toggle("hidden", type !== "ip");
  $("row-cam-index-2").classList.toggle("hidden", type !== "dual");
}

// ─── 控制按钮 ───────────────────────────────────────────────────────
async function onStart() {
  // 先提交配置
  const config = {
    camera_type: $("cam-type").value,
    camera_index: parseInt($("cam-index").value) || 0,
    ip_camera_url: $("ip-url").value,
    camera_index_2: parseInt($("cam-index-2").value) || 1,
    profile: $("profile-select").value,
    cooldown_ms: parseInt($("cooldown").value) || 300,
    hold_mode: $("hold-mode").checked,
  };

  try {
    await API.post("/api/config", config);
  } catch (e) {
    console.error("配置失败:", e);
  }

  try {
    const r = await API.post("/api/start");
    if (r.ok) {
      setRunning(true);
      startSSE();
    } else {
      alert("启动失败: " + (r.detail || r.message || "未知错误"));
    }
  } catch (e) {
    alert("启动失败: " + e.message);
  }
}

async function onStop() {
  try {
    await API.post("/api/stop");
  } catch (e) {}
  setRunning(false);
  stopSSE();
}

async function onPause() {
  try {
    const r = await API.post("/api/pause");
    setPaused(r.paused);
  } catch (e) {}
}

// ─── SSE ────────────────────────────────────────────────────────────
function startSSE() {
  stopSSE();
  eventSource = new EventSource("/api/events");
  eventSource.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.gestures && data.gestures.length > 0) {
      $("gesture-text").textContent = data.gestures.join(", ");
    } else {
      $("gesture-text").textContent = "—";
    }
    if (data.keys && data.keys.length > 0) {
      $("key-text").textContent = data.keys.join(", ");
    } else {
      $("key-text").textContent = "—";
    }
    if (data.frame) {
      const img = $("video-feed");
      img.src = "data:image/jpeg;base64," + data.frame;
      img.style.display = "block";
      $("no-video").style.display = "none";
    }
    if (data.fps !== undefined) {
      $("info-fps").textContent = data.fps;
    }
    if (data.paused !== undefined) {
      setPaused(data.paused);
    }
  };
  eventSource.onerror = () => {
    // SSE 连接断开会自动重连
  };
}

function stopSSE() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  $("video-feed").style.display = "none";
  $("no-video").style.display = "flex";
  $("gesture-text").textContent = "—";
  $("key-text").textContent = "—";
}

// ─── 状态更新 ───────────────────────────────────────────────────────
function setRunning(v) {
  running = v;
  btnStart.disabled = v;
  btnStop.disabled = !v;
  btnPause.disabled = !v;
  $("cam-type").disabled = v;
  $("cam-index").disabled = v;
  $("ip-url").disabled = v;
  $("cam-index-2").disabled = v;
  $("profile-select").disabled = v;
  $("cooldown").disabled = v;
  $("hold-mode").disabled = v;

  if (v) {
    statusBadge.textContent = "运行中";
    statusBadge.className = "badge running";
  } else {
    statusBadge.textContent = "已停止";
    statusBadge.className = "badge stopped";
  }
}

function setPaused(v) {
  paused = v;
  btnPause.textContent = v ? "继续" : "暂停";
  statusBadge.textContent = v ? "已暂停" : "运行中";
  statusBadge.className = v ? "badge paused" : "badge running";
}

// ─── 启动 ───────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", init);
