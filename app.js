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
  const el = document.getElementById("loading");
  el.classList.remove("hidden");
  document.getElementById("loading-message").textContent = message;
}

function hideLoading() {
  document.getElementById("loading").classList.add("hidden");
}

const container = document.getElementById("toasts");
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
    emit("state_changed", null);
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
  const el = document.getElementById("gpx-info");
  const lines = [];
  const s = (label, value) =>
    `<div class="stat"><span>${label}</span><span>${value}</span></div>`;

  const metadata = await pyodide.runPythonAsync("to_js(web.get_metadata())");
  if (metadata?.name) {
    lines.push(s("Name", escHtml(metadata.name)));
    el.innerHTML = lines[0];
  }

  const stats = await pyodide.runPythonAsync("to_js(web.get_stats())");
  for (const [label, info] of stats) {
    lines.push(s(label, info));
  }
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
  map = L.map("map").setView([0, 0], 2);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution:
      '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
}

let mapGpxLayers = [];
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
  for (const points of segments) {
    const coords = points.map((p) => [p.lat, p.lon]);
    const trackLayer = L.polyline(coords, {
      color: "#968068",
      weight: 3,
    }).addTo(map);
    const pointMarkers = L.layerGroup(
      points.map((p) =>
        L.circleMarker([p.lat, p.lon], {
          radius: 3,
          color: "#16a34a",
          fillOpacity: 0.6,
        }),
      ),
    ).addTo(map);
    bounds.push(trackLayer.getBounds().pad(0.1));
    mapGpxLayers.push(trackLayer);
    mapGpxLayers.push(pointMarkers);
  }
  map.fitBounds(L.latLngBounds(bounds));
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
      const target = document.querySelector(
        `.tab-content[data-tab="${btn.dataset.tab}"]`,
      );
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
    await pyodide.runPythonAsync("web.undo()");
    emit("state_changed", null);
  }

  async function onResetClick() {
    if (!pyodide) return;
    await pyodide.runPythonAsync("web.reset()");
    emit("state_changed", null);
  }

  $("#btn-save").addEventListener("click", () =>
    showToast("Save — not implemented yet"),
  );
  $("#btn-undo").addEventListener("click", onUndoClick);
  $("#btn-reset").addEventListener("click", onResetClick);
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
