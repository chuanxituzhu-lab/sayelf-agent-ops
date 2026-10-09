import { invoke } from "@tauri-apps/api/core";
import { extractEvidence } from "./intake.js";
import { generateWorkforceBlueprint } from "./workforce_blueprint.js";

const $ = (id) => document.getElementById(id);
let selectedPath = null;
let ready = false;
let selectedEvidence = [];
let currentWorkItemId = null;
let pendingRoleId = null;
let pendingRoleIds = [];
let currentRunId = null;
let currentResultVersion = null;
let currentIsGeneratedDraft = false;
let currentIsKernelResult = false;
let currentDeliverable = null;
// Deliverables the Agent Ops kernel runs (producer self-check + independent review).
const kernelTasks = { "title-list": "生成标题", "video-script": "生成短视频脚本" };
kernelTasks["software-feature-package"] = "生成软件功能成果包";
let approvedPackage = false;
let providerConfig = { configured: false, endpoint: "", model: "" };
let currentPack = null;
let currentRoles = [];

const labels = {
  database: "本地数据库",
  directories: "数据目录",
  core: "Agent Ops Core",
  registry: "角色与技能注册表",
};
const packLabels = { media: "内容与媒体", engineering: "工程与项目", software: "软件开发" };
const profileStorageKey = "sayelf-workforce-profile-v1";

function restoreWorkforceProfile() {
  try {
    const profile = JSON.parse(localStorage.getItem(profileStorageKey) || "null");
    if (typeof profile?.industry === "string") $("industry-input").value = profile.industry;
    if (typeof profile?.workDescription === "string") $("work-description").value = profile.workDescription;
  } catch { /* Keep first-run defaults if local storage is unavailable or invalid. */ }
}

