const state = {
  file: null,
  sessionId: null,
  boxes: [],
  width: 0,
  height: 0,
  sourceImage: null,
  mode: "auto",
  items: [],
  zoom: 1,
  editMode: false,
  selectedIndex: 0,
  pointerAction: null,
  modified: false,
  undoStack: [],
  redoStack: [],
};

const elements = {
  uploadView: document.querySelector("#uploadView"),
  workspace: document.querySelector("#workspace"),
  dropZone: document.querySelector("#dropZone"),
  fileInput: document.querySelector("#fileInput"),
  replaceButton: document.querySelector("#replaceButton"),
  reanalyzeButton: document.querySelector("#reanalyzeButton"),
  rowInput: document.querySelector("#rowInput"),
  columnInput: document.querySelector("#columnInput"),
  gridFields: document.querySelector("#gridFields"),
  editModeButton: document.querySelector("#editModeButton"),
  addBoxButton: document.querySelector("#addBoxButton"),
  deleteBoxButton: document.querySelector("#deleteBoxButton"),
  undoButton: document.querySelector("#undoButton"),
  redoButton: document.querySelector("#redoButton"),
  fitButton: document.querySelector("#fitButton"),
  zoomInput: document.querySelector("#zoomInput"),
  zoomValue: document.querySelector("#zoomValue"),
  canvasStage: document.querySelector("#canvasStage"),
  editHint: document.querySelector("#editHint"),
  sourceCanvas: document.querySelector("#sourceCanvas"),
  canvasLoading: document.querySelector("#canvasLoading"),
  sourceTitle: document.querySelector("#sourceTitle"),
  imageMeta: document.querySelector("#imageMeta"),
  detectMeta: document.querySelector("#detectMeta"),
  cropCount: document.querySelector("#cropCount"),
  cropList: document.querySelector("#cropList"),
  folderName: document.querySelector("#folderName"),
  bulkName: document.querySelector("#bulkName"),
  bulkApplyButton: document.querySelector("#bulkApplyButton"),
  lightbox: document.querySelector("#lightbox"),
  lightboxImg: document.querySelector("#lightboxImg"),
  lightboxClose: document.querySelector("#lightboxClose"),
  enabledCount: document.querySelector("#enabledCount"),
  toggleAllButton: document.querySelector("#toggleAllButton"),
  exportButton: document.querySelector("#exportButton"),
  headerStatus: document.querySelector("#headerStatus"),
  toast: document.querySelector("#toast"),
};

let toastTimer;

function showToast(message) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.hidden = false;
  toastTimer = setTimeout(() => { elements.toast.hidden = true; }, 3200);
}

function markModified() {
  state.modified = true;
}

function confirmDiscard(action) {
  if (!state.modified) return true;
  return window.confirm(`${action}将清空当前已填写的名称和启停设置，确定继续？`);
}

function pushHistory() {
  state.undoStack.push({
    boxes: state.boxes.map((box) => ({ ...box })),
    items: state.items.map((item) => ({ ...item })),
  });
  if (state.undoStack.length > 50) state.undoStack.shift();
  state.redoStack.length = 0;
  updateUndoButtons();
}

function restoreHistory(snapshot) {
  state.boxes = snapshot.boxes;
  state.items = snapshot.items;
  state.selectedIndex = Math.max(0, Math.min(state.selectedIndex, state.boxes.length - 1));
  renderList();
  drawCanvas();
}

function undo() {
  if (!state.undoStack.length) return;
  state.redoStack.push({
    boxes: state.boxes.map((box) => ({ ...box })),
    items: state.items.map((item) => ({ ...item })),
  });
  restoreHistory(state.undoStack.pop());
  updateUndoButtons();
}

function redo() {
  if (!state.redoStack.length) return;
  state.undoStack.push({
    boxes: state.boxes.map((box) => ({ ...box })),
    items: state.items.map((item) => ({ ...item })),
  });
  restoreHistory(state.redoStack.pop());
  updateUndoButtons();
}

function updateUndoButtons() {
  elements.undoButton.disabled = state.undoStack.length === 0;
  elements.redoButton.disabled = state.redoStack.length === 0;
}

