import { invoke } from "@tauri-apps/api/core";
import { extractEvidence } from "./intake.js";
import { recommendIndustryRoles } from "./industry_recommendation.js";

const $ = (id) => document.getElementById(id);
let selectedPath = null;
let ready = false;
let selectedEvidence = [];
let currentWorkItemId = null;
let pendingRoleId = null;
let currentRunId = null;
let currentResultVersion = null;
let currentIsGeneratedDraft = false;
let approvedPackage = false;
let providerConfig = { configured: false, endpoint: "", model: "" };
let currentPack = null;
let currentRoles = [];
let recommendedRoleIds = new Set();

const labels = {
  database: "本地数据库",
  directories: "数据目录",
  core: "Agent Ops Core",
  registry: "角色与技能注册表",
};
const packLabels = { media: "内容与媒体", engineering: "工程与项目" };

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
    if (recommendedRoleIds.has(role.id)) {
      const badge = document.createElement("span");
      badge.className = "role-recommendation-badge";
      badge.textContent = "行业建议";
      detail.append(name, badge, responsibility);
    } else {
      detail.append(name, responsibility);
    }
    const state = document.createElement("span");
    state.className = `role-state ${role.active ? "active" : "inactive"}`;
    state.textContent = role.active ? "已激活" : "未激活";
    detail.append(state);
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
  currentPack = data.pack;
  currentRoles = data.roles || [];
  $("status-pill").textContent = "本机已就绪";
  $("status-pill").className = "pill check-ok";
  $("initialize").textContent = "重新检查环境";
  $("data-location").textContent = data.data_dir;
  $("pack").value = data.pack;
  $("pack").disabled = true;
  $("choose-location").disabled = true;
  renderChecks();
  renderRoles(currentRoles);
  $("role-management-card").hidden = false;
  $("role-recommendation-note").textContent = `当前工作空间使用“${packLabels[data.pack] || data.pack}”行业包；只推荐该行业包中已注册的岗位。`;
  $("activate-media-team").hidden = data.pack !== "media";
  $("workbench").hidden = data.pack !== "media";
  if (data.pack === "media") {
    $("recent-workflows-card").hidden = false;
    setMessage("message", `本地环境已就绪。${data.roles.length} 个媒体角色已注册；角色需要激活后才会接收工作。`);
    void refreshProviderStatus();
    void refreshRecentWorkflows();
  } else {
    $("recent-workflows-card").hidden = true;
    setMessage("message", "本地环境已就绪。当前桌面需求工作流优先支持自媒体公司，请在首次设置时选择“内容与媒体”。");
  }
}

const workflowStateLabels = {
  RUNNING: "处理中",
  FAILED: "已暂停",
  BLOCKED: "等待处理",
  NEEDS_REVIEW: "待审核",
  COMPLETED: "已完成",
};
const workflowStepLabels = {
  "content-plan": "内容策划",
  "creative-brief": "视觉方案",
  "platform-package": "平台发布包",
  "human-review": "人工审核",
  "package-exported": "发布包已导出",
};

