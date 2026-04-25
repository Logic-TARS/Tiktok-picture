const STORAGE_KEY = "tiktok-picture:last-material-selection";

const presetModels = [
  "deepseek-v4-flash",
  "deepseek-v4-pro",
  "deepseek-chat",
  "deepseek-reasoner",
];

const fields = [
  "deepseek_api_key",
  "deepseek_base_url",
  "creator_upload_url",
  "browser_profile_dir",
  "browser_path",
  "group_size",
  "hashtags_count",
  "force_9x16_upload",
  "force_9x16_mode",
  "upload_selector",
  "title_selector",
  "caption_selector",
  "topic",
  "account_position",
  "caption_style",
];

const state = {
  config: {},
  scan: null,
  jobs: [],
  selection: null,
  editingJobId: "",
  ui: {
    creatingJobs: false,
    uploadingMaterials: false,
    lastGroupSize: 4,
  },
};

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#039;",
  })[char]);
}

function log(message) {
  const line = document.createElement("div");
  line.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
  $("logBox").prepend(line);
}

function showToast(kind, title, detail = "") {
  const toast = document.createElement("div");
  toast.className = `toast ${kind}`;
  toast.innerHTML = `
    <div class="toast-title">${escapeHtml(title)}</div>
    ${detail ? `<div class="toast-detail">${escapeHtml(detail)}</div>` : ""}
  `;
  $("toastContainer").appendChild(toast);
  window.setTimeout(() => {
    toast.classList.add("closing");
    window.setTimeout(() => toast.remove(), 220);
  }, 4200);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || response.statusText);
  }
  return data;
}

function setButtonLoading(buttonId, loadingText, isLoading) {
  const button = $(buttonId);
  if (!button.dataset.defaultText) {
    button.dataset.defaultText = button.textContent;
  }
  button.disabled = isLoading;
  button.classList.toggle("loading", isLoading);
  button.textContent = isLoading ? loadingText : button.dataset.defaultText;
}

function setCreateFeedback(kind, message, detail = "") {
  const node = $("createJobsFeedback");
  if (!message) {
    node.className = "feedback-card hidden";
    node.innerHTML = "";
    return;
  }
  node.className = `feedback-card ${kind}`;
  node.innerHTML = `
    <div class="feedback-title">${escapeHtml(message)}</div>
    ${detail ? `<div class="feedback-detail">${escapeHtml(detail)}</div>` : ""}
  `;
}

function normalizeStatus(status) {
  return status === "fail" ? "failed" : (status || "pending");
}

function statusLabel(status) {
  const mapping = {
    pending: "待发布",
    captioning: "生成文案中",
    publishing: "发布中",
    need_manual: "待人工确认",
    submitted: "已提交",
    published: "已发布",
    failed: "失败",
  };
  return mapping[normalizeStatus(status)] || normalizeStatus(status);
}

function statusClassName(status) {
  const normalized = normalizeStatus(status);
  if (normalized === "failed") return "failed";
  if (normalized === "need_manual") return "need_manual";
  if (normalized === "publishing") return "publishing";
  return "";
}

function summarizeJobError(job) {
  const raw = (job.error_message || "").trim();
  if (!raw) return "";
  if (raw.includes("单文件上传控件")) {
    return raw;
  }
  if (raw.includes("single file")) {
    return "当前命中的是单文件上传控件，不是图集上传入口。";
  }
  if (raw.toLowerCase().includes("timeout")) {
    return "等待抖音页面超时，请确认当前账号仍处于登录状态。";
  }
  return raw;
}

function applyModelValue(value) {
  const model = (value || "").trim() || "deepseek-v4-flash";
  const select = $("deepseek_model_select");
  const customWrap = $("deepseek_model_custom_wrap");
  const customInput = $("deepseek_model");
  const isPreset = presetModels.includes(model);
  select.value = isPreset ? model : "__custom__";
  customInput.value = model;
  customWrap.classList.toggle("hidden", isPreset);
}

function getSelectedModelValue() {
  const value = $("deepseek_model_select").value;
  if (value === "__custom__") {
    return $("deepseek_model").value.trim() || "deepseek-v4-flash";
  }
  return value;
}

function update9x16ModeUi() {
  $("force_9x16_mode").disabled = !$("force_9x16_upload").checked;
}

function getCurrentGroupSize() {
  return Math.max(1, Number($("group_size").value || 4));
}

function updateCreateButtonLabel() {
  const groupSize = getCurrentGroupSize();
  state.ui.lastGroupSize = groupSize;
  const button = $("createJobsBtn");
  button.textContent = `创建 ${groupSize} 图任务`;
}