function openLightbox(index) {
  const item = state.items[index];
  if (!item || !state.sourceImage) return;
  const box = state.boxes[index];
  const canvas = document.createElement("canvas");
  canvas.width = 300;
  canvas.height = 300;
  canvas.getContext("2d").drawImage(state.sourceImage, box.x, box.y, box.size, box.size, 0, 0, 300, 300);
  elements.lightboxImg.src = canvas.toDataURL("image/png");
  elements.lightbox.hidden = false;
  elements.lightboxClose.focus();
}

function closeLightbox() {
  elements.lightbox.hidden = true;
  elements.lightboxImg.src = "";
}

async function apiError(response) {
  try {
    const body = await response.json();
    return body.detail || "操作失败，请重试";
  } catch {
    return "操作失败，请重试";
  }
}

function setBusy(busy) {
  elements.canvasLoading.hidden = !busy;
  elements.reanalyzeButton.disabled = busy;
  elements.exportButton.disabled = busy;
}

async function analyze(file = state.file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".png") && file.type !== "image/png") {
    showToast("请选择 PNG 图片");
    return;
  }
  state.file = file;
  setBusy(true);
  const form = new FormData();
  form.append("file", file);
  form.append("mode", state.mode);
  form.append("rows", elements.rowInput.value);
  form.append("columns", elements.columnInput.value);
  try {
    const response = await fetch("/api/analyze", { method: "POST", body: form });
    if (!response.ok) throw new Error(await apiError(response));
    const result = await response.json();
    state.sessionId = result.session_id;
    state.modified = false;
    state.undoStack.length = 0;
    state.redoStack.length = 0;
    updateUndoButtons();
    state.boxes = result.boxes;
    state.width = result.width;
    state.height = result.height;
    state.items = result.boxes.map((_, index) => ({ cropIndex: index, name: "表情", enabled: true }));
    elements.folderName.value = `${result.source_name}_表情包`;
    elements.sourceTitle.textContent = file.name;
    elements.imageMeta.textContent = `${result.width} × ${result.height}px`;
    elements.uploadView.hidden = true;
    elements.workspace.hidden = false;
    await loadSource();
    fitCanvas();
    renderList();
    elements.headerStatus.textContent = `已识别 ${result.boxes.length} 张表情`;
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(false);
  }
}

function loadSource() {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      state.sourceImage = image;
      drawCanvas();
      resolve();
    };
    image.onerror = () => reject(new Error("原图预览加载失败"));
    image.src = `/api/session/${state.sessionId}/source?t=${Date.now()}`;
  });
}

function drawCanvas() {
  if (!state.sourceImage) return;
  const canvas = elements.sourceCanvas;
  const context = canvas.getContext("2d");
  canvas.width = state.width;
  canvas.height = state.height;
  canvas.style.width = `${Math.round(state.width * state.zoom)}px`;
  canvas.style.height = `${Math.round(state.height * state.zoom)}px`;
  context.drawImage(state.sourceImage, 0, 0);
  const lineWidth = Math.max(2, Math.round(Math.min(state.width, state.height) / 300));
  context.lineWidth = lineWidth;
  context.font = `700 ${Math.max(13, lineWidth * 6)}px Inter, sans-serif`;
  state.boxes.forEach((box, index) => {
    const active = state.items[index]?.enabled !== false;
    const selected = index === state.selectedIndex && state.editMode;
    context.strokeStyle = selected ? "#125f91" : (active ? "#e85d3f" : "#777873");
    context.lineWidth = selected ? lineWidth * 2 : lineWidth;
    context.fillStyle = active ? "#e85d3f" : "#777873";
    context.strokeRect(box.x, box.y, box.size, box.size);
    const label = String(index + 1).padStart(2, "0");
    const labelWidth = context.measureText(label).width + lineWidth * 5;
    const labelHeight = Math.max(20, lineWidth * 9);
    context.fillRect(box.x, box.y, labelWidth, labelHeight);
    context.fillStyle = "white";
    context.fillText(label, box.x + lineWidth * 2, box.y + labelHeight - lineWidth * 2);
    if (selected) {
      context.fillStyle = "#125f91";
      context.fillRect(box.x + box.size - 12, box.y + box.size - 12, 12, 12);
    }
  });
}

