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

async function hideLoadingLater() {
  if (pyodide) {
    await new Promise((r) => setTimeout(r, 100));
    await pyodide.runPythonAsync("pass");
  }
  hideLoading();
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
    .slice(0, 19);
}

function cmpArray(a, b) {
  if (a.length != b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] != b[i]) return false;
  return true;
}

// ── Pyodide ─────────────────────────────────────────────────────
let pyodide = null;
async function setupPyodide() {
  try {
    showLoading("Loading engine…");
    const py = await loadPyodide();
    showLoading("Loading GPhiX…");
    py.FS.mkdirTree("/gphix");
    py.FS.writeFile("/gphix/__init__.py", '"""GPX file toolbox."""');
    for (const f of [
      "utils.py",
      "gpx.py",
      "web.py",
      "trim.py",
      "elevation.py",
      "fix.py",
    ]) {
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
  let paths = [];
  try {
    for (const file of files) {
      const bytes = new Uint8Array(await file.arrayBuffer());
      pyodide.FS.writeFile(`/tmp/${file.name}`, bytes);
      paths.push(file.name);
    }
    await pyodide.runPythonAsync(`load_gpx("/tmp", ${pyodide.toPy(paths)})`);
    showLoading("Updating state…");
    emit("state_changed", true);
  } catch (err) {
    showToast("Failed to parse GPX: " + err.message);
    console.error(err);
  } finally {
    for (const path of paths) {
      pyodide.FS.unlink(`/tmp/${path}`);
    }
    hideLoadingLater();
  }
}

// ── Stats ────────────────────────────────────────────────────────
function setupStats() {
  $("#btn-first").addEventListener("click", () => selectPoint(0, ""));
  $("#btn-last").addEventListener("click", async () => {
    await selectPoint(-1, "");
    $("#btn-last").disabled = true;
    $("#btn-next").disabled = true;
  });
  $("#btn-prev").addEventListener("click", async () => {
    if (!selectedPoint || !pyodide) return;
    const pt = await pyodide.runPythonAsync(
      `to_js(get_point(${selectedPoint.seg},${selectedPoint.idx - 1}))`,
    );
    if (pt) emit("point_selected", pt);
    else $("#btn-prev").disabled = true;
  });
  $("#btn-next").addEventListener("click", async () => {
    if (!selectedPoint || !pyodide) return;
    const pt = await pyodide.runPythonAsync(
      `to_js(get_point(${selectedPoint.seg},${selectedPoint.idx + 1}))`,
    );
    if (pt) emit("point_selected", pt);
    else {
      $("#btn-next").disabled = true;
      $("#btn-last").disabled = true;
    }
  });

  on("meta_changed", onShowStats);
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
  $("#btn-first").disabled = point && point.seg + point.idx == 0;
  $("#btn-prev").disabled = !point || point.seg + point.idx == 0;
  $("#btn-next").disabled = !point;
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
    // setTimeout(async () => {
    const size = getSize($("#plot-time-dist"));
    if (size.width > 0) {
      await tdPlot.setSize(size);
      await edPlot.setSize(getSize($("#plot-elev-dist")));
      if (sdPlot != null) drawPlotPoint(sdPlot);
    }
    // }, 100);
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
  if (hasGpx && pyodide) data = await pyodide.runPythonAsync("to_js(get_plot_data())");
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
  on("resize", (_) => setTimeout(() => map.invalidateSize(false), 100));
  on("state_changed", renderMap);
  on("point_selected", onSelectedPointMap);
  on("map_preview", onPreviewPointMap);
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
      if (i > 0 && cmpArray(coords[i], coords[i - 1])) continue;
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
    if (points.length == 1 && !points[0].length)
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
    list.hidden = true;
    return;
  }
  list.hidden = false;
  list.innerHTML += "<p>Processing GPX files...</p>";
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
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
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
    showLoading("Updating state…");
    emit("state_changed", true);
    hideLoadingLater();
  });

  $("#btn-trim-after").addEventListener("click", async () => {
    if (!pyodide || selectedPoint == null) return;
    showLoading("Trimming GPX");
    await pyodide.runPythonAsync(`trim_after(${selectedPoint.seg},${selectedPoint.idx})`);
    showLoading("Updating state…");
    emit("state_changed", true);
    hideLoadingLater();
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
    for (const field of metadataFields) values[field] = $("#meta-" + field).value;
    await pyodide.runPythonAsync(`set_metadata(**${pyodide.toPy(values)})`);
    emit("meta_changed", true);
  });
  on("meta_changed", loadMetadata);
}