function saveSelectionMemory(selection) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(selection));
}

function loadSelectionMemory() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function renderSelectionSummary() {
  const node = $("selectionSummary");
  if (!state.selection) {
    node.className = "selection-summary empty";
    node.textContent = "还没有选择素材";
    return;
  }
  node.className = "selection-summary";
  node.innerHTML = `
    <div class="selection-title">${escapeHtml(state.selection.source_label || "已选择素材")}</div>
    <div class="selection-meta">
      <span>${state.selection.images_count || 0} 张图片</span>
      <span>${state.selection.groups_count || 0} 组任务</span>
      <span>当前按 ${state.selection.group_size || getCurrentGroupSize()} 张分组</span>
    </div>
  `;
}

function renderScan() {
  if (!state.scan) return;
  $("scanSummary").textContent = `${state.scan.images.length} 张图片，${state.scan.groups.length} 组，${state.scan.unsupported.length} 个不支持文件`;
  const list = $("groupsList");
  list.innerHTML = "";
  for (const [index, group] of state.scan.groups.entries()) {
    const item = document.createElement("div");
    item.className = "group-item";
    item.innerHTML = `
      <strong>第 ${index + 1} 组 · ${group.paths.length} 张${group.is_full_group ? "" : " · 不足一组"}</strong>
    `;
    for (const path of group.paths) {
      const line = document.createElement("span");
      line.textContent = path.split(/[\\/]/).slice(-2).join(" / ");
      item.appendChild(line);
    }
    list.appendChild(item);
  }
}

function setSelectionFromScan(scanResult, meta = {}) {
  state.scan = scanResult;
  state.selection = {
    upload_dir: meta.upload_dir || scanResult.upload_dir,
    source_label: meta.source_label || scanResult.source_label || "已选择素材",
    images_count: scanResult.images.length,
    groups_count: scanResult.groups.length,
    saved_count: meta.saved_count || scanResult.images.length,
    group_size: scanResult.group_size,
    remembered_at: new Date().toISOString(),
  };
  saveSelectionMemory(state.selection);
  $("restoreSelectionBtn").classList.remove("hidden");
  renderSelectionSummary();
  renderScan();
}

async function loadHealth() {
  const data = await api("/api/health");
  const parts = [
    "本地服务正常",
    data.deepseek_configured ? "DeepSeek 已配置" : "DeepSeek 未配置",
    data.playwright ? "Playwright 可用" : "Playwright 未安装",
    data.ffmpeg ? "FFmpeg 可用" : "FFmpeg 未安装",
  ];
  $("healthText").textContent = parts.join(" · ");
}

async function loadConfig() {
  state.config = await api("/api/config");
  for (const key of fields) {
    if (!$(key)) continue;
    if (key === "deepseek_api_key") {
      $(key).value = "";
    } else if ($(key).type === "checkbox") {
      $(key).checked = Boolean(state.config[key]);
    } else {
      $(key).value = state.config[key] ?? "";
    }
  }
  applyModelValue(state.config.deepseek_model || "deepseek-v4-flash");
  update9x16ModeUi();
  updateCreateButtonLabel();
}