function renderBlueprint({ scroll = false, reveal = false } = {}) {
  const industry = $("industry-input").value;
  const workDescription = $("work-description").value;
  const result = generateWorkforceBlueprint(industry, workDescription);
  if (result.status !== "generated") {
    setMessage("message", "请填写行业与业务内容（最多 1200 个字符），并检查典型工作描述长度。", true);
    $("blueprint-card").hidden = true;
    return false;
  }
  try {
    localStorage.setItem(profileStorageKey, JSON.stringify({ industry, workDescription }));
  } catch { /* The current session can still use the generated local proposal. */ }
  $("blueprint-state").textContent = "岗位方案 · 未激活";
  $("blueprint-summary").textContent = `${result.industry}${result.workDescription ? ` · ${result.workDescription}` : ""} · 最少 ${result.roleCount} 个岗位`;
  $("blueprint-roles").replaceChildren(...result.roles.map((role, index) => {
    const card = document.createElement("article");
    card.className = "blueprint-role";
    const heading = document.createElement("div");
    heading.className = "blueprint-role-heading";
    const name = document.createElement("strong");
    name.textContent = `${index + 1}. ${role.name}`;
    const state = document.createElement("span");
    state.className = "role-state inactive";
    state.textContent = "方案角色";
    heading.append(name, state);
    const responsibility = document.createElement("p");
    responsibility.textContent = role.responsibility;
    const contract = document.createElement("dl");
    contract.className = "blueprint-contract";
    for (const [label, value] of [["输入", role.input], ["工作成果", role.output], ["验收标准", role.acceptance]]) {
      const term = document.createElement("dt");
      term.textContent = label;
      const detail = document.createElement("dd");
      detail.textContent = value;
      contract.append(term, detail);
    }
    card.append(heading, responsibility, contract);
    return card;
  }));
  $("blueprint-note").textContent = result.notice;
  $("blueprint-card").hidden = !reveal;
  if (reveal && scroll) $("blueprint-card").scrollIntoView({ behavior: "smooth", block: "nearest" });
  if (!reveal) setMessage("message", "岗位方案已在本机准备；实际工作成果返回后才显示岗位闭环内容。", false);
  return true;
}

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
    detail.append(name, responsibility);
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
  $("initialize").textContent = "生成岗位方案";
  $("choose-location").textContent = "打开其他工作空间";
  $("data-location").textContent = data.data_dir;
  $("pack").value = data.pack;
  $("pack").disabled = true;
  $("choose-location").disabled = true;
  renderChecks();
  renderRoles(currentRoles);
  $("role-management-card").hidden = false;
  $("role-recommendation-note").textContent = `“${packLabels[data.pack] || data.pack}”只是示范包；下面只展示已登记的可用岗位。其他行业的岗位方案需连接相应技能后才能执行。`;
  $("activate-media-team").hidden = data.pack !== "media";
  $("activate-media-team").textContent = "启用完整内容流程";
  $("workbench").hidden = !["media", "engineering", "software"].includes(data.pack);
  $("workbench-title").textContent = data.pack === "software" ? "创建一项软件开发工作"
    : data.pack === "engineering" ? "创建一项工程专业工作" : "创建一项内容工作";
  $("channel-field").hidden = data.pack !== "media";
  $("channel").required = data.pack === "media";
  if (data.pack === "software") $("channel").value = "软件开发";
  else if (data.pack === "engineering") $("channel").value = "工程与项目";
  else if ($("channel").value === "软件开发" || $("channel").value === "工程与项目") $("channel").value = "小红书";
  $("workbench-intro").textContent = data.pack === "software"
    ? "用文字描述想完成的软件工作。Sayelf 会根据范围匹配最少岗位；明确的跨模块或架构任务才增加方案设计岗，并保留独立 QA。成果先保存在本机供你审阅。"
    : data.pack === "engineering"
      ? "写下工程专业任务，可添加文字、PDF 或照片。Sayelf 会组合已注册的专业岗位，并按成果依赖排列步骤；超出已注册能力的事项会明确提示。"
      : "写下要完成的内容工作，添加文字、PDF 或照片。Sayelf 会识别交付要求，只组合必需的已注册岗位，按成果依赖安排顺序，并保留独立审核；当前不会理解照片场景或物体，请在文字中说明画面内容。";
  $("attachment-controls").hidden = data.pack === "software";
  $("attachment-list").hidden = data.pack === "software";
  $("request").placeholder = data.pack === "software"
    ? "例如：修复登录失败；或规划一个跨模块会员系统并实现、测试。简单工作只分配开发与 QA，复杂方案才增加设计岗位。"
    : data.pack === "engineering"
      ? "例如：对比两版 BOQ 和施工图差异；检查一批试验报告并整理缺项。系统只使用当前行业包已注册的专业能力。"
      : "例如：根据产品资料写小红书新品体验笔记并生成配图方案；系统按明确交付内容匹配最少岗位。";
  if (data.pack === "media") {
    $("recent-workflows-card").hidden = false;
    setMessage("message", `本地环境已就绪。${data.roles.length} 个媒体角色已注册；角色需要激活后才会接收工作。`);
    void refreshProviderStatus();
    void refreshRecentWorkflows();
  } else if (data.pack === "software") {
    $("recent-workflows-card").hidden = true;
    setMessage("message", `本地环境已就绪。${data.roles.length} 个软件岗位已注册；系统会按任务范围选择必需岗位，独立 QA 保留。`);
    void refreshProviderStatus();
  } else if (data.pack === "engineering") {
    $("recent-workflows-card").hidden = true;
    setMessage("message", `本地环境已就绪。${data.roles.length} 个工程岗位已注册；仅在任务涉及对应交付时才加入工作流。`);
  } else {
    $("recent-workflows-card").hidden = true;
    setMessage("message", "本地环境已就绪。当前桌面需求工作流优先支持自媒体公司，请在首次设置时选择“内容与媒体”。");
  }
  try {
    if (localStorage.getItem(profileStorageKey)) renderBlueprint({ scroll: false, reveal: false });
  } catch { /* Existing workspace remains usable when browser storage is disabled. */ }
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
  currentIsKernelResult = false;
  // A resumable run belongs to the three-stage media workflow, not a kernel task.
  currentDeliverable = null;
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
  if (!currentWorkItemId || currentIsGeneratedDraft || currentIsKernelResult) return;
  const panel = $("execution-panel");
  if (!panel) return;
  if (currentPack === "engineering") {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  const button = $("run-media-workflow");
  const kernelButton = $("run-kernel-task");
  const kernelLabel = kernelTasks[currentDeliverable];
  const canRunFullMediaWorkflow = currentPack === "media" && currentDeliverable === "platform-package";
  panel.hidden = !kernelLabel && !canRunFullMediaWorkflow;
  kernelButton.hidden = !kernelLabel;
  kernelButton.textContent = kernelLabel || "";
  button.hidden = !canRunFullMediaWorkflow;
  button.className = kernelLabel ? "secondary" : "primary";
  const consent = $("provider-consent");
  if (!providerConfig.configured || !providerConfig.credential_available) {
    $("provider-target").textContent = providerConfig.configured
      ? "服务信息已保存，请在“AI 服务设置”中重新输入密钥并测试连接。"
      : "先在“AI 服务设置”中填写兼容接口地址、模型和密钥。";
    button.disabled = true;
    kernelButton.disabled = true;
    consent.disabled = true;
  } else {
    const local = providerIsLocal();
    $("consent-text").textContent = currentPack === "software"
      ? "我确认本次将需求文字，以及本流程生成的设计和实现文字发送到上述模型地址；不会上传原始文件或自动写入项目。"
      : "我确认本次将需求文字和附件中提取的文字发送到上述模型地址；照片和原始文件仍留在本机。";
    $("provider-target").textContent = local
      ? `本机模型：${providerConfig.endpoint} · ${providerConfig.model}。软件工作流会依次处理需求、设计和代码成果。`
      : currentPack === "software"
        ? `本次工作流将把需求文字和生成的设计、实现内容发送至：${providerConfig.endpoint}（${providerConfig.model}）。`
        : `本次将把工作单文字和 OCR 提取文字发送至：${providerConfig.endpoint}（${providerConfig.model}）。原始附件不会发送。`;
    consent.disabled = local;
    button.disabled = !local && !consent.checked;
    kernelButton.disabled = !local && !consent.checked;
    button.textContent = currentRunId ? "从失败步骤继续生成" : "生成内容与平台发布包";
  }
}