// ── Track Metadata ────────────────────────────────────────────────
async function loadTrackMetadata(hasGpx) {
  const cards = $("#track-cards");
  $("#track-apply").disabled = true;
  if (!pyodide || !hasGpx) {
    cards.innerHTML = '<li class="muted field">No tracks</li>';
    return;
  }
  const tracks = await pyodide.runPythonAsync("to_js(get_track_metadata())");
  if (tracks.length == 0) cards.innerHTML = '<li class="muted field">No tracks</li>';
  else cards.innerHTML = "";
  for (let i = 0; i < tracks.length; i++) {
    const li = document.createElement("li");
    li.className = "track-card";
    li.innerHTML = `
      <fieldset>
        <legend>Track ${i}${tracks[i].name ? ": " + escHtml(tracks[i].name) : ""}</legend>
        <div class="field"><label for="track-${i}-name">Name</label><input type="text" id="track-${i}-name" /></div>
        <div class="field"><label for="track-${i}-description">Description</label><input type="text" id="track-${i}-description" /></div>
        <div class="field"><label for="track-${i}-type">Type</label><input type="text" id="track-${i}-type" /></div>
      </fieldset>
    `;
    cards.appendChild(li);
    for (const field of ["name", "description", "type"]) {
      $(`#track-${i}-${field}`).value = tracks[i][field] ?? "";
      $(`#track-${i}-${field}`).addEventListener("input", () => {
        $("#track-apply").disabled = false;
      });
    }
  }
}

function setupTrackMetadata() {
  $("#track-apply").addEventListener("click", async () => {
    const len = $("#track-cards").children.length;
    const tracks = [...Array(len).keys()].map((i) => ({
      name: $(`#track-${i}-name`).value,
      description: $(`#track-${i}-description`).value,
      type: $(`#track-${i}-type`).value,
    }));
    $("#track-cards").innerHTML = '<li class="muted field">Updating tracks</li>';
    await pyodide.runPythonAsync(`set_track_metadata(${pyodide.toPy(tracks)})`);
    emit("meta_changed", true);
  });
  on("meta_changed", loadTrackMetadata);
}

// ── Clean ──────────────────────────────────────────────────────────────
function setupClean() {
  on("state_changed", (hasGpx) => ($("#clean-apply").disabled = !hasGpx));

  $("#clean-outliers").addEventListener("change", () => {
    $("#clean-max-dist").disabled = $("#clean-max-time").disabled =
      !$("#clean-outliers").checked;
  });

  $("#clean-apply").addEventListener("click", async () => {
    try {
      showLoading("Cleaning GPX…");
      const args = [
        $("#clean-outliers").checked,
        parseFloat($("#clean-max-dist").value),
        parseFloat($("#clean-max-time").value),
        parseInt($("#clean-size").value),
        $("#clean-merge").checked,
        $("#clean-bounds").checked,
      ];
      await pyodide.runPythonAsync(`apply_clean(*${pyodide.toPy(args)})`);
      showLoading("Updating state…");
      emit("state_changed", true);
    } catch (err) {
      showToast("Cleaning failed: " + err.message);
      console.error(err);
    } finally {
      hideLoadingLater();
    }
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
    if (update) inp.addEventListener("input", () => emit("map_preview", getInsertRows()));
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
    emit("map_preview", getInsertRows());
  });
  const downBtn = makeActionBtn("\u2193", "Move down", () => {
    const next = tr.nextElementSibling;
    if (next) tbody.insertBefore(next, tr);
    emit("map_preview", getInsertRows());
  });
  const removeBtn = makeActionBtn("\u00d7", "Remove", () => {
    tr.remove();
    if (tbody.children.length === 1) tbody.querySelector("[data-empty]").hidden = false;
    emit("map_preview", getInsertRows());
  });
  removeBtn.classList.add("danger");
  actions.append(upBtn, downBtn, removeBtn);
  tdActions.appendChild(actions);
  tr.appendChild(tdActions);

  tbody.appendChild(tr);
  emit("map_preview", getInsertRows());
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
    if (!$("#insert-click-mode").checked || $(`.tab-content[data-tab="insert"]`).hidden)
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
      showLoading("Updating state…");
      $("#point-rows")
        .querySelectorAll("tr:not([data-empty])")
        .forEach((e) => e.remove());
      emit("state_changed", true);
      emit("map_preview", null);
    } catch (err) {
      showToast("Insert failed: " + err.message);
      console.error(err);
    } finally {
      hideLoadingLater();
    }
  });
}

