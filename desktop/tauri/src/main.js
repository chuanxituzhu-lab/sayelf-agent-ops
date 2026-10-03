import { invoke } from "@tauri-apps/api/core";
import { extractEvidence } from "./intake.js";

const $ = (id) => document.getElementById(id);
let selectedPath = null;
let ready = false;
let selectedEvidence = [];
let currentWorkItemId = null;
let pendingRoleId = null;

const labels = {
  database: "本地数据库",
  directories: "数据目录",
  core: "Agent Ops Core",
  registry: "角色与技能注册表",
};

function setMessage(id, message, error = false) {
  const element = $(id);
  element.textContent = message;
  element.classList.toggle("error", error);
}

function renderChecks() {
  $("checks").replaceChildren(...Object.entries(labels).map(([key, label]) => {
    const row = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = label;
    const value = document.createElement("span");
    value.className = "check-ok";
    value.textContent = "正常";
    row.append(name, value);
    return row;
  }));
}

function renderRoles(roles = []) {
  const container = $("role-list");
  if (!roles.length) {
    container.replaceChildren(Object.assign(document.createElement("p"), {
      className: "subtle", textContent: "没有可用角色。",
    }));
    return;
  }
  container.replaceChildren(...roles.map((role) => {
    const card = document.createElement("article");
    card.className = "role-item";
    const detail = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = role.name;
    const responsibility = document.createElement("p");
    responsibility.className = "subtle";
    responsibility.textContent = role.responsibility;
    const state = document.createElement("span");
    state.className = `role-state ${role.active ? "active" : "inactive"}`;
    state.textContent = role.active ? "已激活" : "未激活";
    detail.append(name, responsibility, state);
    const action = document.createElement("button");
    action.type = "button";
    action.className = role.active ? "secondary role-toggle" : "secondary role-toggle activate";
    action.textContent = role.active ? "停用" : "激活";
    action.addEventListener("click", () => void setRoleActive(role.id, !role.active));
    card.append(detail, action);
    return card;
  }));
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
  renderChecks();
  renderRoles(data.roles);
  $("workbench").hidden = data.pack !== "media";
  if (data.pack === "media") {
    setMessage("message", `本地环境已就绪。${data.roles.length} 个媒体角色已注册；角色需要激活后才会接收工作。`);
  } else {
    setMessage("message", "本地环境已就绪。当前桌面需求工作流优先支持自媒体公司，请在首次设置时选择“内容与媒体”。");
  }
}

function needsSetup(result) {
  ready = false;
  $("status-pill").textContent = "等待设置";
  $("status-pill").className = "pill";
  setMessage("message", result.msg || "请选择行业包并开始设置。", result.data?.reason !== "SETUP_REQUIRED");
}

async function inspect() {
  try {
    const result = await invoke("check_environment", { dataDir: selectedPath });
    if (result.code === 0) render(result.data);
    else needsSetup(result);
  } catch {
    setMessage("message", "无法检查本机环境，请重新安装应用后再试。", true);
  }
}

function renderAttachments() {
  const list = $("attachment-list");
  if (!selectedEvidence.length) {
    const empty = document.createElement("li");
    empty.className = "subtle empty-attachments";
    empty.textContent = "还没有添加材料";
    list.replaceChildren(empty);
    return;
  }
  list.replaceChildren(...selectedEvidence.map((file, index) => {
    const row = document.createElement("li");
    const detail = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = file.name;
    const status = document.createElement("span");
    status.className = "subtle attachment-status";
    status.textContent = file.status;
    detail.append(name, status);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "secondary remove-file";
    remove.textContent = "移除";
    remove.setAttribute("aria-label", `移除 ${file.name}`);
    remove.addEventListener("click", () => {
      selectedEvidence.splice(index, 1);
      renderAttachments();
    });
    row.append(detail, remove);
    return row;
  }));
}

async function addFiles() {
  if (selectedEvidence.length >= 5) {
    setMessage("work-message", "最多添加 5 个文件。", true);
    return;
  }
  const button = $("add-files");
  button.disabled = true;
  button.textContent = "正在读取…";
  setMessage("work-message", "材料只在本机读取和识别；请稍候。", false);
  try {
    const chosen = await invoke("choose_evidence_files");
    const existing = new Set(selectedEvidence.map((file) => file.path));
    const incoming = chosen.filter((file) => !existing.has(file.path));
    if (selectedEvidence.length + incoming.length > 5) {
      throw new Error("最多添加 5 个文件，请减少本次选择数量。");
    }
    for (const file of incoming) {
      const entry = { ...file, extractedText: "", status: "等待本机识别" };
      selectedEvidence.push(entry);
      renderAttachments();
      try {
        const rawBytes = await invoke("read_selected_evidence", { path: file.path });
        const bytes = rawBytes instanceof Uint8Array
          ? rawBytes
          : new Uint8Array(rawBytes);
        const extracted = await extractEvidence({ ...file, bytes }, (status, progress) => {
          if (typeof progress === "number") entry.status = `${status} ${Math.round(progress * 100)}%`;
          else if (status) entry.status = status;
          renderAttachments();
        });
        entry.extractedText = extracted.text;
        entry.status = extracted.status;
      } catch (error) {
        entry.extractedText = "";
        entry.status = `无法提取文字：${error instanceof Error ? error.message : "读取失败"}；原文件仍可附入工作单`;
      }
      renderAttachments();
    }
    if (incoming.length) setMessage("work-message", "材料已在本机读取。提交后会与需求一起进行角色路由。", false);
    else if (!chosen.length) setMessage("work-message", "没有选择文件。", false);
  } catch (error) {
    setMessage("work-message", error instanceof Error ? error.message : "无法读取所选文件。", true);
  } finally {
    button.disabled = false;
    button.textContent = "添加文件";
  }
}

