(function () {
  "use strict";
  const KEY = "sayelf.token";
  const LABELS = {INBOX:"收件箱",SCOPED:"已定范围",WORKING:"处理中",READY:"待自检",REVIEW:"待复核",APPROVED:"待人批准",REWORK:"退回重做",DELIVERED:"已交付"};
  let config = {api: ""}, token = "", me = null, uploads = [];
  const $ = (s) => document.querySelector(s);
  const mount = () => $("#app");
  function node(tag, attrs, ...children) {
    const n = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      if (value === null || value === undefined || value === false) return;
      if (key === "class") n.className = value;
      else if (key === "text") n.textContent = value;
      else if (key.startsWith("on")) n.addEventListener(key.slice(2), value);
      else n.setAttribute(key, value === true ? "" : String(value));
    });
    children.flat().forEach((child) => {
      if (child === null || child === undefined || child === false) return;
      n.append(child instanceof Node ? child : document.createTextNode(String(child)));
    });
    return n;
  }
  const label = (state) => LABELS[state] || state || "—";
  const pill = (text, kind = "") => node("span", {class: `pill ${kind}`, text});
  const heading = (title, aside) => node("div", {class: "row between"}, node("h2", {text: title}), aside ? node("span", {class: "muted small", text: aside}) : null);
  function toast(message) { const n = $("#toast"); n.textContent = message; n.hidden = false; clearTimeout(toast.timer); toast.timer = setTimeout(() => { n.hidden = true; }, 3500); }
  const errorText = (e) => ({AUTH_REQUIRED:"请先登录",INVALID_TOKEN:"凭证已失效",ORIGIN_NOT_ALLOWED:"接口没有允许此页面来源",FILE_TYPE_NOT_ALLOWED:"这种文件类型不收",FILE_TOO_LARGE:"文件超过 20 MiB",FILE_EMPTY:"文件是空的",FILE_NAME_INVALID:"文件名不合法",XLSX_UNSAFE_XML:"Excel 含不安全 XML，已拒收",XLSX_INVALID:"Excel 文件损坏",INVALID_FILES:"附件数量或格式不对",UNKNOWN_FILE:"找不到附件",REASON_REQUIRED_TO_RETURN:"退回必须写明原因"}[e && e.code] || (e && e.message) || "操作失败");
  async function api(method, path, body) {
    const headers = {Accept: "application/json"};
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    let response;
    try { response = await fetch(config.api + path, {method, headers, body: body === undefined ? undefined : JSON.stringify(body), cache: "no-store"}); }
    catch (_) { throw Object.assign(new Error("连不上工作区接口"), {code: "NETWORK"}); }
    let data = {}; try { data = await response.json(); } catch (_) {}
    if (!response.ok) { if (response.status === 401) forget(); throw Object.assign(new Error(""), {code: data.error || `HTTP_${response.status}`}); }
    return data;
  }
  function chrome(on) {
    $("#nav").hidden = !on; $("#who").hidden = !on; $("#logout").hidden = !on; $("#runtime-status").hidden = !on;
    $("#who").textContent = on && me ? `${me.member.name || me.member.id} · 单人模式` : "";
  }
  function forget() { token = ""; me = null; try { sessionStorage.removeItem(KEY); } catch (_) {} chrome(false); }
  function login(message) {
    chrome(false);
    const input = node("input", {class: "input", type: "password", placeholder: "sao_…", autocomplete: "off"});
    const form = node("form", {class: "card login stack", onsubmit: async (event) => {
      event.preventDefault(); if (!input.value.trim()) return; token = input.value.trim();
      try { me = await api("GET", "/me"); try { sessionStorage.setItem(KEY, token); } catch (_) {} chrome(true); location.hash = "#/"; render(); }
      catch (error) { forget(); login(errorText(error)); }
    }}, node("h1", {text: "进入 Agent Ops 工作台"}), node("p", {class: "muted", text: "在本机输入行业与工作内容，Agent Ops 会给出最少岗位和可核对的交付链。"}), message ? node("div", {class: "error", text: message}) : null, node("label", {class: "field"}, "工作区凭证", input), node("button", {class: "btn", type: "submit", text: "进入工作台"}));
    mount().replaceChildren(form); input.focus();
  }
  function chips() { return node("div", {class: "chips"}, uploads.map((file, index) => node("span", {class: "chip"}, file.name, node("button", {type: "button", text: "移除", onclick: () => { uploads.splice(index, 1); render(); }})))); }
  function routeCard(data) {
    const decision = data.decision || {};
    const steps = (data.steps || []).map((step, index) => node("li", {}, node("span", {class: "num", text: String(index + 1)}), node("div", {}, node("div", {class: "step-title", text: `${step.role} · ${step.skill}`}), node("div", {class: "muted small", text: step.done_when || "完成岗位输出并留下证据"}))));
    return node("section", {class: "route stack"}, node("div", {class: "row between"}, node("div", {}, node("b", {text: `${decision.industry || "通用"} · ${decision.deliverable_type || "交付物"}`}), data.industry_input ? node("div", {class: "muted small", text: `输入行业：${data.industry_input}`}) : null), pill(`最少岗位 ${new Set((data.steps || []).map((s) => s.role)).size}`)), node("ol", {class: "steps"}, steps), node("div", {class: "notice", text: data.workflow_validation && data.workflow_validation.valid ? "工作流契约通过结构校验。" : "需要补充输入或能力后再执行。"}));
  }
  function modelSummary(model) {
    const configured = Boolean(model && model.configured);
    return node("div", {class: "status-list"},
      node("div", {class: "status-row"}, node("span", {text: "模型"}), node("b", {text: configured ? (model.model || "已配置") : "未配置，使用内置能力"})),
      node("div", {class: "status-row"}, node("span", {text: "来源"}), node("b", {text: configured ? (model.source || "本机") : "内置"})),
      node("div", {class: "status-row"}, node("span", {text: "远程调用"}), node("b", {text: configured && model.remote ? (model.remote_allowed ? "已允许" : "未允许") : "否"})),
      node("div", {class: "status-row"}, node("span", {text: "通用技能"}), node("b", {text: model && model.generic_skills ? "开启" : "未配置"})));
  }
  function statusFlow(state) {
    const states = [["INBOX", "收件"], ["SCOPED", "已定范围"], ["WORKING", "处理中"], ["READY", "待自检"], ["REVIEW", "待复核"], ["APPROVED", "待批准"], ["DELIVERED", "已交付"]];
    const current = states.findIndex(([key]) => key === state);
    return node("div", {class: "status-flow"}, states.map(([key, text], index) => node("span", {class: index === current ? "current" : index < current ? "done" : "", text})));
  }
  async function upload(file) {
    const base64 = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",")[1] || ""); reader.onerror = reject; reader.readAsDataURL(file); });
    return api("POST", "/files", {name: file.name, content_base64: base64});
  }
  async function home() {
    const [caps, items] = await Promise.all([api("GET", "/capabilities"), api("GET", "/workitems")]);
    const industry = node("input", {class: "input", maxlength: "120", placeholder: "例如：自媒体公司、软件开发、工程咨询、教育培训"});
    const text = node("textarea", {class: "input textarea", maxlength: "20000", placeholder: "输入要完成的专业工作，例如：为这篇新品写 5 个公众号标题，给出分工和交付包。"});
    const fileInput = node("input", {type: "file", multiple: true, hidden: true, accept: ".xlsx,.xls,.csv,.tsv,.txt,.md,.json,.pdf,.docx,.dwg,.dxf,.png,.jpg,.jpeg"});
    const preview = node("div", {class: "stack"}); const status = node("span", {class: "muted small"});
    fileInput.addEventListener("change", async () => {
      for (const file of Array.from(fileInput.files || [])) {
        if (uploads.length >= 10) { toast("一次最多 10 个附件"); break; }
        if (file.size > 20 * 1024 * 1024) { toast(`${file.name} 超过 20 MiB`); continue; }
        status.textContent = `正在读取 ${file.name}…`;
        try { uploads.push(await upload(file)); } catch (error) { toast(`${file.name}：${errorText(error)}`); }
      }
      fileInput.value = ""; status.textContent = ""; render();
    });
    const previewButton = node("button", {class: "btn ghost", type: "button", text: "只看分派方案", onclick: async () => {
      if (!text.value.trim()) { toast("先写工作内容"); return; }
      try { preview.replaceChildren(routeCard(await api("POST", "/route", {industry: industry.value.trim(), text: text.value.trim()}))); } catch (error) { toast(errorText(error)); }
    }});
    const submit = node("button", {class: "btn", type: "button", text: "开始执行", onclick: async () => {
      if (!text.value.trim()) { toast("先写工作内容"); return; }
      submit.disabled = true;
      try { const item = await api("POST", "/workitems", {industry: industry.value.trim(), text: text.value.trim(), files: uploads.map((file) => file.id)}); uploads = []; location.hash = `#/items/${encodeURIComponent(item.id)}`; }
      catch (error) { toast(errorText(error)); } finally { submit.disabled = false; }
    }});
    const recent = (items.workitems || []).slice(0, 5);
    const hero = node("section", {class: "hero card"}, node("h1", {text: "今天要交付什么？"}), node("p", {text: "这是通用 Agent Ops 工作台。输入行业或专业与工作内容，系统按最少岗位生成可核对的工作闭环。"}));
    const inputCard = node("section", {class: "card stack"}, heading("输入需求", "本地处理"), node("label", {class: "field"}, "行业 / 专业（可填）", industry), node("label", {class: "field"}, "工作内容", text), node("div", {class: "row"}, node("label", {class: "btn ghost", text: "附加文字 / PDF / 图片"}, fileInput)), uploads.length ? chips() : null, node("p", {class: "notice", text: "行业包只是示范与已连接能力目录；不选择行业也可以先生成路由建议。附件和工作内容均在本机处理。"}), node("div", {class: "actions"}, previewButton, submit, status), preview);
    const recentCard = node("section", {class: "card"}, heading("最近工作"), recent.length ? node("div", {class: "stack"}, recent.map((item) => node("a", {href: `#/items/${encodeURIComponent(item.id)}`, text: `${item.id} · ${label(item.state)}`}))) : node("p", {class: "empty", text: "还没有工作项。"}));
    const abilityCard = node("section", {class: "card"}, heading("共享底座"), node("p", {class: "muted small", text: "通用 Agent Ops：先识别需求，再组合最少岗位、执行技能、自检、独立复核和交付证据。"}), node("p", {class: "muted small", text: `示范行业包：${(caps.packs || []).join("、") || "暂无"}`}), node("p", {class: "muted small", text: "执行宿主：Codex；route_task 只生成可核对的岗位分工和证据要求。"}));
    return node("div", {class: "page"}, hero, node("div", {class: "grid"}, inputCard, node("aside", {class: "stack"}, recentCard, abilityCard)));
  }
  async function connections() {
    const [caps, project] = await Promise.all([api("GET", "/capabilities"), api("GET", "/project")]);
    const packs = caps.packs || [];
    const members = project.members || [];
    const model = caps.model || {};
    return node("div", {class: "page"},
      node("section", {class: "page-intro"}, node("h1", {text: "接入"}), node("p", {class: "muted", text: "两个入口，一个共享内核：Codex 负责实际工作，工作台负责输入、查看和人工批准。"})),
      node("div", {class: "connection-grid"},
        node("section", {class: "card connection-card"}, node("div", {class: "row between"}, node("h2", {text: "Codex / MCP 宿主"}), pill("已连接")), node("p", {class: "muted", text: "Codex 调用 route_task 获取岗位分工、技能、执行合同和证据要求，再完成实际工作；工作台不会把 run_task 当作宿主执行入口。"}), node("div", {class: "connection-line"}, node("span", {class: "dot"}), node("b", {text: "本机共享能力"})), node("p", {class: "muted small", text: "Agent 不能批准对外动作；发布等高风险交付仍须负责人批准。"})),
        node("section", {class: "card connection-card"}, node("div", {class: "row between"}, node("h2", {text: "模型与执行"}), pill(model.configured ? "已配置" : "内置能力")), modelSummary(model), node("p", {class: "muted small", text: model.configured && model.endpoint ? `地址：${model.endpoint}` : "未配置模型时，已注册内置技能仍可运行；其他技能会如实标记为占位产出。"}))),
      node("section", {class: "card"}, node("div", {class: "row between"}, node("h2", {text: "行业包（可选示范）"}), node("span", {class: "muted small", text: `${packs.length} 个已加载`})), node("div", {class: "pack-grid"}, packs.length ? packs.map((pack) => node("div", {class: "pack-card"}, node("b", {text: pack}), node("span", {class: "pill", text: "可路由"}), node("p", {class: "muted small", text: "作为共享底座的可替换能力目录，不决定工作台的产品行业。"}))) : node("p", {class: "empty", text: "暂未加载行业包。"}))),
      node("section", {class: "card"}, node("div", {class: "row between"}, node("h2", {text: "工作区"}), pill("本机")), node("dl", {class: "kv"}, node("dt", {text: "项目"}), node("dd", {text: project.id || "—"}), node("dt", {text: "成员"}), node("dd", {text: `${members.filter((member) => member.kind === "human").length} 位负责人，Agent 角色按需加载`}), node("dt", {text: "审批"}), node("dd", {text: "工作成果与授权绑定，审批记录保留在本机"}))));
  }
  async function items() {
    const data = await api("GET", "/workitems");
    const body = data.workitems && data.workitems.length ? node("table", {}, node("thead", {}, node("tr", {}, ["编号", "需求", "状态", "交付物", "岗位"].map((x) => node("th", {text: x})))), node("tbody", {}, data.workitems.map((item) => node("tr", {}, node("td", {}, node("a", {href: `#/items/${encodeURIComponent(item.id)}`, text: item.id})), node("td", {text: String(item.input || "").slice(0, 60)}), node("td", {}, pill(label(item.state), item.state === "APPROVED" ? "warn" : "")), node("td", {text: item.deliverable_type || "—"}), node("td", {text: item.role || "—"}))))) : node("p", {class: "empty", text: "还没有工作项。"});
    return node("div", {class: "page"}, node("section", {class: "page-intro"}, node("h1", {text: "工作项"}), node("p", {class: "muted", text: "每项工作都保留岗位分工、交付成果和证据日志，便于继续执行或人工批准。"})), node("section", {class: "card"}, heading("最近工作", `${(data.workitems || []).length} 条`), body));
  }
  async function download(file) { const response = await fetch(`${config.api}/files/${file.id}/content`, {headers: {Authorization: `Bearer ${token}`}}); if (!response.ok) throw new Error("下载失败"); const url = URL.createObjectURL(await response.blob()); const a = node("a", {href: url, download: file.name}); a.click(); setTimeout(() => URL.revokeObjectURL(url), 3000); }
  function attachmentCard(item) { if (!item.attachments || !item.attachments.length) return null; return node("section", {class: "card"}, heading("输入材料", `${item.attachments.length} 个`), node("div", {class: "stack"}, item.attachments.map((file) => node("div", {class: "row between"}, node("span", {class: "small", text: `${file.name} · ${Math.ceil((file.size || 0) / 1024)} KB`}), node("button", {class: "btn ghost", type: "button", text: "下载", onclick: () => download(file).catch((e) => toast(e.message))}))))); }
  async function itemView(id) {
    const item = await api("GET", `/workitems/${encodeURIComponent(id)}`); const gate = item.gate;
    const decide = async (approve) => { const reason = window.prompt(approve ? "批准说明（可留空）" : "退回原因（必填）", "") || ""; if (!approve && !reason.trim()) return; try { await api("POST", `/workitems/${encodeURIComponent(id)}/decision`, {approve, reason}); toast(approve ? "已批准" : "已退回"); render(); } catch (e) { toast(errorText(e)); } };
    const steps = (item.steps || []).map((step, index) => node("li", {}, node("span", {class: "num", text: String(index + 1)}), node("div", {}, node("div", {class: "step-title", text: `${step.role} · ${step.skill}`}), node("div", {class: "muted small", text: step.output || "—"}))));
    const outputs = item.outputs && item.outputs.length ? node("div", {class: "stack"}, item.outputs.map((out) => node("div", {class: "output", text: JSON.stringify(out, null, 2)}))) : node("p", {class: "empty", text: "成果尚未生成，或正在等待 Codex 执行并回填证据。"});
    const events = item.events && item.events.length ? node("div", {class: "timeline"}, item.events.map((event) => node("div", {class: "event"}, node("b", {text: event.event || "event"}), ` · ${event.actor || "—"}`))) : node("p", {class: "empty", text: "暂无事件"});
    const gateCard = gate ? node("section", {class: "card gate-card"}, heading("对外动作待批准"), node("p", {class: "muted small", text: `${gate.action || "需要批准"} · 目标：${gate.target || "当前工作项"}`}), node("p", {class: "muted small", text: gate.kind === "quorum" ? "需要所有要求的不同负责人分别批准。" : "一次批准只授权当前成果和当前动作。"}), node("div", {class: "actions"}, node("button", {class: "btn", disabled: !gate.can_decide, text: gate.can_decide ? "批准这一次" : "等待其他负责人", onclick: () => decide(true)}), node("button", {class: "btn ghost danger", disabled: !gate.can_decide, text: "退回", onclick: () => decide(false)}))) : node("section", {class: "card"}, heading("审批"), node("p", {class: "muted small", text: "当前工作项不需要人工批准，交付由执行证据决定。"}));
    const evidenceCard = node("section", {class: "card"}, heading("证据日志", `${(item.events || []).length} 条`), events);
    const main = node("div", {class: "stack"}, node("section", {class: "card"}, heading("步骤", `${(item.steps || []).length} 个岗位步骤`), node("ol", {class: "steps"}, steps)), node("section", {class: "card"}, heading("工作成果"), outputs));
    const aside = node("aside", {class: "stack"}, gateCard, attachmentCard(item), evidenceCard);
    return node("div", {class: "page"}, node("a", {class: "back-link", href: "#/items", text: "← 返回工作项"}), node("section", {class: "item-heading card"}, node("div", {class: "row between"}, node("div", {}, node("h1", {text: item.input || item.id}), node("p", {class: "muted", text: `${item.industry || "通用"} · ${item.deliverable_type || "交付物"} · ${item.role || "—"}`})), pill(label(item.state), item.state === "APPROVED" ? "warn" : "")), statusFlow(item.state)), node("div", {class: "detail-grid"}, main, aside));
  }
  async function simpleList(path, title, empty) { const data = await api("GET", path); const key = path.slice(1); const rows = data[key] || []; return node("div", {class: "page"}, node("section", {class: "card"}, heading(title, `${rows.length} 条`), rows.length ? node("div", {class: "stack"}, rows.map((row) => node("div", {class: "route"}, node("b", {text: row.workitem_id || row.id || "工作"}), node("p", {class: "muted small", text: row.role || row.input || "等待处理"})))) : node("p", {class: "empty", text: empty}))); }
  async function counts() { try { const [a, t] = await Promise.all([api("GET", "/approvals"), api("GET", "/tasks")]); $("#approval-count").textContent = a.approvals && a.approvals.length || ""; $("#task-count").textContent = t.tasks && t.tasks.length || ""; } catch (_) {} }
  async function render() {
    if (!token || !me) { login(); return; }
    const path = location.hash.slice(1) || "/";
    document.querySelectorAll("nav a").forEach((a) => a.classList.toggle("active", path === (a.dataset.view === "home" ? "/" : `/${a.dataset.view}`)));
    try { let content; if (path.startsWith("/items/")) content = await itemView(decodeURIComponent(path.slice(7))); else if (path === "/items") content = await items(); else if (path === "/approvals") content = await simpleList("/approvals", "待我批准", "没有待批准工作。"); else if (path === "/tasks") content = await simpleList("/tasks", "我的任务", "没有等待中的人工任务。"); else if (path === "/connections") content = await connections(); else content = await home(); mount().replaceChildren(content); await counts(); }
    catch (error) { mount().replaceChildren(node("section", {class: "card error", text: errorText(error)})); }
  }
  async function boot() { $("#logout").addEventListener("click", () => { forget(); render(); }); try { config = await (await fetch("/config.json")).json(); } catch (_) { config.api = "http://127.0.0.1:8765/v1"; } try { token = sessionStorage.getItem(KEY) || ""; } catch (_) {} if (token) { try { me = await api("GET", "/me"); chrome(true); } catch (_) { forget(); } } render(); }
  window.addEventListener("hashchange", render); boot();
}());