async function saveConfig() {
  const payload = {};
  for (const key of fields) {
    if (!$(key)) continue;
    if (key === "deepseek_api_key" && !$(key).value.trim()) continue;
    payload[key] = $(key).type === "checkbox" ? $(key).checked : $(key).value.trim();
  }
  payload.deepseek_model = getSelectedModelValue();
  state.config = await api("/api/config", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  update9x16ModeUi();
  updateCreateButtonLabel();
  showToast("success", "配置已保存", `当前模型：${state.config.deepseek_model}`);
  log("配置已保存");
  await loadHealth();
}

async function uploadMaterials(files, label) {
  if (!files.length) {
    setCreateFeedback("warning", "还没有选中素材", "请先选择文件夹或图片。");
    return;
  }
  const formData = new FormData();
  formData.append("group_size", String(getCurrentGroupSize()));
  formData.append("source_label", label);
  files.forEach((file) => {
    formData.append("files", file, file.webkitRelativePath || file.name);
  });

  state.ui.uploadingMaterials = true;
  setButtonLoading("pickFolderBtn", "正在导入文件夹...", true);
  setButtonLoading("pickFilesBtn", "正在导入图片...", true);
  setCreateFeedback("info", "正在导入素材", `已选 ${files.length} 个文件，正在复制到本地工作目录。`);

  try {
    const response = await fetch("/api/materials/upload", { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || response.statusText);
    setSelectionFromScan(data, {
      upload_dir: data.upload_dir,
      source_label: label,
      saved_count: data.saved_count,
    });
    setCreateFeedback("success", "素材已导入", `${data.images.length} 张图片，已按 ${data.group_size} 张分成 ${data.groups.length} 组。`);
    showToast("success", "素材已导入", `${data.images.length} 张图片`);
    log(`素材导入完成：${data.images.length} 张图片，${data.groups.length} 组`);
  } catch (error) {
    setCreateFeedback("error", "导入素材失败", error.message || "请重试。");
    showToast("error", "导入素材失败", error.message);
    log(`导入素材失败：${error.message}`);
  } finally {
    state.ui.uploadingMaterials = false;
    setButtonLoading("pickFolderBtn", "正在导入文件夹...", false);
    setButtonLoading("pickFilesBtn", "正在导入图片...", false);
  }
}

async function rescanSelection({ silent = false } = {}) {
  if (!state.selection?.upload_dir) {
    if (!silent) {
      setCreateFeedback("warning", "还没有可重新扫描的素材", "请先导入一次素材。");
      showToast("warning", "还没有可重新扫描的素材");
    }
    return null;
  }

  const groupSize = getCurrentGroupSize();
  if (!silent) {
    setCreateFeedback("info", "正在重新分组", `按 ${groupSize} 张一组重新扫描当前素材。`);
  }

  const data = await api("/api/materials/scan", {
    method: "POST",
    body: JSON.stringify({
      paths: [state.selection.upload_dir],
      group_size: groupSize,
    }),
  });
  setSelectionFromScan(data, state.selection);
  if (!silent) {
    setCreateFeedback("success", "重新分组完成", `当前共有 ${data.groups.length} 组任务。`);
    showToast("success", "重新分组完成", `${data.groups.length} 组任务`);
  }
  log(`重新扫描完成：按 ${groupSize} 张分组，共 ${data.groups.length} 组`);
  return data;
}

async function restoreLastSelection() {
  const remembered = loadSelectionMemory();
  if (!remembered?.upload_dir) {
    showToast("warning", "没有可恢复的素材");
    return;
  }
  state.selection = remembered;
  renderSelectionSummary();
  await rescanSelection();
}

async function ensureScanMatchesGroupSize() {
  const currentGroupSize = getCurrentGroupSize();
  if (!state.scan) return null;
  if (Number(state.scan.group_size) === currentGroupSize) {
    return state.scan;
  }
  setCreateFeedback("info", "分组数已变更", `已从 ${state.scan.group_size} 张改为 ${currentGroupSize} 张，正在重新分组。`);
  return rescanSelection({ silent: false });
}

async function createJobs() {
  if (state.ui.creatingJobs) return;
  if (!state.scan || !state.scan.groups.length) {
    setCreateFeedback("warning", "还没有可创建的任务", "请先导入素材。");
    showToast("warning", "还没有可创建的任务");
    return;
  }

  await ensureScanMatchesGroupSize();
  if (!state.scan || !state.scan.groups.length) {
    return;
  }

  state.ui.creatingJobs = true;
  setButtonLoading("createJobsBtn", "正在创建任务...", true);
  setCreateFeedback(
    "info",
    `正在创建 ${state.scan.groups.length} 组任务`,
    `当前按 ${state.scan.group_size} 张一组。组数越多，文案生成时间越长。`
  );
  log(`开始创建任务：${state.scan.groups.length} 组，按 ${state.scan.group_size} 张一组`);

  try {
    const startedAt = Date.now();
    const data = await api("/api/jobs", {
      method: "POST",
      body: JSON.stringify({
        groups: state.scan.groups,
        topic: $("topic").value.trim(),
        style: $("caption_style").value,
        account_position: $("account_position").value.trim(),
        keywords: $("keywords").value.trim(),
        banned_words: $("banned_words").value.trim(),
        auto_caption: true,
        replace_existing: true,
      }),
    });
    const seconds = ((Date.now() - startedAt) / 1000).toFixed(1);
    const replacedCount = Number(data.replaced_count || 0);
    setCreateFeedback(
      "success",
      `已创建 ${data.jobs.length} 个任务`,
      `${replacedCount ? `已覆盖 ${replacedCount} 个旧任务，` : ""}耗时 ${seconds} 秒。页面已滚动到任务队列。`
    );
    showToast("success", "任务创建完成", `${data.jobs.length} 个任务${replacedCount ? `，已覆盖 ${replacedCount} 个旧任务` : ""}`);
    log(`任务创建完成：${data.jobs.length} 个任务，覆盖旧任务 ${replacedCount} 个，耗时 ${seconds} 秒`);
    await loadJobs();
    document.querySelector(".jobs-band")?.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    setCreateFeedback("error", "创建任务失败", error.message || "请查看日志。");
    showToast("error", "创建任务失败", error.message);
    log(`创建任务失败：${error.message}`);
  } finally {
    state.ui.creatingJobs = false;
    setButtonLoading("createJobsBtn", "正在创建任务...", false);
    updateCreateButtonLabel();
  }
}

async function testCaption() {
  const data = await api("/api/captions/generate", {
    method: "POST",
    body: JSON.stringify({
      topic: $("topic").value.trim(),
      style: $("caption_style").value,
      account_position: $("account_position").value.trim(),
      keywords: $("keywords").value.trim(),
      banned_words: $("banned_words").value.trim(),
      hashtags_count: Math.min(5, Number($("hashtags_count").value || 5)),
      group_index: 1,
      material_count: getCurrentGroupSize(),
    }),
  });
  $("captionPreview").textContent = JSON.stringify(data, null, 2);
  log(`测试文案已生成：${data.source || "deepseek"}`);
  showToast("success", "测试文案已生成", data.title || data.source || "DeepSeek");
}

async function loadJobs() {
  const data = await api("/api/jobs");
  state.jobs = data.jobs || [];
  renderJobs();
}

async function waitForPublishResult(id, maxChecks = 12) {
  for (let attempt = 0; attempt < maxChecks; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
    await loadJobs();
    const job = state.jobs.find((item) => item.id === id);
    if (!job) return;
    const normalized = normalizeStatus(job.status);
    if (normalized === "publishing") continue;
    if (normalized === "failed") {
      const reason = summarizeJobError(job) || "发布失败，请查看日志。";
      showToast("error", `任务 ${id} 发布失败`, reason);
      log(`任务 ${id} 发布失败：${reason}`);
      return;
    }
    showToast("success", `任务 ${id} 状态已更新`, statusLabel(normalized));
    log(`任务 ${id} 状态更新为 ${statusLabel(normalized)}`);
    return;
  }
}

function renderJobs() {
  const tbody = $("jobsTable");
  tbody.innerHTML = "";
  if (!state.jobs.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="6" class="muted">暂无任务</td>`;
    tbody.appendChild(row);
    return;
  }

  for (const job of state.jobs) {
    const errorSummary = summarizeJobError(job);
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><strong>${escapeHtml(job.id)}</strong><br><span class="muted">${escapeHtml(job.material_type)}</span></td>
      <td>${job.material_paths.length} 张</td>
      <td>
        <div>${escapeHtml(job.title || "未生成")}</div>
        ${errorSummary ? `<div class="job-detail error-text">${escapeHtml(errorSummary)}</div>` : ""}
      </td>
      <td><span class="status ${statusClassName(job.status)}">${statusLabel(job.status)}</span></td>
      <td>${escapeHtml(job.updated_at || "")}</td>
      <td>
        <div class="row-actions">
          <button class="ghost" data-edit="${escapeHtml(job.id)}" type="button">编辑</button>
          <button data-publish="${escapeHtml(job.id)}" type="button">半自动发布</button>
        </div>
      </td>
    `;
    tbody.appendChild(row);

    if (state.editingJobId === job.id) {
      const editorRow = document.createElement("tr");
      editorRow.className = "inline-editor-row";
      editorRow.innerHTML = `
        <td colspan="6">
          <div class="inline-editor">
            <div class="inline-editor-head">
              <strong>编辑任务 ${escapeHtml(job.id)}</strong>
              <span>修改后直接保存，最多 5 个话题</span>
            </div>
            <div class="inline-editor-grid">
              <label>标题
                <input id="inlineEditTitle" type="text" value="${escapeHtml(job.title || "")}">
              </label>
              <label>话题
                <input id="inlineEditHashtags" type="text" value="${escapeHtml((job.hashtags || []).join(" "))}" placeholder="用空格或逗号分隔">
              </label>
            </div>
            <label>正文
              <textarea id="inlineEditBody" rows="5">${escapeHtml(job.body || "")}</textarea>
            </label>
            <div class="row-actions inline-editor-actions">
              <button data-save-inline="${escapeHtml(job.id)}" type="button">保存任务</button>
              <button class="ghost" data-cancel-inline="1" type="button">取消</button>
            </div>
          </div>
        </td>
      `;
      tbody.appendChild(editorRow);
    }
  }

  tbody.querySelectorAll("[data-edit]").forEach((button) => {
    button.addEventListener("click", () => editJob(button.dataset.edit));
  });
  tbody.querySelectorAll("[data-publish]").forEach((button) => {
    button.addEventListener("click", () => publishJob(button.dataset.publish));
  });
  tbody.querySelectorAll("[data-save-inline]").forEach((button) => {
    button.addEventListener("click", () => saveInlineJob(button.dataset.saveInline));
  });
  tbody.querySelectorAll("[data-cancel-inline]").forEach((button) => {
    button.addEventListener("click", clearEditor);
  });
}

function editJob(id) {
  const job = state.jobs.find((item) => item.id === id);
  if (!job) return;
  state.editingJobId = state.editingJobId === job.id ? "" : job.id;
  renderJobs();
  const inlineTitle = $("inlineEditTitle");
  if (inlineTitle) {
    inlineTitle.focus();
  }
  log(`正在编辑任务 ${job.id}`);
  showToast("info", "已打开任务编辑", job.id);
}

async function saveInlineJob(id) {
  const hashtags = $("inlineEditHashtags").value
    .split(/[\s,，]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 5);

  await api(`/api/jobs/${id}`, {
    method: "POST",
    body: JSON.stringify({
      title: $("inlineEditTitle").value.trim(),
      body: $("inlineEditBody").value.trim(),
      hashtags,
    }),
  });
  state.editingJobId = "";
  await loadJobs();
  showToast("success", "任务已保存", id);
  log(`任务 ${id} 已保存`);
}

async function publishJob(id) {
  await api(`/api/jobs/${id}/publish`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  showToast("success", "已开始发布", id);
  log(`任务 ${id} 已开始发布`);
  await loadJobs();
  waitForPublishResult(id).catch((error) => {
    log(`任务 ${id} 状态轮询失败：${error.message}`);
  });
}

function clearEditor() {
  state.editingJobId = "";
  renderJobs();
}

function restoreSelectionUiHint() {
  const remembered = loadSelectionMemory();
  if (!remembered?.upload_dir) return;
  $("restoreSelectionBtn").classList.remove("hidden");
  state.selection = remembered;
  renderSelectionSummary();
}

function bindEvents() {
  $("saveConfigBtn").addEventListener("click", () => saveConfig().catch((error) => {
    log(error.message);
    showToast("error", "保存配置失败", error.message);
  }));
  $("refreshJobsBtn").addEventListener("click", () => loadJobs().catch((error) => {
    log(error.message);
    showToast("error", "刷新任务失败", error.message);
  }));
  $("scanBtn").addEventListener("click", () => rescanSelection().catch((error) => {
    log(error.message);
    showToast("error", "重新扫描失败", error.message);
  }));
  $("createJobsBtn").addEventListener("click", () => createJobs().catch((error) => {
    log(error.message);
    showToast("error", "创建任务失败", error.message);
  }));
  $("testCaptionBtn").addEventListener("click", () => testCaption().catch((error) => {
    log(error.message);
    showToast("error", "测试文案失败", error.message);
  }));

  $("deepseek_model_select").addEventListener("change", () => {
    const value = $("deepseek_model_select").value;
    applyModelValue(value === "__custom__" ? $("deepseek_model").value.trim() : value);
  });
  $("force_9x16_upload").addEventListener("change", update9x16ModeUi);
  $("group_size").addEventListener("input", () => {
    updateCreateButtonLabel();
    if (state.selection?.upload_dir) {
      setCreateFeedback("info", "分组数已修改", `当前改为 ${getCurrentGroupSize()} 张一组，创建任务前会自动重新分组。`);
    }
  });

  $("pickFolderBtn").addEventListener("click", () => $("folderPicker").click());
  $("pickFilesBtn").addEventListener("click", () => $("filePicker").click());

  $("folderPicker").addEventListener("change", async (event) => {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;
    const folderLabel = files[0].webkitRelativePath ? files[0].webkitRelativePath.split("/")[0] : "所选文件夹";
    await uploadMaterials(files, folderLabel);
    event.target.value = "";
  });

  $("filePicker").addEventListener("change", async (event) => {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;
    await uploadMaterials(files, `已选择 ${files.length} 个文件`);
    event.target.value = "";
  });

  $("restoreSelectionBtn").addEventListener("click", () => restoreLastSelection().catch((error) => {
    log(error.message);
    showToast("error", "恢复上次选择失败", error.message);
  }));
}

async function boot() {
  bindEvents();
  await loadConfig();
  await loadHealth();
  await loadJobs();
  restoreSelectionUiHint();
  renderSelectionSummary();
  log("工作台已就绪");
  showToast("info", "工作台已就绪", "可以开始选择素材或恢复上次选择");
}

boot().catch((error) => {
  log(error.message);
  showToast("error", "页面初始化失败", error.message);
});