function showActivation(result) {
  const data = result.data;
  currentWorkItemId = data.workitem_id;
  pendingRoleId = data.required_role_id;
  const role = (data.roles || []).find((candidate) => candidate.id === pendingRoleId);
  $("suggested-role-name").textContent = role?.name || pendingRoleId;
  $("suggested-role-reason").textContent = `${data.routing?.reason || "该角色最适合当前交付物。"} 激活后才会生成工作方案。`;
  $("activation-prompt").hidden = false;
  setMessage("work-message", "已识别需求。请确认激活建议角色，再生成工作方案。", false);
  renderRoles(data.roles || []);
}

function showResult(data) {
  currentWorkItemId = data.workitem_id;
  pendingRoleId = null;
  $("activation-prompt").hidden = true;
  $("result-card").hidden = false;
  $("result-title").textContent = data.routing?.deliverable_type === "video-script" ? "短视频工作方案" : "工作方案";
  $("result-state").textContent = "已规划 · 尚未执行";
  $("result-summary").textContent = `工作单 ${data.workitem_id} · 建议角色：${data.routing?.role_name || "未指定"}。方案已保存到本机成果目录，可继续编辑后导出。`;
  $("result-content").value = data.result_content || "";
  renderRoles(data.roles || []);
  setMessage("result-message", `已保存：${data.output_name || `${data.workitem_id}.md`}`, false);
  $("result-card").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function buildPlan(workitemId = currentWorkItemId) {
  if (!workitemId) return;
  const button = $("activate-and-continue");
  button.disabled = true;
  button.textContent = "正在生成方案…";
  try {
    const result = await invoke("build_workplan", { workitemId });
    if (result.code === 0) showResult(result.data);
    else setMessage("work-message", result.msg || "工作方案没有生成。", true);
  } catch {
    setMessage("work-message", "工作方案没有生成，请检查本机工作空间后重试。", true);
  } finally {
    button.disabled = false;
    button.textContent = "激活角色并生成方案";
  }
}

async function setRoleActive(roleId, active) {
  try {
    const result = await invoke("set_role_active", { roleId, active });
    if (result.code !== 0) throw new Error(result.msg || "角色状态没有更新。");
    renderRoles(result.data.roles || []);
    if (pendingRoleId === roleId && active) await buildPlan();
    else setMessage("work-message", active ? "角色已激活，可处理匹配的工作。" : "角色已停用，不会接收新工作。", false);
  } catch (error) {
    setMessage("work-message", error instanceof Error ? error.message : "角色状态没有更新。", true);
  }
}

$("choose-location").addEventListener("click", async () => {
  try {
    const folder = await invoke("choose_data_directory");
    if (folder) { selectedPath = folder; $("data-location").textContent = folder; }
  } catch {
    setMessage("message", "无法打开文件夹选择窗口。", true);
  }
});

$("initialize").addEventListener("click", async () => {
  if (ready) { await inspect(); return; }
  const button = $("initialize");
  button.disabled = true;
  button.textContent = "正在准备…";
  try {
    const result = await invoke("initialize_workspace", { pack: $("pack").value, dataDir: selectedPath });
    if (result.code === 0) render(result.data);
    else needsSetup(result);
  } catch {
    setMessage("message", "设置没有完成。请检查所选文件夹权限，再重试。", true);
  } finally {
    button.disabled = false;
    if (!ready) button.textContent = "重试设置";
  }
});

$("recheck").addEventListener("click", inspect);
$("add-files").addEventListener("click", addFiles);

$("request-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("activation-prompt").hidden = true;
  $("result-card").hidden = true;
  pendingRoleId = null;
  const button = $("create-workitem");
  button.disabled = true;
  button.textContent = "正在识别并规划…";
  try {
    const attachments = selectedEvidence.map((file) => ({
      path: file.path,
      extractedText: file.extractedText,
      extractionStatus: file.status,
    }));
    const result = await invoke("create_workitem", {
      request: $("request").value,
      channel: $("channel").value,
      attachments,
    });
    if (result.code === 11) {
      selectedEvidence = [];
      renderAttachments();
      showActivation(result);
    } else if (result.code === 0) {
      selectedEvidence = [];
      renderAttachments();
      showResult(result.data);
    }
    else setMessage("work-message", result.msg || "无法识别当前需求，请补充平台或交付内容。", true);
  } catch (error) {
    setMessage("work-message", error instanceof Error ? error.message : "无法创建工作单，请重试。", true);
  } finally {
    button.disabled = false;
    button.textContent = "识别需求并生成工作方案";
  }
});

$("activate-and-continue").addEventListener("click", async () => {
  if (pendingRoleId) await setRoleActive(pendingRoleId, true);
});

$("save-result").addEventListener("click", async () => {
  if (!currentWorkItemId) return;
  try {
    const message = await invoke("save_workitem_result", {
      workitemId: currentWorkItemId,
      content: $("result-content").value,
    });
    setMessage("result-message", message, false);
  } catch {
    setMessage("result-message", "成果保存失败，请检查数据目录权限后重试。", true);
  }
});

$("export-result").addEventListener("click", async () => {
  if (!currentWorkItemId) return;
  try {
    const destination = await invoke("export_workitem_result", {
      workitemId: currentWorkItemId,
      content: $("result-content").value,
    });
    if (destination) setMessage("result-message", `已导出到：${destination}`, false);
  } catch {
    setMessage("result-message", "成果导出失败，请重新选择一个可写入的位置。", true);
  }
});

void inspect();
