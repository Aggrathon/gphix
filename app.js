// ── Event system ──────────────────────────────────────────────────────
const _listeners = new Map();

function on(event, fn) {
  const list = _listeners.get(event);
  if (list) list.push(fn);
  else _listeners.set(event, [fn]);
}

function emit(event, data) {
  for (const fn of _listeners.get(event) ?? []) {
    try {
      fn(data);
    } catch (err) {
      console.error(`[${event}]`, err);
    }
  }
}

// ── Helpers ───────────────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);

function showLoading(message = "Loading…") {
  const el = $("#loading");
  el.classList.remove("hidden");
  $("#loading-message").textContent = message;
}

function hideLoading() {
  $("#loading").classList.add("hidden");
}

const container = $("#toasts");
function showToast(msg) {
  const el = document.createElement("div");
  el.className = "toast";
  el.setAttribute("role", "status");
  el.textContent = msg;
  container.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));
  el.addEventListener("click", () => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 150);
  });
}

function escHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

// ── Pyodide init ─────────────────────────────────────────────────────
let pyodide = null;
async function setupPyodide() {
  try {
    showLoading("Loading engine…");
    const py = await loadPyodide();
    py.FS.mkdirTree("/gphix");
    py.FS.writeFile("/gphix/__init__.py", '"""GPX file toolbox."""');
    for (const f of ["utils.py", "gpx.py", "web.py"]) {
      const resp = await fetch("src/gphix/" + f);
      py.FS.writeFile("/gphix/" + f, await resp.text());
    }
    await py.runPythonAsync(`
import sys
sys.path.append("/")
from gphix import web
from pyodide.ffi import to_js
    `);
    pyodide = py;
  } catch (err) {
    showToast("Failed to load Pyodide: " + err.message);
    console.error(err);
  } finally {
    hideLoading();
  }
}

// ── Load GPX → emit ─────────────────────────────────────────────────
async function handleFiles(files) {
  if (!pyodide || files.length == 0) return;
  showLoading("Processing GPX…");
  try {
    let paths = [];
    for (const file of files) {
      const bytes = new Uint8Array(await file.arrayBuffer());
      pyodide.FS.writeFile(`/tmp/` + file.name, bytes);
      paths.push(file.name);
    }
    await pyodide.runPythonAsync(
      `web.load_gpx("/tmp", ${pyodide.toPy(paths)})`,
    );
    for (const path of paths) {
      pyodide.FS.unlink(`/tmp/` + path);
    }
    emit("state_changed", true);
  } catch (err) {
    showToast("Failed to parse GPX: " + err.message);
    console.error(err);
  } finally {
    hideLoading();
  }
}

// ── Stats ────────────────────────────────────────────────────────
async function renderStats(_) {
  if (!pyodide) return;
  const el = $("#gpx-info");
  const lines = [];
  const s = (label, value) =>
    `<div class="stat"><span>${label}</span><span>${value}</span></div>`;

  const metadata = await pyodide.runPythonAsync("to_js(web.get_metadata())");
  if (metadata?.name) {
    lines.push(s("Name", escHtml(metadata.name)));
    el.innerHTML = lines[0];
  }

  const stats = await pyodide.runPythonAsync("to_js(web.get_stats())");
  for (const label in stats) lines.push(s(label, stats[label]));
  if (lines.length == 0) el.innerHTML = "Load a file to see info";
  else el.innerHTML = lines.join("");
}

// ── Charts ────────────────────────────────────────────────────────
function drawPlaceholder(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.fillStyle = "#fdfdfd";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#888";
  ctx.font = "12px system-ui";
  ctx.textAlign = "center";
  ctx.fillText(
    "Load a GPX file to see chart",
    canvas.width / 2 / dpr,
    canvas.height / 2 / dpr,
  );
}

async function renderCharts(_) {
  for (const id of ["#chart-elev", "#chart-time-dist", "#chart-time-elev"])
    drawPlaceholder($(id));
  return;
}

// ── Map ──────────────────────────────────────────────────────────────
let map = null;
function setupMap() {
  map = L.map("map", { preferCanvas: true }).setView([0, 0], 2);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution:
      '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
}

let mapGpxLayers = [];
let selectedMarker = null;

async function renderMap(_) {
  if (!map) return;
  for (const layer of mapGpxLayers) {
    map.removeLayer(layer);
  }
  mapGpxLayers = [];

  if (!pyodide) return;
  const segments = await pyodide.runPythonAsync("to_js(web.get_segments())");
  if (segments.length == 0) {
    map.setView([0, 0], 2);
    return;
  }

  let bounds = [];
  for (let s = 0; s < segments.length; s++) {
    const coords = segments[s];
    const trackLayer = L.polyline(coords, {
      color: "#968068",
      weight: 3,
    }).addTo(map);
    mapGpxLayers.push(trackLayer);
    bounds.push(trackLayer.getBounds());
    for (let i = 0; i < coords.length; i++) {
      const marker = L.circleMarker(coords[i], {
        radius: 3,
        color: "#16a34a",
        fillOpacity: 0.6,
      }).addTo(map);
      marker.on("click", () => emit("point_selected", [s, i]));
      mapGpxLayers.push(marker);
    }
  }
  map.fitBounds(L.latLngBounds(bounds).pad(0.1));
}