async function refreshRecentWorkflows() {
  if (!ready || currentPack !== "media") return;
  const list = $("recent-workflows-list");
  try {
    const result = await invoke("list_recent_media_workflows");
    if (result.code !== 0) throw new Error(result.msg || "读取失败");
    const items = result.data?.items || [];
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "subtle";
      empty.textContent = "完成第一项内容任务后，记录和成果会显示在这里。";
      list.replaceChildren(empty);
      setMessage("recent-workflows-message", "");
      return;
    }
    list.replaceChildren(...items.map((item) => {
      const row = document.createElement("article");
      row.className = "recent-workflow-item";
      row.setAttribute("role", "listitem");
      const detail = document.createElement("div");
      detail.className = "recent-workflow-detail";
      const title = document.createElement("strong");
      const interrupted = item.error_code === "WORKFLOW_INTERRUPTED";
      const stoppedCheckpoint = item.error_code === "WORKFLOW_CHECKPOINT_INVALID";
      const status = item.state === "RUNNING"
        ? "处理中（可能在另一窗口运行）"
        : interrupted ? "上次中断 · 可继续"
          : stoppedCheckpoint ? "已停止 · 检查点异常"
            : item.resumable && item.state === "FAILED" ? "已暂停 · 可继续"
              : workflowStateLabels[item.state] || item.state;
      title.textContent = `${item.channel || "媒体内容"} · ${status}`;
      const meta = document.createElement("p");
      meta.className = "recent-workflow-meta";
      const step = workflowStepLabels[item.current_step] || item.current_step || "已记录";
      const timestamp = item.updated_at ? new Date(item.updated_at).toLocaleString() : "时间未知";
      meta.textContent = `${item.workitem_id} · ${step} · ${timestamp}`;
      detail.append(title, meta);
      const actions = document.createElement("div");
      actions.className = "recent-workflow-actions";
      if (item.has_result) {
        const openButton = document.createElement("button");
        openButton.type = "button";
        openButton.className = "secondary";
        openButton.textContent = "打开成果";
        openButton.addEventListener("click", () => void openSavedMediaResult(item));
        actions.append(openButton);
      }
      if (item.resumable) {
        const resumeButton = document.createElement("button");
        resumeButton.type = "button";
        resumeButton.className = "secondary";
        resumeButton.textContent = "继续任务";
        resumeButton.addEventListener("click", () => resumeSavedWorkflow(item));
        actions.append(resumeButton);
      }
      row.append(detail, actions);
      return row;
    }));
    setMessage("recent-workflows-message", `显示最近 ${items.length} 项；运行记录和成果仅保存在本机。`);
  } catch {
    list.replaceChildren();
    setMessage("recent-workflows-message", "无法读取本机任务记录，请稍后刷新。", true);
  }
}

async function openSavedMediaResult(item) {
  try {
    const result = await invoke("load_saved_media_result", {
      workitemId: item.workitem_id,
      runId: item.run_id,
    });
    if (result.code !== 0) throw new Error(result.msg || "成果读取失败");
    showResult(result.data);
  } catch (error) {
    setMessage("recent-workflows-message", error instanceof Error ? error.message : "无法打开本机成果。", true);
  }
}

