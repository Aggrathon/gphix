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
let selectedPoint = null;

function showLoading(message = "Loading…") {
  $("#loading").hidden = false;
  $("#loading-message").textContent = message;
}

function hideLoading() {
  $("#loading").hidden = true;
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

function formatDistance(val) {
  if (val < 1000) return val.toFixed(1) + " m";
  return (val / 1000).toFixed(2) + " km";
}

function formatLocalTime(time) {
  return new Date(time.getTime() - time.getTimezoneOffset() * 60 * 1000)
    .toISOString()
    .slice(0, 19)
}

// ── Pyodide ─────────────────────────────────────────────────────
let pyodide = null;
async function setupPyodide() {
  try {
    showLoading("Loading engine…");
    const py = await loadPyodide();
    py.FS.mkdirTree("/gphix");
    py.FS.writeFile("/gphix/__init__.py", '"""GPX file toolbox."""');
    for (const f of ["utils.py", "gpx.py", "web.py", "trim.py"]) {
      const resp = await fetch("src/gphix/" + f);
      py.FS.writeFile("/gphix/" + f, await resp.text());
    }
    await py.runPythonAsync(`
import sys
sys.path.append("/")
from gphix.web import *
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

async function selectPoint(seg, idx) {
  const point = await pyodide.runPythonAsync(`to_js(get_point(${seg},${idx}))`);
  emit("point_selected", point);
}

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
    await pyodide.runPythonAsync(`load_gpx("/tmp", ${pyodide.toPy(paths)})`);
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
function setupStats() {
  $("#btn-first").addEventListener("click", () => selectPoint(0, ""));
  $("#btn-last").addEventListener("click", async () => {
    await selectPoint(-1, "");
    $("#btn-last").disabled = true;
  });

  on("state_changed", onShowStats);
  on("state_changed", (show) => ($("#select-point").hidden = !show));
  on("point_selected", onSelectedPointStats);
  on("point_selected", enablePointSelection);
}

async function onShowStats(hasGpx) {
  const el = $("#gpx-info");
  if (!hasGpx || !pyodide) {
    el.innerHTML = "Load a file to see info";
    return;
  }
  const lines = [];
  const s = (label, value) =>
    `<div class="stat"><span>${label}</span><span>${value}</span></div>`;

  const metadata = await pyodide.runPythonAsync("to_js(get_metadata())");
  if (metadata?.name) {
    lines.push(s("Name", escHtml(metadata.name)));
    el.innerHTML = lines[0];
  }

  const stats = await pyodide.runPythonAsync("to_js(get_stats())");
  for (const label in stats) {
    if (label == "Start" || label == "End")
      lines.push(s(label, new Date(stats[label]).toLocaleString()));
    else lines.push(s(label, stats[label]));
  }
  if (lines.length == 0) el.innerHTML = "Load a file to see info";
  else el.innerHTML = lines.join("");
}

async function onSelectedPointStats(point) {
  const el = $("#selected-point");
  if (!point) {
    el.innerHTML = '<span class="muted">Click on a point to see info</span>';
    return;
  }
  const s = (label, value) =>
    `<div class="stat"><span>${label}</span><span>${value}</span></div>`;
  el.innerHTML = [
    s("Latitude", point.lat.toFixed(5)),
    s("Longitude", point.lon.toFixed(5)),
    s("Distance", formatDistance(point.dist)),
    s("Elevation", point.ele != null ? point.ele.toFixed(1) + " m" : "N/A"),
    s("Time", point.time ? new Date(point.time).toLocaleString() : "N/A"),
    s("Segment", point.seg + 1),
    s("Point", point.idx + 1),
  ].join("");
}

function enablePointSelection(point) {
  $("#btn-first").disabled = point && point.seg == 0 && point.idx == 0;
  $("#btn-last").disabled = false;
}

// ── Plots ────────────────────────────────────────────────────────
let tdPlot = null;
let edPlot = null;
let sdPlot = null;

function setupPlots() {
  function getSize(el) {
    return {
      width: el.offsetWidth,
      height: el.offsetHeight - 25,
    };
  }
  function fmtDistAx(self, ticks) {
    if (!ticks) return ticks;
    if (ticks[ticks.length - 1] < 1000) return ticks.map((val) => val + " m");
    return ticks.map((val) => val / 1000 + " km");
  }
  function onClick(u) {
    u.over.addEventListener("click", (e) => {
      if (u.cursor.idx) selectPoint(u.cursor.idx, "");
    });
  }
  function plot(id, time, yseries) {
    const el = $(id);
    let ax2 = {};
    if (time)
      ax2.values = [
        [3600 * 24 * 28, "{MMM}", "\n{YYYY}"],
        [3600 * 24, "{DD}/{MM}", "\n{YYYY}"],
        [60, "{HH}:{mm}", "\n{DD}/{MM}"],
        [1, "{ss}", "\n{HH}:{mm}\n{DD}/{MM}"],
      ];
    const opts = {
      ...getSize(el),
      cursor: { sync: { key: 0, setSeries: true } },
      axes: [{ values: fmtDistAx }, ax2],
      scales: { x: { time: false }, y: { time: time } },
      series: [
        {
          label: "Distance",
          value: (_, v) => (v != null ? formatDistance(v) : ""),
        },
        { ...yseries, spanGaps: false, stroke: "#16a34a", width: 2 },
      ],
      hooks: { init: [onClick] },
    };
    return new uPlot(opts, [[], []], el);
  }

  tdPlot = plot("#plot-time-dist", true, {
    value: (_, v) => (v == null ? "" : new Date(v * 1000).toLocaleTimeString()),
  });
  edPlot = plot("#plot-elev-dist", false, {
    label: "Elevation",
    value: (_, v) => (v == null ? "" : v.toFixed(1) + " m"),
  });

  on("resize", async (_) => {
    await tdPlot.setSize(getSize($("#plot-time-dist")));
    await edPlot.setSize(getSize($("#plot-elev-dist")));
    if (sdPlot != null) drawPlotPoint(sdPlot);
  });
  on("state_changed", renderPlots);
  on("point_selected", onSelectedPointPlot);
}

function drawPlotPoint(idx) {
  if (idx >= tdPlot.data[0].length) return;
  for (const plt of [tdPlot, edPlot]) {
    const x = plt.valToPos(plt.data[0][idx], "x", plt.ctx);
    const y = plt.valToPos(plt.data[1][idx], "y", plt.ctx);
    if (y == Infinity) continue;
    plt.ctx.beginPath();
    plt.ctx.arc(x, y, 5, 0, 2 * Math.PI);
    plt.ctx.fillStyle = "#dc2626";
    plt.ctx.fill();
  }
  sdPlot = idx;
}

async function onSelectedPointPlot(point) {
  if (sdPlot != null) {
    sdPlot = null;
    await tdPlot.redraw();
    await edPlot.redraw();
  }
  if (point && tdPlot) {
    drawPlotPoint(tdPlot.valToIdx(point.dist));
  }
}

async function renderPlots(hasGpx) {
  let data;
  if (hasGpx && pyodide)
    data = await pyodide.runPythonAsync("to_js(get_plot_data())");
  if (!data) data = [[], [], []];
  sdPlot = null;
  tdPlot.setData([data[0], data[1]]);
  edPlot.setData([data[0], data[2]]);
}

// ── Map ──────────────────────────────────────────────────────────────
let map = null;
function setupMap() {
  map = L.map("map", { preferCanvas: true }).setView([0, 0], 2);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution:
      '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  on("resize", (_) => setTimeout(map.invalidateSize, 100));
  on("state_changed", renderMap);
  on("point_selected", onSelectedPointMap);
  on("points_preview", onPreviewPointMap);
  map.on("click", async (e) => emit("map_clicked", e.latlng));
}

let mapGpxLayers = [];
let selectedMarker = null;
let mapPreviewLayer = null;

async function renderMap(hasGpx) {
  if (!map) return;
  for (const layer of mapGpxLayers) {
    map.removeLayer(layer);
  }
  mapGpxLayers = [];

  if (!hasGpx || !pyodide) return;
  const segments = await pyodide.runPythonAsync("to_js(get_segments())");
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
        radius: 2,
        color: "#16a34a",
        fillOpacity: 0.6,
      }).addTo(map);
      marker.on("click", () => selectPoint(s, i));
      mapGpxLayers.push(marker);
    }
  }
  map.fitBounds(L.latLngBounds(bounds).pad(0.1));
}

async function onSelectedPointMap(point) {
  if (selectedMarker) {
    map.removeLayer(selectedMarker);
    selectedMarker = null;
  }
  if (point) {
    selectedMarker = L.circleMarker([point.lat, point.lon], {
      radius: 6,
      color: "#dc2626",
      fillOpacity: 1,
    });
    selectedMarker.on("click", () => emit("point_selected", null));
    selectedMarker.addTo(map);
  }
}

function onPreviewPointMap(points) {
  if (mapPreviewLayer) {
    map.removeLayer(mapPreviewLayer);
    mapPreviewLayer = null;
  }
  if (points && points.length > 0) {
    if (points.length == 1)
      mapPreviewLayer = L.circleMarker(points[0], {
        color: "#7C1BD1",
        radius: 6,
        fillOpacity: 1,
      });
    else mapPreviewLayer = L.polyline(points, { color: "#7C1BD1", weight: 5 });
    mapPreviewLayer.addTo(map);
  }
}

// ── Tab switching ────────────────────────────────────────────────────
function setupTabs() {
  const tabButtons = document.querySelectorAll("#tabs > button");
  const tabContents = document.querySelectorAll(".tab-content");

  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabButtons.forEach((b) => (b.ariaSelected = false));
      tabContents.forEach((c) => (c.hidden = true));
      btn.ariaSelected = true;
      const target = $(`.tab-content[data-tab="${btn.dataset.tab}"]`);
      if (target) target.hidden = false;
      emit("resize", null);
    });
  });
}

// ── Files ────────────────────────────────────────────────────────
async function updateFileList(hasGpx) {
  const list = $("#file-list");
  if (!hasGpx || !pyodide) {
    list.innerHTML = "<h3>No files loaded</h3>";
    return;
  }
  list.innerHTML += "Processing GPX files...";
  const files = await pyodide.runPythonAsync("to_js(get_files())");
  if (files.length == 1) list.innerHTML = "<h3>Current GPX File</h3>";
  else if (files.length > 0) list.innerHTML = "<h3>Merged GPX Files</h3>";
  for (const f of files) {
    const li = document.createElement("li");
    li.textContent = f;
    list.appendChild(li);
  }
}

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

  on("state_changed", updateFileList);
}

// ── Trim ──────────────────────────────────────────────────────────────
function setupTrim() {
  $("#btn-trim-before").addEventListener("click", async () => {
    if (!pyodide || selectedPoint == null) return;
    showLoading("Trimming GPX");
    await pyodide.runPythonAsync(
      `trim_before(${selectedPoint.seg},${selectedPoint.idx})`,
    );
    emit("state_changed", true);
    hideLoading();
  });

  $("#btn-trim-after").addEventListener("click", async () => {
    if (!pyodide || selectedPoint == null) return;
    showLoading("Trimming GPX");
    await pyodide.runPythonAsync(
      `trim_after(${selectedPoint.seg},${selectedPoint.idx})`,
    );
    emit("state_changed", true);
    hideLoading();
  });
  on("point_selected", (p) => {
    $("#btn-trim-before").disabled = $("#btn-trim-after").disabled = !p;
  });
}

// ── Metadata ─────────────────────────────────────────────────────────
const metadataFields = [
  "name",
  "description",
  "author",
  "email",
  "copyright",
  "keywords",
];
async function loadMetadata(hasGpx) {
  let meta;
  if (!pyodide || !hasGpx) meta = {};
  else meta = await pyodide.runPythonAsync("to_js(get_metadata())");
  for (const field of metadataFields) {
    const mf = $("#meta-" + field);
    mf.value = meta[field] ?? "";
    mf.disabled = !hasGpx;
  }
  $("#meta-apply").disabled = true;
}

function setupMetadata() {
  for (const field of metadataFields) {
    $("#meta-" + field).addEventListener("input", () => {
      $("#meta-apply").disabled = false;
    });
  }
  $("#meta-apply").addEventListener("click", async () => {
    if (!pyodide) return;
    const values = {};
    for (const field of metadataFields)
      values[field] = $("#meta-" + field).value;
    await pyodide.runPythonAsync(`set_metadata(**${pyodide.toPy(values)})`);
    emit("state_changed", true);
  });
  on("state_changed", loadMetadata);
}

// ── Clean ──────────────────────────────────────────────────────────────
function setupClean() {
  on("state_changed", (hasGpx) => ($("#clean-apply").disabled = !hasGpx));

  $("#clean-outliers").addEventListener("change", () => {
    $("#clean-max-dist").disabled = $("#clean-max-time").disabled =
      !$("#clean-outliers").checked;
  });

  $("#clean-apply").addEventListener("click", async () => {
    if (!pyodide) return;
    const args = [
      parseInt($("#clean-size").value),
      $("#clean-bounds").checked,
      $("#clean-outliers").checked,
      parseFloat($("#clean-max-dist").value),
      parseFloat($("#clean-max-dist").value),
    ];
    console.log(args);
    showLoading("Cleaning GPX");
    await pyodide.runPythonAsync(`apply_clean(*${pyodide.toPy(args)})`);
    emit("state_changed", true);
    hideLoading();
  });
}

// ── Insert (new track) ───────────────────────────────────────────────
function createRow(lat = "", lon = "", ele = "", time = "") {
  const tbody = $("#point-rows");
  tbody.querySelector("[data-empty]").hidden = true;

  const makeInput = (type, value, step, placeholder, update) => {
    const td = document.createElement("td");
    const inp = document.createElement("input");
    inp.type = type;
    inp.step = step;
    inp.value = value;
    inp.placeholder = placeholder;
    if (update)
      inp.addEventListener("input", () =>
        emit("points_preview", getInsertRows()),
      );
    td.appendChild(inp);
    return td;
  };
  const makeActionBtn = (text, title, onClick) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn-icon";
    btn.textContent = text;
    btn.title = title;
    btn.addEventListener("click", onClick);
    return btn;
  };

  const tr = document.createElement("tr");
  tr.appendChild(makeInput("number", lat, "0.00001", "e.g. 42.1337", true));
  tr.appendChild(makeInput("number", lon, "0.00001", "e.g. -12.007", true));
  tr.appendChild(makeInput("number", ele, "0.1", "e.g. 42"));
  tr.appendChild(makeInput("datetime-local", time, "1", ""));

  const tdActions = document.createElement("td");
  const actions = document.createElement("span");
  actions.style.cssText = "display:flex";
  const upBtn = makeActionBtn("\u2191", "Move up", () => {
    const prev = tr.previousElementSibling;
    if (prev && !prev.hasAttribute("data-empty")) tbody.insertBefore(tr, prev);
    emit("points_preview", getInsertRows());
  });
  const downBtn = makeActionBtn("\u2193", "Move down", () => {
    const next = tr.nextElementSibling;
    if (next) tbody.insertBefore(next, tr);
    emit("points_preview", getInsertRows());
  });
  const removeBtn = makeActionBtn("\u00d7", "Remove", () => {
    tr.remove();
    if (tbody.children.length === 1)
      tbody.querySelector("[data-empty]").hidden = false;
    emit("points_preview", getInsertRows());
  });
  removeBtn.classList.add("danger");
  actions.append(upBtn, downBtn, removeBtn);
  tdActions.appendChild(actions);
  tr.appendChild(tdActions);

  tbody.appendChild(tr);
  emit("points_preview", getInsertRows());
}

function getInsertRows() {
  return [...$("#point-rows").querySelectorAll("tr:not([data-empty])")]
    .map((tr) => {
      const [tdLat, tdLon, tdEle, tdTime] = tr.children;
      const row = {
        lat: tdLat.querySelector("input").value,
        lon: tdLon.querySelector("input").value,
      };
      const ele = tdEle.querySelector("input").value;
      if (ele) row.ele = ele;
      const time = tdTime.querySelector("input").value;
      if (time) row.time = time;
      return row;
    })
    .filter((r) => r.lat && r.lon);
}

function setupInsert() {
  $("#btn-add-row").addEventListener("click", createRow);
  $("#insert-copy").addEventListener("click", () => {
    if (!selectedPoint) return;
    const pt = selectedPoint;
    createRow(
      pt.lat.toFixed(5),
      pt.lon.toFixed(5),
      pt.ele != null ? pt.ele.toFixed(1) : "",
      pt.time ? formatLocalTime(new Date(pt.time)) : "",
    );
  });
  on("point_selected", (point) => ($("#insert-copy").disabled = !point));
  on("state_changed", (hasGpx) => ($("#insert-apply").disabled = !hasGpx));
  on("map_clicked", (pt) => {
    if (
      !$("#insert-click-mode").checked ||
      $(`.tab-content[data-tab="insert"]`).hidden
    )
      return;
    createRow(pt.lat.toFixed(5), pt.lng.toFixed(5));
  });
  $("#insert-apply").addEventListener("click", async () => {
    const rows = getInsertRows();
    if (rows.length === 0 || !pyodide) return;
    showLoading("Inserting points...");
    try {
      rows.forEach((r) => {
        if (r.time) r.time = new Date(r.time).toISOString();
      });
      await pyodide.runPythonAsync(`insert_points(${pyodide.toPy(rows)})`);
      $("#point-rows")
        .querySelectorAll("tr:not([data-empty])")
        .forEach((e) => e.remove());
      emit("state_changed", true);
      emit("points_preview", null);
    } catch (err) {
      showToast("Insert failed: " + err.message);
      console.error(err);
    } finally {
      hideLoading();
    }
  });
}

// ── State and File buttons ───────────────────────────────────────────
function setupButtons() {
  $("#btn-save").addEventListener("click", () =>
    showToast("Save — not implemented yet"),
  );
  $("#btn-undo").addEventListener("click", async () => {
    if (!pyodide) return;
    const hasGpx = await pyodide.runPythonAsync("to_js(undo())");
    emit("state_changed", hasGpx);
  });
  $("#btn-reset").addEventListener("click", async () => {
    if (!pyodide) return;
    await pyodide.runPythonAsync("reset()");
    emit("state_changed", false);
  });
}

// ── Init ─────────────────────────────────────────────────────────────
setupTabs();
setupFileDrop();
setupTrim();
setupInsert();
setupButtons();
setupStats();
setupMap();
setupMetadata();
setupClean();
setupPyodide();
setupPlots();

on("state_changed", (_) => emit("point_selected", null));
on("point_selected", (pt) => (selectedPoint = pt));
window.addEventListener("resize", (e) => emit("resize", null));
emit("state_changed", false);