// ── Fix ──────────────────────────────────────────────────────────────
let fixList = [];

function setupFix() {
  on("state_changed", (hasGpx) => {
    $("#fix-find").disabled = !hasGpx;
    clearFixList();
  });

  $("#fix-clear").addEventListener("click", () => ($("#fix-ref").value = ""));
  for (const el of document.querySelectorAll('.tab-content[data-tab="fix"] input'))
    el.addEventListener("change", clearFixList);

  $("#fix-find").addEventListener("click", async () => {
    showLoading("Finding issues…");
    try {
      fixList = await pyodide.runPythonAsync(
        `to_js(find_issues(**${pyodide.toPy(getFixConfig())}))`,
      );
      renderFixList(true);
      renderFixPreview();
      $("#fix-apply").disabled = fixList.length === 0;
    } catch (err) {
      showToast("Find issues failed: " + err.message);
      console.error(err);
    } finally {
      hideLoading();
    }
  });

  $("#fix-apply").addEventListener("click", async () => {
    const issues = selectedFixIdx();
    if (issues.length == 0) {
      showToast("No gaps selected");
      return;
    }
    showLoading("Loading dependencies…");
    let args = getFixConfig();
    args.selected = issues;
    args.ref_path = "";
    const refs = $("#fix-ref");
    try {
      await pyodide.loadPackage("scipy");
      showLoading("Loading reference…");
      pyodide.FS.mkdirTree("/tmp/_fix_ref");
      if (refs.files.length > 0) {
        const file = refs.files[0];
        const bytes = new Uint8Array(await file.arrayBuffer());
        args.ref_path = `/tmp/_fix_ref/${file.name}`;
        pyodide.FS.writeFile(args.ref_path, bytes);
      }
      showLoading("Filling gaps…");
      await pyodide.runPythonAsync(`apply_fix(**${pyodide.toPy(args)})`);
      showLoading("Updating state…");
      clearFixList();
      emit("state_changed", true);
    } catch (err) {
      showToast("Fixing failed: " + err.message);
      console.error(err);
    } finally {
      if (args.ref_path != "") pyodide.FS.unlink(args.ref_path);
      hideLoadingLater();
    }
  });
}

function getFixConfig() {
  return {
    gaps: $("#fix-gaps").checked,
    frozen: $("#fix-frozen").checked,
    distance: parseFloat($("#fix-min-dist").value),
    duration: parseFloat($("#fix-min-time").value),
    points: parseInt($("#fix-min-num").value),
  };
}

function selectedFixIdx() {
  if (!fixList || fixList.length == 0) return [];
  return [...document.querySelectorAll("#fix-list input:checked")].map((cb) =>
    parseInt(cb.dataset.idx),
  );
}

function clearFixList() {
  $("#fix-apply").disabled = true;
  const hasList = fixList.length > 0;
  fixList = [];
  const list = $("#fix-list");
  list.hidden = true;
  list.innerHTML = "";
  if (hasList) renderFixPreview();
}

function renderFixList(after) {
  const list = $("#fix-list");
  list.hidden = false;
  if (fixList.length === 0) {
    list.innerHTML = after ? "<h3>No issues found</h3>" : "";
    return;
  }
  const formatListItem = (g, i) => {
    const time = g.time
      ? `${new Date(g.time).toLocaleString()}`
      : `(${g.start_lat.toFixed(5)}, ${g.start_lon.toFixed(5)})`;
    const length = g.length > 0 ? `, ${g.length}` : ", gap";
    const duration = g.duration ? `, ${g.duration}` : "";
    return `<li data-gap="${i}"><label class="check"><input type="checkbox" checked data-idx="${i}">&nbsp; ${time}, ${g.distance}${duration}${length}</label></li>`;
  };
  list.innerHTML = "<h3>Detected Issues</h3>" + fixList.map(formatListItem).join("");
  list
    .querySelectorAll("input")
    .forEach((cb) => cb.addEventListener("change", renderFixPreview));
}