function resumeSavedWorkflow(item) {
  currentWorkItemId = item.workitem_id;
  currentRunId = item.run_id;
  currentResultVersion = null;
  currentIsGeneratedDraft = false;
  approvedPackage = false;
  pendingRoleId = null;
  $("activation-prompt").hidden = true;
  $("result-card").hidden = false;
  $("result-title").textContent = "继续内容任务";
  $("result-state").textContent = item.error_code === "WORKFLOW_INTERRUPTED" ? "上次运行已中断" : "等待继续";
  $("result-summary").textContent = `工作单 ${item.workitem_id} · ${workflowStepLabels[item.current_step] || item.current_step || "未完成步骤"}。已完成的有效阶段会从本机检查点恢复。`;
  $("result-content").value = "";
  $("execution-panel").hidden = false;
  $("approve-publish-package").hidden = true;
  $("performance-panel").hidden = true;
  $("provider-consent").checked = false;
  setMessage("execution-message", "继续前请检查本次使用的模型。云端模型每次恢复都需要重新确认发送范围。", false);
  setMessage("result-message", "任务状态已恢复到本机界面；确认后继续。", false);
  void refreshProviderStatus();
  updateExecutionPanel();
  $("result-card").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function refreshProviderStatus() {
  try {
    const result = await invoke("ai_provider_status");
    if (result.code !== 0) throw new Error(result.msg || "读取失败");
    providerConfig = result.data;
    $("provider-status").textContent = providerConfig.configured
      ? (providerConfig.credential_available ? `已配置 · ${providerConfig.model}` : "服务信息已保存，请重新输入密钥")
      : "尚未配置";
    if (providerConfig.configured) {
      $("provider-endpoint").value = providerConfig.endpoint;
      $("provider-model").value = providerConfig.model;
    }
    updateExecutionPanel();
  } catch {
    providerConfig = { configured: false, endpoint: "", model: "" };
    $("provider-status").textContent = "读取失败";
    updateExecutionPanel();
  }
}

function providerIsLocal() {
  if (!providerConfig.configured || !providerConfig.credential_available) return false;
  try { return ["localhost", "127.0.0.1", "::1", "[::1]"].includes(new URL(providerConfig.endpoint).hostname); }
  catch { return false; }
}

function updateExecutionPanel() {
  if (!currentWorkItemId || currentIsGeneratedDraft) return;
  const panel = $("execution-panel");
  if (!panel) return;
  panel.hidden = false;
  const button = $("run-media-workflow");
  const consent = $("provider-consent");
  if (!providerConfig.configured || !providerConfig.credential_available) {
    $("provider-target").textContent = providerConfig.configured
      ? "服务信息已保存，请在“AI 服务设置”中重新输入密钥并测试连接。"
      : "先在“AI 服务设置”中填写兼容接口地址、模型和密钥。";
    button.disabled = true;
    consent.disabled = true;
  } else {
    const local = providerIsLocal();
    $("provider-target").textContent = local
      ? `本机模型：${providerConfig.endpoint} · ${providerConfig.model}。本次只读取工作单文字和 OCR 文字。`
      : `本次将把工作单文字和 OCR 提取文字发送至：${providerConfig.endpoint}（${providerConfig.model}）。原始附件不会发送。`;
    consent.disabled = local;
    button.disabled = !local && !consent.checked;
    button.textContent = currentRunId ? "从失败步骤继续生成" : "生成内容与平台发布包";
  }
}

function needsSetup(result) {
  ready = false;
  $("role-management-card").hidden = true;
  $("workbench").hidden = true;
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
  currentRunId = data.run_id || null;
  currentResultVersion = data.version || null;
  currentIsGeneratedDraft = Boolean(data.platform_package);
  approvedPackage = data.review_state === "APPROVED";
  pendingRoleId = null;
  $("activation-prompt").hidden = true;
  $("result-card").hidden = false;
  $("result-title").textContent = data.platform_package
    ? `${data.channel || "媒体"}发布包 · v${data.version}`
    : data.routing?.deliverable_type === "video-script" ? "短视频工作方案" : "工作方案";
  $("result-state").textContent = data.platform_package
    ? approvedPackage ? "已确认 · 可手动发布" : "待人工审核"
    : "已规划 · 尚未执行";
  $("result-summary").textContent = data.platform_package
    ? approvedPackage
      ? `工作单 ${data.workitem_id} · 版本已确认，可手动发布；Sayelf 未连接平台账号。`
      : `工作单 ${data.workitem_id} · 三个媒体岗位已完成草稿、视觉方案和平台发布检查；发布包尚未确认，也未发布。`
    : `工作单 ${data.workitem_id} · 建议角色：${data.routing?.role_name || "未指定"}。方案已保存到本机成果目录，可继续生成内容并导出。`;
  $("result-content").value = data.result_content || "";
  $("execution-panel").hidden = currentIsGeneratedDraft;
  $("approve-publish-package").hidden = !currentIsGeneratedDraft;
  $("approve-publish-package").textContent = approvedPackage ? "已确认，发布包已生成" : "确认成果并生成发布包";
  $("approve-publish-package").disabled = approvedPackage;
  $("performance-panel").hidden = !approvedPackage;
  renderRoles(data.roles || []);
  if (data.saved_record) {
    setMessage("result-message", `已从本机任务记录恢复成果：${data.output_name || `版本 ${data.version}`}。`, false);
  } else if (data.output_saved === false) {
    const evidenceNote = data.output_evidence_recorded === false ? "本机状态记录也暂时不可用。" : "";
    setMessage(
      "result-message",
      `草稿已生成并可在此审核，但未能保存本机草稿文件。${evidenceNote}确认后仍可尝试生成发布包。`,
      true,
    );
  } else if (data.output_evidence_recorded === false) {
    setMessage("result-message", `草稿已保存：${data.output_name || `${data.workitem_id}.md`}，但本机状态记录暂时不可用。`, true);
  } else {
    setMessage("result-message", `已保存：${data.output_name || `${data.workitem_id}.md`}`, false);
  }
  $("execution-message").textContent = "";
  $("provider-consent").checked = false;
  void refreshProviderStatus();
  void refreshRecentWorkflows();
  $("result-card").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function runMediaWorkflow() {
  if (!currentWorkItemId || !providerConfig.configured) return;
  const button = $("run-media-workflow");
  button.disabled = true;
  button.textContent = currentRunId ? "正在从检查点继续…" : "正在生成三岗位成果…";
  setMessage("execution-message", "每个岗位的完成结果都会保存在本机；失败时可从最后完成的步骤继续。", false);
  try {
    const result = await invoke("execute_media_workflow", {
      workitemId: currentWorkItemId,
      consentToProvider: !providerIsLocal() && $("provider-consent").checked,
      resumeRunId: currentRunId,
    });
    if (result.code === 0) {
      showResult(result.data);
    } else if (result.code === 11 && result.data?.missing_roles) {
      const names = result.data.missing_roles.join("、");
      setMessage("execution-message", `请先点击“启用完整内容流程”，启用缺少的角色：${names}。`, true);
    } else if (result.data?.run_id && result.data.resumable === true) {
      currentRunId = result.data.run_id;
      $("provider-consent").checked = false;
      setMessage("execution-message", `${result.msg} 可确认后继续。${result.data.current_step || ""}`, true);
      updateExecutionPanel();
    } else {
      currentRunId = null;
      $("provider-consent").checked = false;
      setMessage("execution-message", result.msg || "内容工作流没有启动。", true);
    }
  } catch {
    setMessage("execution-message", "内容工作流没有启动，请检查模型配置和本机工作空间。", true);
  } finally {
    updateExecutionPanel();
    void refreshRecentWorkflows();
  }
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
    currentRoles = result.data.roles || [];
    renderRoles(currentRoles);
    if (pendingRoleId === roleId && active) await buildPlan();
    else setMessage("work-message", active ? "角色已激活，可处理匹配的工作。" : "角色已停用，不会接收新工作。", false);
    return true;
  } catch (error) {
    setMessage("work-message", error instanceof Error ? error.message : "角色状态没有更新。", true);
    return false;
  }
}

$("industry-recommendation-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const industry = $("industry-input").value;
  const result = recommendIndustryRoles(industry, currentPack, currentRoles);
  recommendedRoleIds = new Set(result.roles.map((role) => role.id));
  renderRoles(currentRoles);

  if (result.status === "recommended") {
    setMessage("industry-message", `“${industry.trim()}”匹配到${result.pack.name}，本机已有 ${result.roles.length} 个岗位建议。按需激活后才会接收工作。`);
  } else if (result.status === "pack-mismatch") {
    setMessage("industry-message", `“${industry.trim()}”匹配到${result.pack.name}，但当前工作空间使用“${packLabels[currentPack] || currentPack}”行业包。请在首次设置时选择对应行业包；不会跨包借用角色。`, true);
  } else if (result.status === "ambiguous") {
    setMessage("industry-message", `描述同时匹配到${result.packs.map((pack) => pack.name).join("、")}，请补充更具体的行业名称。`, true);
  } else if (result.status === "unknown") {
    setMessage("industry-message", "暂未匹配到已注册的行业岗位。可试试“自媒体公司”“MCN”或“工程项目”。", true);
  } else if (result.status === "empty") {
    setMessage("industry-message", "该行业包当前没有可推荐的已注册岗位，请重新检查本机环境。", true);
  } else {
    setMessage("industry-message", "请输入不超过 120 个字符的行业名称。", true);
  }
});

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
$("refresh-recent-workflows").addEventListener("click", () => void refreshRecentWorkflows());
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

