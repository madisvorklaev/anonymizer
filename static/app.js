// ---- tabs ----
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("panel-" + btn.dataset.tab).classList.add("active");
  });
});

// ---- anonymize state ----
let docId = null;
let pageCount = 0;
let currentPage = 0;
let scale = 1; // canvas px per pdf point, for the currently loaded page
let regionsByPage = {}; // { pageIndex: [{x0,y0,x1,y1} in pdf points] }
let dragStart = null;
let currentImage = null;

const canvas = document.getElementById("pdfCanvas");
const ctx = canvas.getContext("2d");
const anonStatus = document.getElementById("anonStatus");

function setStatus(el, msg, kind) {
  el.textContent = msg || "";
  el.className = "status" + (kind ? " " + kind : "");
}

function totalRegions() {
  return Object.values(regionsByPage).reduce((sum, arr) => sum + arr.length, 0);
}

function updateCounter() {
  document.getElementById("regionCounter").textContent = totalRegions() + " region(s) selected";
  document.getElementById("anonymizeRow").style.display = totalRegions() > 0 ? "flex" : "none";
}

document.getElementById("fileInput").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  setStatus(anonStatus, "Uploading...", "");
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch("/api/upload", { method: "POST", body: fd });
    if (!res.ok) throw new Error((await res.json()).detail || "Upload failed");
    const data = await res.json();
    docId = data.doc_id;
    pageCount = data.page_count;
    currentPage = 0;
    regionsByPage = {};
    document.getElementById("pageControls").style.display = "flex";
    document.getElementById("canvasWrap").style.display = "inline-block";
    updateCounter();
    await loadPage(currentPage);
    setStatus(anonStatus, "Loaded \"" + data.filename + "\" (" + pageCount + " page" + (pageCount > 1 ? "s" : "") + ").", "ok");
  } catch (err) {
    setStatus(anonStatus, String(err.message || err), "error");
  }
});

async function loadPage(n) {
  const res = await fetch(`/api/page/${docId}/${n}`);
  if (!res.ok) throw new Error("Could not load page");
  const pageWidthPts = parseFloat(res.headers.get("X-Page-Width-Pts"));
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  await new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      currentImage = img;
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      scale = img.naturalWidth / pageWidthPts;
      redraw();
      URL.revokeObjectURL(url);
      resolve();
    };
    img.onerror = reject;
    img.src = url;
  });
  document.getElementById("pageLabel").textContent = `Page ${n + 1} / ${pageCount}`;
  document.getElementById("prevPage").disabled = n === 0;
  document.getElementById("nextPage").disabled = n === pageCount - 1;
}

function redraw(previewRect) {
  if (!currentImage) return;
  ctx.drawImage(currentImage, 0, 0);
  ctx.lineWidth = 2;
  ctx.strokeStyle = "#dc2626";
  ctx.fillStyle = "rgba(220, 38, 38, 0.15)";
  const boxes = regionsByPage[currentPage] || [];
  for (const r of boxes) {
    const x = r.x0 * scale, y = r.y0 * scale;
    const w = (r.x1 - r.x0) * scale, h = (r.y1 - r.y0) * scale;
    ctx.fillRect(x, y, w, h);
    ctx.strokeRect(x, y, w, h);
  }
  if (previewRect) {
    ctx.strokeStyle = "#2563eb";
    ctx.fillStyle = "rgba(37, 99, 235, 0.15)";
    ctx.fillRect(previewRect.x, previewRect.y, previewRect.w, previewRect.h);
    ctx.strokeRect(previewRect.x, previewRect.y, previewRect.w, previewRect.h);
  }
}

canvas.addEventListener("mousedown", (e) => {
  const rect = canvas.getBoundingClientRect();
  dragStart = { x: e.clientX - rect.left, y: e.clientY - rect.top };
});

canvas.addEventListener("mousemove", (e) => {
  if (!dragStart) return;
  const rect = canvas.getBoundingClientRect();
  const cur = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  const x = Math.min(dragStart.x, cur.x), y = Math.min(dragStart.y, cur.y);
  const w = Math.abs(cur.x - dragStart.x), h = Math.abs(cur.y - dragStart.y);
  redraw({ x, y, w, h });
});

window.addEventListener("mouseup", (e) => {
  if (!dragStart) return;
  const rect = canvas.getBoundingClientRect();
  const cur = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  dragStart = { x: Math.max(0, Math.min(canvas.width, dragStart.x)), y: Math.max(0, Math.min(canvas.height, dragStart.y)) };
  const clampedCur = { x: Math.max(0, Math.min(canvas.width, cur.x)), y: Math.max(0, Math.min(canvas.height, cur.y)) };

  const x0px = Math.min(dragStart.x, clampedCur.x), x1px = Math.max(dragStart.x, clampedCur.x);
  const y0px = Math.min(dragStart.y, clampedCur.y), y1px = Math.max(dragStart.y, clampedCur.y);
  dragStart = null;

  if (x1px - x0px < 4 || y1px - y0px < 4) {
    redraw();
    return; // too small, ignore accidental click
  }
  const region = { x0: x0px / scale, y0: y0px / scale, x1: x1px / scale, y1: y1px / scale };
  if (!regionsByPage[currentPage]) regionsByPage[currentPage] = [];
  regionsByPage[currentPage].push(region);
  updateCounter();
  redraw();
});

document.getElementById("prevPage").addEventListener("click", async () => {
  if (currentPage > 0) { currentPage--; await loadPage(currentPage); }
});
document.getElementById("nextPage").addEventListener("click", async () => {
  if (currentPage < pageCount - 1) { currentPage++; await loadPage(currentPage); }
});
document.getElementById("undoBox").addEventListener("click", () => {
  const boxes = regionsByPage[currentPage];
  if (boxes && boxes.length) boxes.pop();
  updateCounter();
  redraw();
});
document.getElementById("clearPageBoxes").addEventListener("click", () => {
  regionsByPage[currentPage] = [];
  updateCounter();
  redraw();
});

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

document.getElementById("anonymizeBtn").addEventListener("click", async () => {
  const regions = [];
  for (const [page, boxes] of Object.entries(regionsByPage)) {
    for (const b of boxes) regions.push({ page: parseInt(page, 10), ...b });
  }
  if (!regions.length) return;
  setStatus(anonStatus, "Anonymizing...", "");
  try {
    const res = await fetch("/api/anonymize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_id: docId, regions }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Anonymize failed");
    const blob = await res.blob();
    downloadBlob(blob, "anonymized.pdf");
    setStatus(anonStatus, "Done. Downloaded anonymized.pdf", "ok");
  } catch (err) {
    setStatus(anonStatus, String(err.message || err), "error");
  }
});

// ---- restore ----
const restoreStatus = document.getElementById("restoreStatus");
document.getElementById("restoreBtn").addEventListener("click", async () => {
  const file = document.getElementById("restoreInput").files[0];
  if (!file) { setStatus(restoreStatus, "Choose a PDF first.", "error"); return; }
  setStatus(restoreStatus, "Restoring...", "");
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch("/api/restore", { method: "POST", body: fd });
    if (!res.ok) throw new Error((await res.json()).detail || "Restore failed");
    const blob = await res.blob();
    downloadBlob(blob, "restored.pdf");
    setStatus(restoreStatus, "Done. Downloaded restored.pdf", "ok");
  } catch (err) {
    setStatus(restoreStatus, String(err.message || err), "error");
  }
});