function renderFixPreview() {
  emit(
    "map_preview",
    selectedFixIdx()
      .map((i) => fixList[i])
      .map((g) => [
        [g.start_lat, g.start_lon],
        [g.end_lat, g.end_lon],
      ]),
  );
}

// ── Elevation ─────────────────────────────────────────────────────────
function setupElevation() {
  $("#elev-apply").addEventListener("click", async () => {
    const elevInput = $("#elev-sources");
    if (elevInput.files.length === 0) {
      showToast("No elevation reference files loaded");
      return;
    }
    const args = {
      radius: parseFloat($("#elev-radius").value),
      overwrite: $("#elev-overwrite").checked ? "True" : "False",
      paths: [],
    };
    try {
      showLoading("Loading dependencies…");
      await pyodide.loadPackage("rasterio");
      await pyodide.loadPackage("scipy");
      showLoading("Reading files…");
      pyodide.FS.mkdirTree("/tmp/_elev_ref");
      for (const file of elevInput.files) {
        const bytes = new Uint8Array(await file.arrayBuffer());
        pyodide.FS.writeFile(`/tmp/_elev_ref/${file.name}`, bytes);
        args.paths.push(`/tmp/_elev_ref/${file.name}`);
      }
      showLoading("Adding elevation…");
      await pyodide.runPythonAsync(`apply_elevation(**${pyodide.toPy(args)})`);
      showLoading("Updating state…");
      emit("state_changed", true);
    } catch (err) {
      showToast("Elevation failed: " + err.message);
      console.error(err);
    } finally {
      for (const file of args.paths) {
        pyodide.FS.unlink(file);
      }
      hideLoadingLater();
    }
  });

  on("state_changed", (hasGpx) => ($("#elev-apply").disabled = !hasGpx));
}

// ── State and File buttons ───────────────────────────────────────────
function setupButtons() {
  on("state_changed", (hasGpx) => ($("#btn-save").disabled = !hasGpx));

  $("#btn-save").addEventListener("click", async () => {
    showLoading("Saving GPX");
    try {
      const files = await pyodide.runPythonAsync("get_files()");
      if (files.length == 0) return showToast("No GPX to save");
      const name = files[0].replace(/\.gpx$/i, "_processed.gpx");
      const xml = await pyodide.runPythonAsync("save_gpx()");
      const blob = new Blob([xml], { type: "application/gpx+xml" });
      if ("showSaveFilePicker" in window) {
        const handle = await window.showSaveFilePicker({
          suggestedName: name,
          types: [
            {
              description: "GPX File",
              accept: { "application/gpx+xml": [".gpx"] },
            },
          ],
        });
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
      } else {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      if (err.name !== "AbortError") showToast("Save failed: " + err.message);
    } finally {
      hideLoading();
    }
  });

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
  $("#plot-toggle").addEventListener("click", async () => {
    const plotPanel = $("#plot-panel");
    plotPanel.hidden = !plotPanel.hidden;
    $("#plot-toggle").textContent = plotPanel.hidden ? "◀" : "▶";
    emit("resize", null);
  });

  document.querySelectorAll(".desc").forEach((d) => {
    d.addEventListener("click", async () => {
      showLoading("Preloading dependencies…");
      await pyodide.loadPackage("rasterio");
      await pyodide.loadPackage("scipy");
      hideLoading();
      showToast("Offline mode activated");
    });
  });
}

// ── Init ─────────────────────────────────────────────────────────────
setupTabs();
setupFileDrop();
setupButtons();
setupStats();
setupMetadata();
setupTrackMetadata();
setupClean();
setupTrim();
setupInsert();
setupElevation();
setupFix();
setupMap();
setupPlots();
setupPyodide();

on("state_changed", (_) => emit("point_selected", null));
on("state_changed", (b) => emit("meta_changed", b));
on("point_selected", (pt) => (selectedPoint = pt));
window.addEventListener("resize", (e) => emit("resize", null));
emit("state_changed", false);