$("activate-media-team").addEventListener("click", async () => {
  const button = $("activate-media-team");
  button.disabled = true;
  const roles = ["media.content-planner", "media.creative-producer", "media.growth-operator"];
  try {
    let allActivated = true;
    for (const roleId of roles) allActivated = (await setRoleActive(roleId, true)) && allActivated;
    setMessage("work-message", allActivated
      ? "完整内容流程已启用。现在可以选择工作方案并生成发布包。"
      : "部分角色未能启用。请检查角色列表中的状态，再重试。", !allActivated);
  } finally {
    button.disabled = false;
  }
});

$("provider-consent").addEventListener("change", updateExecutionPanel);
$("run-media-workflow").addEventListener("click", () => void runMediaWorkflow());
$("result-content").addEventListener("input", () => {
  if (approvedPackage) {
    approvedPackage = false;
    $("result-state").textContent = "有未审核修改";
    $("approve-publish-package").textContent = "确认修改并更新发布包";
    $("approve-publish-package").disabled = false;
    $("performance-panel").hidden = true;
  }
});

$("approve-publish-package").addEventListener("click", async () => {
  if (!currentWorkItemId || !currentIsGeneratedDraft) return;
  const button = $("approve-publish-package");
  button.disabled = true;
  button.textContent = "正在生成本机发布包…";
  try {
    const result = await invoke("approve_and_export_media_package", {
      workitemId: currentWorkItemId,
      version: currentResultVersion,
      content: $("result-content").value,
    });
    if (result.code !== 0) throw new Error(result.msg || "确认失败");
    approvedPackage = true;
    currentResultVersion = result.data.version;
    $("result-state").textContent = "已确认 · 可手动发布";
    button.textContent = "已确认，发布包已生成";
    $("performance-panel").hidden = false;
    setMessage("result-message", `发布包已保存到本机：${result.data.package_path}`, false);
    void refreshRecentWorkflows();
  } catch (error) {
    button.textContent = "确认成果并生成发布包";
    setMessage("result-message", error instanceof Error ? error.message : "发布包生成失败。", true);
  } finally {
    button.disabled = approvedPackage;
  }
});