function fitCanvas() {
  if (!state.sourceImage) return;
  const availableWidth = Math.max(240, elements.canvasStage.clientWidth - 28);
  const availableHeight = Math.max(200, elements.canvasStage.clientHeight - 28);
  state.zoom = Math.max(0.25, Math.min(2.2, Math.min(availableWidth / state.width, availableHeight / state.height)));
  elements.zoomInput.value = String(Math.round(state.zoom * 100));
  elements.zoomValue.textContent = `${Math.round(state.zoom * 100)}%`;
  drawCanvas();
  elements.canvasStage.scrollLeft = 0;
  elements.canvasStage.scrollTop = 0;
}

function setZoom(value) {
  state.zoom = Math.max(0.25, Math.min(2.2, Number(value) / 100));
  elements.zoomInput.value = String(Math.round(state.zoom * 100));
  elements.zoomValue.textContent = `${Math.round(state.zoom * 100)}%`;
  drawCanvas();
}

function canvasPoint(event) {
  const rect = elements.sourceCanvas.getBoundingClientRect();
  return {
    x: (event.clientX - rect.left) * state.width / rect.width,
    y: (event.clientY - rect.top) * state.height / rect.height,
  };
}

function boxAt(point) {
  for (let index = state.boxes.length - 1; index >= 0; index -= 1) {
    const box = state.boxes[index];
    if (point.x >= box.x && point.x <= box.x + box.size && point.y >= box.y && point.y <= box.y + box.size) return index;
  }
  return -1;
}

function refreshCropPreview(index) {
  const item = state.items[index];
  const image = document.querySelectorAll(".crop-thumb")[index];
  if (!item || !image || !state.sourceImage) return;
  const box = state.boxes[index];
  const preview = document.createElement("canvas");
  preview.width = 300;
  preview.height = 300;
  preview.getContext("2d").drawImage(state.sourceImage, box.x, box.y, box.size, box.size, 0, 0, 300, 300);
  image.src = preview.toDataURL("image/png");
}

function renderList() {
  elements.cropList.replaceChildren();
  state.items.forEach((item, index) => {
    const row = document.createElement("div");
    row.className = `crop-item${item.enabled ? "" : " disabled"}`;
    row.style.animationDelay = `${Math.min(index * 28, 240)}ms`;
    row.addEventListener("click", (event) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLImageElement) return;
      state.selectedIndex = index;
      drawCanvas();
    });

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = item.enabled;
    checkbox.setAttribute("aria-label", `保留第 ${index + 1} 张表情`);
    checkbox.addEventListener("change", () => {
      item.enabled = checkbox.checked;
      row.classList.toggle("disabled", !item.enabled);
      markModified();
      updateSummary();
      drawCanvas();
    });

    const image = document.createElement("img");
    image.className = "crop-thumb";
    image.alt = `第 ${index + 1} 张表情预览`;
    image.loading = "lazy";
    image.addEventListener("click", (event) => {
      event.stopPropagation();
      openLightbox(index);
    });

    const nameWrap = document.createElement("div");
    nameWrap.className = "name-wrap";
    const label = document.createElement("label");
    label.textContent = "表情名称（1–4 个汉字）";
    const input = document.createElement("input");
    input.className = "name-input";
    input.value = item.name;
    input.maxLength = 4;
    input.inputMode = "text";
    input.addEventListener("input", () => {
      item.name = input.value.trim();
      input.classList.toggle("invalid", !isValidName(item.name));
      markModified();
    });
    input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      const next = document.querySelectorAll(".name-input")[index + 1];
      if (next) next.focus();
      else input.blur();
    });
    nameWrap.append(label, input);

    const number = document.createElement("span");
    number.className = "item-number";
    number.dataset.itemNumber = index;
    row.append(checkbox, image, nameWrap, number);
    elements.cropList.append(row);
    refreshCropPreview(index);
  });
  updateSummary();
}

function isValidName(name) {
  return /^[\u4e00-\u9fff]{1,4}$/.test(name);
}

function safeDownloadName(name) {
  return name.replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").trim().replace(/[ .]+$/, "") || "表情包";
}

