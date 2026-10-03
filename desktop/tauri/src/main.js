import { invoke } from "@tauri-apps/api/core";

const $ = (id) => document.getElementById(id);
let selectedPath = null;
let ready = false;
const labels = { database: "本地数据库", directories: "数据目录", core: "Agent Ops Core", registry: "角色与技能注册表" };

function showMessage(message, error = false) {
  $("message").textContent = message;
  $("message").classList.toggle("error", error);
}

function render(data) {
  ready = true;
  $("status-pill").textContent = "本机已就绪";
  $("status-pill").className = "pill check-ok";
  $("initialize").textContent = "重新检查环境";
  $("data-location").textContent = data.data_dir;
  $("pack").value = data.pack;
  $("pack").disabled = true;
  $("choose-location").disabled = true;
  $("checks").replaceChildren(...Object.entries(labels).map(([key, label]) => {
    const row = document.createElement("li");
    const name = document.createElement("span"); name.textContent = label;
    const value = document.createElement("span"); value.className = "check-ok"; value.textContent = "正常";
    row.append(name, value); return row;
  }));
  showMessage(`本地环境已就绪。当前有 ${data.roles.length} 个 ${data.pack === "media" ? "媒体" : "工程"}角色已注册，尚未激活。`);
}

function needsSetup(result) {
  ready = false;
  $("status-pill").textContent = "等待设置";
  $("status-pill").className = "pill";
  showMessage(result.msg || "请选择行业包并开始设置。", result.data?.reason !== "SETUP_REQUIRED");
}

async function inspect() {
  try {
    const result = await invoke("check_environment", { dataDir: selectedPath });
    if (result.code === 0) render(result.data); else needsSetup(result);
  } catch { showMessage("无法检查本机环境，请重新安装应用后再试。", true); }
}

$("choose-location").addEventListener("click", async () => {
  try {
    const folder = await invoke("choose_data_directory");
    if (folder) { selectedPath = folder; $("data-location").textContent = folder; }
  } catch { showMessage("无法打开文件夹选择窗口。", true); }
});

$("initialize").addEventListener("click", async () => {
  if (ready) { await inspect(); return; }
  const button = $("initialize"); button.disabled = true; button.textContent = "正在准备…";
  try {
    const result = await invoke("initialize_workspace", { pack: $("pack").value, dataDir: selectedPath });
    if (result.code === 0) render(result.data); else needsSetup(result);
  } catch { showMessage("设置没有完成。请检查所选文件夹权限，再重试。", true); }
  finally { button.disabled = false; if (!ready) button.textContent = "重试设置"; }
});

$("recheck").addEventListener("click", inspect);
void inspect();