$("performance-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!currentWorkItemId || !approvedPackage) return;
  const button = $("save-performance");
  const metrics = Object.fromEntries([
    ["views", "metric-views"], ["likes", "metric-likes"], ["saves", "metric-saves"],
    ["comments", "metric-comments"], ["shares", "metric-shares"],
  ].map(([key, id]) => [key, Number($(id).value || 0)]));
  button.disabled = true;
  button.textContent = "正在保存…";
  try {
    const result = await invoke("record_media_performance", { workitemId: currentWorkItemId, metrics });
    if (result.code !== 0) throw new Error(result.msg || "复盘记录保存失败。");
    const rates = result.data.rates;
    setMessage("performance-message", `已保存到本机。互动率 ${(rates.engagement_rate * 100).toFixed(2)}%，收藏率 ${(rates.save_rate * 100).toFixed(2)}%。没有历史基线时不判断表现好坏。`, false);
    $("performance-output").value = result.data.report_markdown;
    $("performance-output").hidden = false;
    $("performance-form").reset();
    $("metric-likes").value = "0";
    $("metric-saves").value = "0";
    $("metric-comments").value = "0";
    $("metric-shares").value = "0";
    $("metric-views").focus();
  } catch (error) {
    setMessage("performance-message", error instanceof Error ? error.message : "复盘记录保存失败。", true);
  } finally {
    button.disabled = false;
    button.textContent = "保存本机复盘记录";
  }
});

$("provider-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("save-provider");
  const endpoint = $("provider-endpoint").value.trim();
  const model = $("provider-model").value.trim();
  const apiKey = $("provider-key").value;
  if (!apiKey) {
    setMessage("provider-message", "请输入 API 密钥。", true);
    return;
  }
  button.disabled = true;
  button.textContent = "正在保存并测试…";
  try {
    const saved = await invoke("configure_ai_provider", { endpoint, model, apiKey });
    if (saved.code !== 0) throw new Error(saved.msg || "AI 服务设置失败。");
    $("provider-key").value = "";
    const tested = await invoke("test_ai_provider");
    if (tested.code !== 0) throw new Error(tested.msg || "连接测试失败。");
    setMessage("provider-message", "连接成功。密钥已保存在系统安全凭据库。", false);
    await refreshProviderStatus();
  } catch (error) {
    setMessage("provider-message", error instanceof Error ? error.message : "AI 服务设置或连接测试失败。", true);
  } finally {
    button.disabled = false;
    button.textContent = "保存并测试连接";
  }
});

$("clear-provider").addEventListener("click", async () => {
  const button = $("clear-provider");
  button.disabled = true;
  try {
    const result = await invoke("clear_ai_provider");
    if (result.code !== 0) throw new Error(result.msg || "AI 服务设置清除失败。");
    providerConfig = { configured: false, credential_available: false, endpoint: "", model: "" };
    $("provider-endpoint").value = "";
    $("provider-model").value = "";
    $("provider-key").value = "";
    $("provider-status").textContent = "尚未配置";
    setMessage("provider-message", "AI 服务地址、模型和密钥已清除。", false);
    updateExecutionPanel();
  } catch (error) {
    setMessage("provider-message", error instanceof Error ? error.message : "AI 服务设置清除失败。", true);
  } finally {
    button.disabled = false;
  }
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
