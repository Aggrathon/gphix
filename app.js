// ── Helpers ──────────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);

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

// ── State ────────────────────────────────────────────────────────
const state = {
  files: [],
  track: null,
  selectedPoint: null,
  activeTab: "data",
};

// ── Chart setup ──────────────────────────────────────────────────
function setupCharts() {
  const chartIds = ["chart-elev", "chart-time-dist", "chart-time-elev"];
  const placeholder = "Load a GPX file to see charts";

  function drawPlaceholder(canvas) {
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    canvas.width = canvas.clientWidth * dpr;
    canvas.height = canvas.clientHeight * dpr;
    ctx.scale(dpr, dpr);
    ctx.fillStyle = "#fdfdfd";
    ctx.fillRect(0, 0, canvas.width / dpr, canvas.height / dpr);
    ctx.fillStyle = "#aaa";
    ctx.font = "13px system-ui";
    ctx.textAlign = "center";
    ctx.fillText(placeholder, canvas.width / dpr / 2, canvas.height / dpr / 2);
  }

  chartIds.forEach((id) => {
    const canvas = document.getElementById(id);
    if (canvas) drawPlaceholder(canvas);
  });

  const observer = new ResizeObserver(() => {
    chartIds.forEach((id) => {
      const canvas = document.getElementById(id);
      if (canvas) drawPlaceholder(canvas);
    });
  });
  chartIds.forEach((id) => {
    const canvas = document.getElementById(id);
    if (canvas) observer.observe(canvas);
  });
}

// ── Map setup ────────────────────────────────────────────────────
const map = L.map("map").setView([0, 0], 2);
function setupMap() {
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "\u00a9 OpenStreetMap contributors",
    referrerPolicy: "origin-when-cross-origin",
  }).addTo(map);
}

const invalidateMap = () => setTimeout(() => map.invalidateSize(), 100);

// ── Tab switching ──────────────────────────────────────────────
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
      if (target) {
        target.classList.add("active");
      }
      state.activeTab = btn.dataset.tab;
      invalidateMap();
    });
  });
}

// ── Tabs ─────────────────────────────────────────────────────
const tabConfig = {
  trim: ["trim-start", "trim-end", "trim-mode"],
  insert: ["insert-points"],
  elevation: ["elev-sources", "elev-radius", "elev-overwrite"],
  fill: ["fill-ref", "fill-min-dist", "fill-min-time"],
  clean: ["clean-outliers", "clean-max-dist", "clean-bounds"],
  meta: [
    "meta-name",
    "meta-desc",
    "meta-author",
    "meta-email",
    "meta-copyright",
    "meta-keywords",
  ],
};

function setupControls() {
  const baselines = new Map();

  const getBaseline = (el) =>
    el.type === "checkbox" || el.type === "radio" ? el.checked : el.value;

  const hasChanges = (tab) =>
    (tabConfig[tab] || [])
      .map((id) => document.getElementById(id))
      .filter(Boolean)
      .some((el) => getBaseline(el) !== baselines.get(el));

  const refreshApplyButtons = () => {
    for (const tab of Object.keys(tabConfig)) {
      const btn = document.getElementById(tab + "-apply");
      if (btn) btn.disabled = !hasChanges(tab);
    }
  };

  for (const [tab, ids] of Object.entries(tabConfig)) {
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      baselines.set(el, getBaseline(el));
      el.addEventListener("change", refreshApplyButtons);
      el.addEventListener("input", refreshApplyButtons);
    });
  }

  document
    .getElementById("elev-add")
    ?.addEventListener("click", refreshApplyButtons);
  refreshApplyButtons();
}

// ── File drop ────────────────────────────────────────────────────
function setupFileDrop() {
  const dropZone = $(".drop-zone");
  const fileInput = $("#file-input");
  fileInput.multiple = true;

  function handleFiles(files) {
    state.files = [...state.files, ...Array.from(files)];
    const list = document.getElementById("file-list");
    Array.from(files).forEach((f) => {
      const li = document.createElement("li");
      li.innerHTML = `<span class="monospace">${f.name}</span>`;
      list.appendChild(li);
    });
    showToast(`Loaded ${files.length} file(s) — skeleton mode, no parsing yet`);
  }

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

// ── Trim sliders ─────────────────────────────────────────────────
function setupTrimSliders() {
  const startSlider = $("#trim-start");
  const endSlider = $("#trim-end");
  const startOutput = $("#trim-start-value");
  const endOutput = $("#trim-end-value");

  startSlider?.addEventListener("input", () => {
    if (startOutput) startOutput.textContent = `${startSlider.value}%`;
  });
  endSlider?.addEventListener("input", () => {
    if (endOutput) endOutput.textContent = `${endSlider.value}%`;
  });
  startSlider.value = 0;
  endSlider.value = 0;
}

// ── File Buttons ───────────────────────────────────────────────
function setupFileButtons() {
  const saveBtn = document.getElementById("btn-save");
  if (saveBtn)
    saveBtn.addEventListener("click", () =>
      showToast("Save — not implemented yet"),
    );

  const undoBtn = document.getElementById("btn-undo");
  if (undoBtn)
    undoBtn.addEventListener("click", () =>
      showToast("Undo — not implemented yet"),
    );

  const resetBtn = document.getElementById("btn-reset");
  if (resetBtn)
    resetBtn.addEventListener("click", () =>
      showToast("Reset — not implemented yet"),
    );
}

// ── Init ─────────────────────────────────────────────────────────
setupCharts();
setupMap();
setupTabs();
setupControls();
setupFileDrop();
setupTrimSliders();
setupFileButtons();