function updateSummary() {
  const enabled = state.items.filter((item) => item.enabled);
  elements.cropCount.textContent = state.items.length;
  elements.enabledCount.textContent = `${enabled.length} 张待导出`;
  elements.detectMeta.textContent = `${state.mode === "auto" ? "自动识别" : "规则网格"} · 1:1 裁切`;
  elements.toggleAllButton.textContent = enabled.length ? "全部停用" : "全部启用";
  let outputIndex = 0;
  state.items.forEach((item, index) => {
    const number = document.querySelector(`[data-item-number="${index}"]`);
    if (!number) return;
    if (!item.enabled) {
      number.textContent = "—";
      return;
    }
    outputIndex += 1;
    number.replaceChildren(document.createTextNode(`_${String(outputIndex).padStart(2, "0")}`));
    if (outputIndex === 1) {
      const badge = document.createElement("span");
      badge.className = "first-badge";
      badge.textContent = "200";
      badge.title = "额外生成 200×200 PNG";
      number.append(badge);
    }
  });
}

async function exportFiles() {
  const items = state.items.filter((item) => item.enabled);
  if (!items.length) return showToast("至少保留一张表情图片");
  const invalid = items.find((item) => !isValidName(item.name));
  if (invalid) return showToast("表情名称只能填写 1 到 4 个汉字");
  const folderName = elements.folderName.value.trim();
  if (!folderName) return showToast("请填写大文件夹名称");

  elements.exportButton.disabled = true;
  elements.exportButton.querySelector("span").textContent = "正在打包";
  try {
    const response = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.sessionId,
        folder_name: folderName,
        items: items.map((item) => ({ crop_index: item.cropIndex, name: item.name, box: state.boxes[item.cropIndex] })),
      }),
    });
    if (!response.ok) throw new Error(await apiError(response));
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${safeDownloadName(folderName)}.zip`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    showToast("文件夹已打包完成");
  } catch (error) {
    showToast(error.message);
  } finally {
    elements.exportButton.disabled = false;
    elements.exportButton.querySelector("span").textContent = "下载文件夹";
  }
}

elements.dropZone.addEventListener("click", () => elements.fileInput.click());
elements.replaceButton.addEventListener("click", () => {
  if (confirmDiscard("换一张")) elements.fileInput.click();
});
elements.fileInput.addEventListener("change", () => analyze(elements.fileInput.files[0]));
elements.reanalyzeButton.addEventListener("click", () => {
  if (confirmDiscard("重新识别")) analyze();
});
elements.exportButton.addEventListener("click", exportFiles);
elements.editModeButton.addEventListener("click", () => {
  state.editMode = !state.editMode;
  elements.editModeButton.setAttribute("aria-pressed", String(state.editMode));
  elements.editModeButton.classList.toggle("active", state.editMode);
  elements.sourceCanvas.classList.toggle("editing", state.editMode);
  elements.editHint.hidden = !state.editMode;
  document.querySelectorAll(".edit-only").forEach((element) => { element.hidden = !state.editMode; });
  updateUndoButtons();
  drawCanvas();
});
elements.addBoxButton.addEventListener("click", () => {
  pushHistory();
  const size = Math.max(40, Math.round(Math.min(state.width, state.height) * 0.25));
  state.boxes.push({ x: Math.round((state.width - size) / 2), y: Math.round((state.height - size) / 2), size });
  state.items.push({ cropIndex: state.items.length, name: "表情", enabled: true });
  state.selectedIndex = state.boxes.length - 1;
  markModified();
  renderList();
  drawCanvas();
});
elements.deleteBoxButton.addEventListener("click", () => {
  if (!state.boxes.length) return;
  pushHistory();
  state.boxes.splice(state.selectedIndex, 1);
  state.items.splice(state.selectedIndex, 1);
  state.items.forEach((item, index) => { item.cropIndex = index; });
  state.selectedIndex = Math.max(0, Math.min(state.selectedIndex, state.boxes.length - 1));
  markModified();
  renderList();
  drawCanvas();
});
elements.undoButton.addEventListener("click", undo);
elements.redoButton.addEventListener("click", redo);
elements.bulkApplyButton.addEventListener("click", () => {
  const name = elements.bulkName.value.trim();
  if (!isValidName(name)) return showToast("名称只能填写 1 到 4 个汉字");
  let applied = 0;
  state.items.forEach((item) => {
    if (!item.enabled) return;
    item.name = name;
    applied += 1;
  });
  if (!applied) return showToast("至少保留一张表情图片");
  markModified();
  renderList();
  showToast(`已为 ${applied} 张表情命名`);
});
elements.bulkName.addEventListener("keydown", (event) => {
  if (event.key === "Enter") elements.bulkApplyButton.click();
});
elements.lightboxClose.addEventListener("click", closeLightbox);
elements.lightbox.addEventListener("click", (event) => {
  if (event.target === elements.lightbox) closeLightbox();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !elements.lightbox.hidden) {
    closeLightbox();
    return;
  }
  if (!(event.ctrlKey || event.metaKey)) return;
  const key = event.key.toLowerCase();
  if (key === "z" && !event.shiftKey) {
    event.preventDefault();
    undo();
  } else if (key === "y" || (key === "z" && event.shiftKey)) {
    event.preventDefault();
    redo();
  }
});
elements.fitButton.addEventListener("click", fitCanvas);
elements.zoomInput.addEventListener("input", () => setZoom(elements.zoomInput.value));
elements.folderName.addEventListener("input", markModified);
elements.toggleAllButton.addEventListener("click", () => {
  const shouldEnable = !state.items.some((item) => item.enabled);
  state.items.forEach((item) => { item.enabled = shouldEnable; });
  markModified();
  renderList();
  drawCanvas();
});

document.querySelectorAll("[data-mode]").forEach((button) => {
  button.addEventListener("click", () => {
    state.mode = button.dataset.mode;
    document.querySelectorAll("[data-mode]").forEach((candidate) => candidate.classList.toggle("active", candidate === button));
    elements.gridFields.hidden = state.mode !== "grid";
  });
});

["dragenter", "dragover"].forEach((eventName) => {
  elements.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropZone.classList.add("dragging");
  });
});
["dragleave", "drop"].forEach((eventName) => {
  elements.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropZone.classList.remove("dragging");
  });
});
elements.dropZone.addEventListener("drop", (event) => analyze(event.dataTransfer.files[0]));
elements.sourceCanvas.addEventListener("pointerdown", (event) => {
  if (!state.editMode) return;
  const point = canvasPoint(event);
  const index = boxAt(point);
  if (index < 0) return;
  state.selectedIndex = index;
  const box = state.boxes[index];
  const handleDistance = Math.max(18, 22 / state.zoom);
  const onHandle = Math.abs(point.x - (box.x + box.size)) < handleDistance && Math.abs(point.y - (box.y + box.size)) < handleDistance;
  state.pointerAction = { index, type: onHandle ? "resize" : "move", start: point, box: { ...box } };
  elements.sourceCanvas.setPointerCapture(event.pointerId);
  drawCanvas();
});
elements.sourceCanvas.addEventListener("pointermove", (event) => {
  const action = state.pointerAction;
  if (!action) return;
  const point = canvasPoint(event);
  const dx = point.x - action.start.x;
  const dy = point.y - action.start.y;
  if (action.type === "move") {
    state.boxes[action.index] = {
      x: Math.max(0, Math.min(Math.round(action.box.x + dx), state.width - action.box.size)),
      y: Math.max(0, Math.min(Math.round(action.box.y + dy), state.height - action.box.size)),
      size: action.box.size,
    };
  } else {
    const maxSize = Math.min(state.width - action.box.x, state.height - action.box.y);
    const size = Math.max(20, Math.min(maxSize, Math.round(action.box.size + Math.max(dx, dy))));
    state.boxes[action.index] = { x: action.box.x, y: action.box.y, size };
  }
  drawCanvas();
});
elements.sourceCanvas.addEventListener("pointerup", (event) => {
  if (!state.pointerAction) return;
  const index = state.pointerAction.index;
  state.pointerAction = null;
  elements.sourceCanvas.releasePointerCapture?.(event.pointerId);
  pushHistory();
  markModified();
  refreshCropPreview(index);
});
elements.sourceCanvas.addEventListener("pointercancel", () => { state.pointerAction = null; });
window.addEventListener("resize", () => { if (state.sourceImage) fitCanvas(); });
window.addEventListener("load", () => { if (window.lucide) window.lucide.createIcons(); });