async function onSelectedPointMap(idx) {
  if (selectedMarker) {
    map.removeLayer(selectedMarker);
    selectedMarker = null;
  }
  if (idx) {
    const [seg, pt] = idx;
    const point = await pyodide.runPythonAsync(
      `to_js(web.get_point(${seg},${pt}))`,
    );
    selectedMarker = L.circleMarker([point.lat, point.lon], {
      radius: 6,
      color: "#dc2626",
      fillOpacity: 1,
    });
    selectedMarker.on("click", () => emit("point_selected", null));
    selectedMarker.addTo(map);
  }
}

async function onSelectedPointStats(idx) {
  const el = $("#selected-point");
  if (!idx) {
    el.innerHTML = '<span class="muted">Click on a point to see info</span>';
    return;
  }
  const [seg, pt] = idx;
  const point = await pyodide.runPythonAsync(
    `to_js(web.get_point(${seg},${pt}))`,
  );
  const s = (label, value) =>
    `<div class="stat"><span>${label}</span><span>${value}</span></div>`;
  el.innerHTML = [
    s("Latitude", point.lat.toFixed(5)),
    s("Longitude", point.lon.toFixed(5)),
    s(
      "Elevation",
      (point.ele != null ? point.ele.toFixed(1) : "\u2014") + " m",
    ),
    s("Time", point.time || "\u2014"),
    s("Segment", seg + 1),
    s("Point", pt + 1),
  ].join("");
}

// ── Tab switching ────────────────────────────────────────────────────
function setupTabs() {
  const tabButtons = document.querySelectorAll("#tabs > button");
  const tabContents = document.querySelectorAll(".tab-content");

  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabButtons.forEach((b) => b.classList.remove("active"));
      tabContents.forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      const target = $(`.tab-content[data-tab="${btn.dataset.tab}"]`);
      if (target) target.classList.add("active");
      setTimeout(() => map.invalidateSize(), 100);
    });
  });
}

// ── File list ────────────────────────────────────────────────────────
async function updateFileList(_) {
  if (!pyodide) return;
  const list = $("#file-list");
  list.innerHTML += "Processing GPX files...";
  const files = await pyodide.runPythonAsync("to_js(web.get_files())");
  if (files.length == 1) list.innerHTML = "<h3>Current GPX File</h3>";
  else if (files.length > 0) list.innerHTML = "<h3>Merged GPX Files</h3>";
  else list.innerHTML = "<h3>No files loaded</h3>";
  for (const f of files) {
    const li = document.createElement("li");
    li.textContent = f;
    list.appendChild(li);
  }
}

// ── File drop ────────────────────────────────────────────────────────
function setupFileDrop() {
  const dropZone = $(".drop-zone");
  const fileInput = $("#file-input");

  dropZone.addEventListener("click", () => fileInput.click());
  dropZone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });
  fileInput.addEventListener("change", () => {
    handleFiles(fileInput.files);
    fileInput.value = "";
  });

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });
  dropZone.addEventListener("dragleave", () =>
    dropZone.classList.remove("dragover"),
  );
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    handleFiles(e.dataTransfer.files);
  });
}

// ── Sliders ─────────────────────────────────────────────────────
function setupSliders() {
  const sliders = ["#trim-start", "#trim-end"];
  for (const id of sliders) {
    const slider = $(id);
    const output = $(id + "-value");
    slider.addEventListener("input", () => {
      output.textContent = `${slider.value}%`;
    });
    slider.value = 0;
  }
}

// ── State and File buttons ───────────────────────────────────────────
function setupButtons() {
  async function onUndoClick() {
    if (!pyodide) return;
    const hasGpx = await pyodide.runPythonAsync("to_js(web.undo())");
    emit("state_changed", hasGpx);
  }

  async function onResetClick() {
    if (!pyodide) return;
    await pyodide.runPythonAsync("web.reset()");
    emit("state_changed", false);
  }

  async function onFirstClick() {
    if (!pyodide) return;
    const point = await pyodide.runPythonAsync("to_js(web.get_point_idx(0))");
    emit("point_selected", point);
    if (point) $("#btn-first").disabled = true;
  }

  async function onLastClick() {
    if (!pyodide) return;
    const point = await pyodide.runPythonAsync("to_js(web.get_point_idx(-1))");
    emit("point_selected", point);
    if (point) $("#btn-last").disabled = true;
  }

  $("#btn-save").addEventListener("click", () =>
    showToast("Save — not implemented yet"),
  );
  $("#btn-undo").addEventListener("click", onUndoClick);
  $("#btn-reset").addEventListener("click", onResetClick);
  $("#btn-first").addEventListener("click", onFirstClick);
  $("#btn-last").addEventListener("click", onLastClick);
}

function showPointSelection(show) {
  if (show) $("#select-point").classList.remove("hidden");
  else $("#select-point").classList.add("hidden");
}

function enablePointSelection(_) {
  $("#btn-first").disabled = false;
  $("#btn-last").disabled = false;
}

// ── Init ─────────────────────────────────────────────────────────────
setupTabs();
setupFileDrop();
setupSliders();
setupButtons();
setupMap();
setupPyodide();
renderCharts(null);

on("state_changed", updateFileList);
on("state_changed", renderStats);
on("state_changed", renderMap);
on("state_changed", renderCharts);
on("state_changed", showPointSelection);
on("state_changed", (_) => emit("point_selected", null));
on("point_selected", onSelectedPointMap);
on("point_selected", onSelectedPointStats);
on("point_selected", enablePointSelection);