function needsSetup(result) {
  ready = false;
  $("role-management-card").hidden = true;
  $("workbench").hidden = true;
  $("status-pill").textContent = "等待设置";
  $("status-pill").className = "pill";
  $("pack").disabled = false;
  $("choose-location").disabled = false;
  $("initialize").textContent = "创建工作空间";
  setMessage("message", result.msg || "请选择行业包并开始设置。", result.data?.reason !== "SETUP_REQUIRED");
}

async function inspect() {
  try {
    const result = await invoke("check_environment", { dataDir: selectedPath });
    if (result.code === 0) render(result.data);
    else needsSetup(result);
  } catch {
    $("status-pill").textContent = "浏览器预览";
    setMessage("message", "浏览器预览未连接桌面运行环境。可先生成岗位方案；本机空间初始化与健康检查需在安装版中完成。", true);
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
  pendingRoleIds = data.missing_role_ids || (data.required_role_id ? [data.required_role_id] : []);
  pendingRoleId = pendingRoleIds.length === 1 ? pendingRoleIds[0] : null;
  const roles = (data.roles || []).filter((candidate) => pendingRoleIds.includes(candidate.id));
  $("suggested-role-name").textContent = roles.length > 1
    ? roles.map((role) => role.name).join(" → ")
    : roles[0]?.name || data.required_role_id || "所需岗位";
  $("suggested-role-reason").textContent = `${data.routing?.reason || "这些岗位共同负责当前交付物。"} 激活后生成工作方案。`;
  $("activate-and-continue").textContent = roles.length > 1 ? "激活所需岗位并生成方案" : "激活角色并生成方案";
  $("activation-prompt").hidden = false;
  setMessage("work-message", "已识别需求。请确认激活建议角色，再生成工作方案。", false);
  renderRoles(data.roles || []);
}

function showResult(data) {
  currentWorkItemId = data.workitem_id;
  currentRunId = data.run_id || null;
  currentResultVersion = data.version || null;
  currentIsGeneratedDraft = Boolean(data.platform_package);
  currentIsKernelResult = false;
  currentDeliverable = data.routing?.deliverable_type || null;
  renderBlueprint({ reveal: Boolean(data.platform_package) });
  approvedPackage = data.review_state === "APPROVED";
  const selectedRoleIds = data.routing?.selected_roles || [];
  const selectedRoleNames = (data.roles || [])
    .filter((role) => selectedRoleIds.includes(role.id))
    .map((role) => role.name);
  pendingRoleId = null;
  pendingRoleIds = [];
  $("activation-prompt").hidden = true;
  $("result-card").hidden = false;
  $("result-title").textContent = data.platform_package
    ? `${data.channel || "媒体"}发布包 · v${data.version}`
    : data.routing?.deliverable_type === "software-feature-package" ? "软件开发工作方案"
      : data.routing?.deliverable_type === "video-script" ? "短视频工作方案" : "工作方案";
  $("result-state").textContent = data.platform_package
    ? approvedPackage ? "已确认 · 可手动发布" : "待人工审核"
    : "已规划 · 尚未执行";
  const canGenerate = currentPack === "engineering" ? false
    : currentPack === "media"
      ? Boolean(kernelTasks[data.routing?.deliverable_type] || data.routing?.deliverable_type === "platform-package")
      : Boolean(kernelTasks[data.routing?.deliverable_type]);
  $("result-summary").textContent = data.platform_package
    ? approvedPackage
      ? `工作单 ${data.workitem_id} · 版本已确认，可手动发布；Sayelf 未连接平台账号。`
      : `工作单 ${data.workitem_id} · 三个媒体岗位已完成草稿、视觉方案和平台发布检查；发布包尚未确认，也未发布。`
    : `工作单 ${data.workitem_id} · 最少岗位 ${data.routing?.role_count || (selectedRoleNames.length || 1)} 个${selectedRoleNames.length ? `：${selectedRoleNames.join(" → ")}` : `：${data.routing?.role_name || "未指定"}`}。交付要求：${(data.routing?.requested_deliverables || [data.routing?.deliverable_type]).filter(Boolean).join("、")}。${canGenerate ? "方案已保存到本机成果目录，可继续生成已接入的岗位成果。" : "方案已保存到本机成果目录；该交付目前仅支持工作流规划，尚无对应岗位执行器，未生成虚假成果。"}`;
  $("result-content").value = data.result_content || "";
  $("execution-panel").hidden = currentIsGeneratedDraft || !canGenerate;
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

function showKernelResult(data) {
  currentWorkItemId = data.workitem_id;
  currentIsKernelResult = true;
  renderBlueprint({ reveal: true });
  currentIsGeneratedDraft = false;
  approvedPackage = false;
  $("result-card").hidden = false;
  $("result-title").textContent = data.label || "成果";
  $("result-state").textContent = "已通过自检与独立审核";
  const rework = data.rework_count ? `，经 ${data.rework_count} 轮返工` : "";
  const completedRoleIds = [...new Set((data.events || [])
    .filter((event) => event.event === "step-completed")
    .map((event) => event.role))];
  const completedRoleNames = (data.roles || [])
    .filter((role) => completedRoleIds.includes(role.id))
    .map((role) => role.name);
  $("result-summary").textContent = data.deliverable_type === "software-feature-package"
    ? `工作单 ${data.workitem_id} · 使用最少岗位：${completedRoleNames.join(" → ")}。成果经独立审核${rework}；测试尚未执行，文件尚未写入项目。`
    : `工作单 ${data.workitem_id} · 由产出岗位生成并自检，再由独立审核岗位检查${rework}。发布前请人工核对事实与平台规范。`;
  $("result-content").value = data.result_content || "";
  $("execution-panel").hidden = true;
  $("approve-publish-package").hidden = true;
  $("performance-panel").hidden = true;
  renderRoles(data.roles || []);
  setMessage("result-message", `已保存：${data.output_name}`, false);
  $("provider-consent").checked = false;
  $("result-card").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function runKernelTask() {
  if (!currentWorkItemId || !kernelTasks[currentDeliverable] || !providerConfig.configured) return;
  const button = $("run-kernel-task");
  const label = kernelTasks[currentDeliverable];
  button.disabled = true;
  button.textContent = "正在生成并审核…";
  setMessage("execution-message", "产出岗位生成后会先自检，再交给独立审核岗位；不合格会自动返工。", false);
  try {
    const result = await invoke("execute_kernel_task", {
      workitemId: currentWorkItemId,
      consentToProvider: !providerIsLocal() && $("provider-consent").checked,
    });
    if (result.code === 0) {
      showKernelResult(result.data);
    } else {
      $("provider-consent").checked = false;
      setMessage("execution-message", result.msg || `${label}没有完成。`, true);
    }
  } catch (error) {
    setMessage("execution-message", typeof error === "string" ? error : `${label}没有完成，请检查模型配置和本机工作空间。`, true);
  } finally {
    button.textContent = label;
    updateExecutionPanel();
  }
}

async function buildPlan(workitemId = currentWorkItemId) {
  if (!workitemId) return;
  const button = $("activate-and-continue");
  button.disabled = true;
  button.textContent = "正在生成方案…";
  pendingRoleIds = [];
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

$("choose-location").addEventListener("click", async () => {
  try {
    const folder = await invoke("choose_data_directory");
    if (folder) {
      selectedPath = folder;
      $("data-location").textContent = folder;
      await inspect();
    }
  } catch {
    setMessage("message", "无法打开文件夹选择窗口。", true);
  }
});

$("initialize").addEventListener("click", async () => {
  if (ready) { renderBlueprint(); return; }
  if (!$("industry-input").value.trim()) {
    setMessage("message", "请先填写行业与业务内容，再创建工作空间并生成岗位。", true);
    $("industry-input").focus();
    return;
  }
  if (!renderBlueprint({ reveal: false })) return;
  const button = $("initialize");
  button.disabled = true;
  button.textContent = "正在准备并生成岗位…";
  try {
    const result = await invoke("initialize_workspace", { pack: $("pack").value, dataDir: selectedPath });
    if (result.code === 0) {
      render(result.data);
      renderBlueprint({ reveal: false });
    }
    else needsSetup(result);
  } catch {
    setMessage("message", "岗位方案已生成；浏览器预览未连接桌面工作空间。本机初始化需在安装版中完成。", true);
  } finally {
    button.disabled = false;
    if (!ready) button.textContent = "创建工作空间并生成岗位";
  }
});

restoreWorkforceProfile();

$("recheck").addEventListener("click", inspect);
$("refresh-recent-workflows").addEventListener("click", () => void refreshRecentWorkflows());
$("add-files").addEventListener("click", addFiles);

$("request-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("activation-prompt").hidden = true;
  $("result-card").hidden = true;
  pendingRoleId = null;
  pendingRoleIds = [];
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
  if (pendingRoleIds.length > 1) {
    const roleIds = [...pendingRoleIds];
    let allActivated = true;
    for (const roleId of roleIds) allActivated = (await setRoleActive(roleId, true)) && allActivated;
    if (allActivated) await buildPlan();
  } else if (pendingRoleId) await setRoleActive(pendingRoleId, true);
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
$("run-kernel-task").addEventListener("click", () => void runKernelTask());
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
