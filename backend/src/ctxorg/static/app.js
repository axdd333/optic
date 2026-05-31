const el = {
  canvas: document.querySelector("#scene"),
  viewport: document.querySelector(".viewport"),
  cards: document.querySelector("#workspace-cards"),
  onboard: document.querySelector("#onboard"),
  scanBtn: document.querySelector("#scanBtn"),
  run: document.querySelector("#run"),
  search: document.querySelector("#search"),
  leftnav: document.querySelector(".leftnav"),
  mobileNav: document.querySelector("#mobileNav"),
  leftnavSettingsBtn: document.querySelector("#leftnavSettingsBtn"),
  tip: document.querySelector("#tooltip"),
  inspector: document.querySelector("#inspector"),
  counts: document.querySelector("#counts"),
  statusbarIndex: document.querySelector("#statusbarIndex"),
  statusSignals: document.querySelector("#statusSignals"),
  statusRun: document.querySelector("#statusRun"),
  modeName: document.querySelector("#modeName"),
  messages: document.querySelector("#messages"),
  draft: document.querySelector("#draft"),
  chatForm: document.querySelector("#chatForm"),
  chips: document.querySelector(".chips"),
  irisModebar: document.querySelector("#irisModebar"),
  irisEntityBar: document.querySelector("#irisEntityBar"),
  irisEntityLabel: document.querySelector("#irisEntityLabel"),
  irisAudienceSelect: document.querySelector("#irisAudienceSelect"),
  topbarPresenceBtn: document.querySelector(".topbar-presence"),
  topbarPresenceDot: document.querySelector(".topbar-presence-dot"),
  topbarAvatarBtn: document.querySelector(".topbar-avatar"),
  logoLockup: document.querySelector("#logoLockup"),
  logoFallback: document.querySelector("#logoFallback"),
};

const palette = {
  Documents: "#5aa7ff",
  Images: "#4bd6c6",
  Code: "#f2bd5a",
  Video: "#ff7f73",
  System: "#7c8291",
  Other: "#b889ff",
};

const modeTitle = {
  workstreams: "Home",
  topology: "Map",
  timeline: "Timeline",
  universe: "Universe",
  iris: "Iris",
  vault: "Vault",
  audiences: "Audiences",
  simulations: "Simulations",
  exports: "Exports",
  onboard: "Scan",
};

const state = {
  run: "",
  home: "",               // user home dir from /api/home
  homeData: null,
  homeSummary: null,
  workstreams: [],
  audiences: [],
  audienceCache: new Map(),
  simulations: [],
  settings: null,
  status: null,
  report: null,
  account: { signed_in: false, account: null },
  graph: { nodes: [], links: [] },
  nodes: [],
  links: [],
  nodeById: new Map(),
  selected: null,
  hover: null,
  q: "",
  highlightCluster: null, // persistent cluster focus (set by "View in map")
  manager: null,
  irisMode: "report",     // current Iris mode
  irisHistory: [],        // multi-turn conversation history [{role,content}]
  irisStreaming: false,   // true while a response is streaming
  irisAbort: null,
  irisReqSeq: 0,
  irisErrStreak: 0,
  // Identity-mode state
  irisEntityIds: [],      // item IDs selected for entity/compare/audience/audit modes
  irisAudience: "recruiter", // selected audience for audience-lens mode
  mirrorRan: false,
  wsFocusCluster: null,
};

const ui = {
  tl: null,
  map: null,
  labels: null,
  hint: null,
  modal: null,
};

boot().catch(err => {
  console.error(err);
  el.inspector.innerHTML = `<h2 class="panel-title">Optic failed</h2>
    <p class="path">${esc(err.message || String(err))}</p>`;
});

const URL_MODE_ALLOW = new Set([
  "workstreams",
  "topology",
  "timeline",
  "universe",
  "iris",
  "vault",
  "audiences",
  "simulations",
  "exports",
  "onboard",
]);

async function boot() {
  initLogoLockup();
  await runs();
  await loadGraph();
  await Promise.all([
    refreshHomeData(),
    refreshReport(),
    refreshStatus(),
    refreshSettings(),
  ]);
  if (window.__opticSyncAccount) await window.__opticSyncAccount();
  normalizeShellNav();
  normalizeSettingsEntryPoints();
  bindShell();
  state.manager = new ModeManager();
  state.manager.switch(startModeFromUrl());
  // Iris welcome greeting
  irisWelcome();
}

function startModeFromUrl() {
  const mode = new URLSearchParams(location.search).get("mode");
  return URL_MODE_ALLOW.has(mode) ? mode : "workstreams";
}

function activeRun() {
  return String(el.run?.value || state.run || "").trim();
}

function writeUrlState(mode, run = activeRun()) {
  const q = new URLSearchParams(location.search);
  q.set("mode", mode || "workstreams");
  if (run) q.set("run", run);
  else q.delete("run");
  history.replaceState(null, "", `?${q.toString()}`);
}

function normalizeShellNav() {
  const top = document.querySelector(".topbar");
  if (top) {
    top.querySelectorAll("[data-mode], .modebar, .mode-tabs, .top-nav, " +
      ".nav-tabs").forEach(node => node.remove());
  }
  dedupeModeButtons(el.leftnav);
  dedupeModeButtons(el.mobileNav);
}

function dedupeModeButtons(root) {
  if (!root) return;
  const seen = new Set();
  root.querySelectorAll("button[data-mode]").forEach(btn => {
    const mode = String(btn.dataset.mode || "").trim();
    if (!mode) return btn.remove();
    if (seen.has(mode)) return btn.remove();
    seen.add(mode);
  });
}

function normalizeSettingsEntryPoints() {
  pinSettingsEntry("primary", "#leftnavSettingsBtn");
  pinSettingsEntry("contextual", "#topbarAvatarBtn");
}

function pinSettingsEntry(kind, preferSel) {
  const nodes = [...document.querySelectorAll(
    `[data-settings-entry='${kind}']`
  )];
  if (!nodes.length) return;
  const keep = nodes.find(node => node.matches(preferSel)) || nodes[0];
  nodes.forEach(node => {
    if (node === keep) return;
    node.hidden = true;
    node.setAttribute("aria-hidden", "true");
    node.removeAttribute("data-settings-entry");
  });
}

function initLogoLockup() {
  const lockup = el.logoLockup;
  const fallback = el.logoFallback;
  if (!lockup || !fallback) return;
  let sealed = false;
  const apply = useFallback => {
    if (sealed) return;
    sealed = true;
    lockup.hidden = useFallback;
    fallback.hidden = !useFallback;
  };
  const useFallback = () => {
    apply(true);
  };
  const useLockup = () => {
    apply(false);
  };
  const validate = () => {
    if (!lockup.naturalWidth || lockup.naturalWidth < 120) {
      useFallback();
      return;
    }
    useLockup();
  };
  lockup.addEventListener("load", validate);
  lockup.addEventListener("error", useFallback, { once: true });
  if (lockup.complete) validate();
}

async function refreshHomeData(force = false) {
  if (!force && state.homeData) return state.homeData;
  try {
    const data = await getJson("/api/home");
    state.homeData = data || {};
    state.home = data?.home || state.home || "";
    if (data?.iris_summary) state.homeSummary = data.iris_summary;
    updateStatusIndex(state.homeData);
    return state.homeData;
  } catch (_) {
    return state.homeData || {};
  }
}

async function refreshAudiences(force = false) {
  if (!force && state.audiences.length) return state.audiences;
  try {
    const data = await getJson("/api/audiences");
    const vals = Array.isArray(data?.audiences) ? data.audiences : [];
    state.audiences = vals;
    return vals;
  } catch (_) {
    state.audiences = [];
    return [];
  }
}

async function refreshStatus(force = false) {
  if (!force && state.status) return state.status;
  try {
    const data = await getJson("/api/status");
    state.status = data || {};
    syncTopbarPresence();
    return state.status;
  } catch (_) {
    syncTopbarPresence();
    return state.status || {};
  }
}

async function refreshReport(force = false) {
  if (!force && state.report) return state.report;
  const run = encodeURIComponent(state.run || "");
  try {
    const data = await getJson(`/api/report?run=${run}`);
    state.report = data || {};
    return state.report;
  } catch (_) {
    return state.report || {};
  }
}

async function refreshSettings(force = false) {
  if (!force && state.settings) return state.settings;
  try {
    const data = await getJson("/api/settings");
    state.settings = data?.settings || null;
    return state.settings;
  } catch (_) {
    return state.settings;
  }
}

async function refreshSimulations(force = false) {
  if (!force && state.simulations.length) return state.simulations;
  const run = encodeURIComponent(state.run || "");
  try {
    const data = await getJson(`/api/simulations?run=${run}`);
    state.simulations = Array.isArray(data?.items) ? data.items : [];
    return state.simulations;
  } catch (_) {
    state.simulations = [];
    return state.simulations;
  }
}

function updateStatusIndex(data = {}) {
  if (!el.statusbarIndex) return;
  const ago = String(data.last_analyzed_ago || "—");
  const sig = Number(data.signal_count || 0).toLocaleString();
  const src = Number(data.source_count || 0).toLocaleString();
  const run = state.status?.last_run || state.run || "—";
  el.statusbarIndex.textContent = `Up to date · ${ago}`;
  if (el.statusSignals) el.statusSignals.textContent = `${sig} from ${src}`;
  if (el.statusRun) {
    const label = String(run).replace(/^(\d{4})(\d{2})(\d{2})-/, "$1-$2-$3 ");
    el.statusRun.textContent = label;
  }
}

function syncTopbarPresence() {
  const btn = el.topbarPresenceBtn;
  const dot = el.topbarPresenceDot;
  if (!btn || !dot) return;
  const qd = Number(state.status?.queue_depth || 0);
  const st = String(state.status?.progress?.stage_state || "").toLowerCase();
  const busy = qd > 0 || (st && !["ready", "idle", "done"].includes(st));
  const signedIn = !!state.account?.signed_in;
  const txt = busy ? "Status: indexing in progress."
    : signedIn ? "Status: account connected."
      : "Status: local-only mode.";
  dot.style.background = busy ? "#d97706" : signedIn ? "#2563eb" : "#16a34a";
  btn.title = txt;
  btn.setAttribute("aria-label", txt);
}

function irisWelcome() {
  const count = state.nodes.length;
  const div = document.createElement("div");
  div.className = "msg msg-welcome";
  if (count > 0) {
    div.innerHTML = `
      <span class="welcome-icon" aria-hidden="true"></span>
      <span class="welcome-title">Ask anything about your files</span>
      <span class="welcome-sub">${count.toLocaleString()} files indexed · everything stays on-device</span>`;
  } else {
    div.innerHTML = `
      <span class="welcome-icon" aria-hidden="true"></span>
      <span class="welcome-title">No files indexed yet</span>
      <span class="welcome-sub">Scan a folder to get started</span>`;
  }
  el.messages.appendChild(div);
}

async function runs() {
  const data = await getJson("/api/runs");
  el.run.innerHTML = data.runs.map(runOpt).join("");
  const req = new URLSearchParams(location.search).get("run");
  if (req && data.runs.includes(req)) el.run.value = req;
}

function runOpt(run) {
  // Format run ID like "20260515-utility-map" → "Run: May 15, 2026 • utility map"
  const m = run.match(/^(\d{4})(\d{2})(\d{2})-(.+)$/);
  if (m) {
    const months = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    const label = `Run: ${months[+m[2]]} ${+m[3]}, ${m[1]} • ${
      m[4].replace(/-/g," ")}`;
    return `<option value="${esc(run)}">${esc(label)}</option>`;
  }
  return `<option value="${esc(run)}">Run: ${esc(run)}</option>`;
}

async function loadGraph() {
  state.run = el.run.value;
  const url = `/api/graph?run=${encodeURIComponent(state.run)}`;
  state.graph = await getJson(url);
  state.nodes = state.graph.nodes.map(normalNode);
  state.links = state.graph.links.map(normalLink);
  state.nodeById = new Map(state.nodes.map(n => [n.id, n]));
  attachDegrees();
  syncSelected();
}

function normalNode(n) {
  const path = n.path || "";
  const label = displayName(n.label || base(path), path);
  return { ...n, label, category: category(n), size: num(n.size),
    mtime: num(n.mtime), degree: 0, r: radius(num(n.size)),
    noise: labelNoise(path), glow: 0,
    pcaX: num(n.x), pcaY: num(n.y), pcaZ: num(n.z), pcaW: num(n.w),
    cluster: n.cluster || n.id };
}

function normalLink(l) {
  return { a: l.a, b: l.b, score: num(l.score) || 0.1,
    why: l.why || "related" };
}

function attachDegrees() {
  state.nodes.forEach(n => n.degree = 0);
  const ok = [];
  state.links.forEach(l => {
    const a = state.nodeById.get(l.a);
    const b = state.nodeById.get(l.b);
    if (!a || !b) return;
    a.degree += 1;
    b.degree += 1;
    ok.push(l);
  });
  state.links = ok;
}

function syncSelected() {
  if (!state.selected?.id) {
    state.selected = null;
    return null;
  }
  const n = state.nodeById.get(state.selected.id);
  if (!n) {
    state.selected = null;
    return null;
  }
  state.selected = n;
  return n;
}

function bindShell() {
  el.run.addEventListener("change", changeRun);
  el.search.addEventListener("input", search);
  el.leftnav?.addEventListener("click", chooseMode);
  el.mobileNav?.addEventListener("click", chooseMode);
  el.leftnavSettingsBtn?.addEventListener("click", () => {
    if (typeof window.__opticOpenSettings === "function") {
      window.__opticOpenSettings();
      return;
    }
    el.topbarAvatarBtn?.click();
  });
  el.chatForm.addEventListener("submit", sendDraft);
  el.chips.addEventListener("click", chip);
  window.addEventListener("keydown", key);
  el.scanBtn.addEventListener("click", () => {
    void syncShellNow();
  });
  // Iris mode tabs + clear chat
  if (el.irisModebar) el.irisModebar.addEventListener("click", chooseIrisMode);
  document.querySelector("#clearChat")?.addEventListener("click", () => {
    el.messages.innerHTML = "";
    state.irisHistory = [];
    state.mirrorRan = false; // allow mirror to auto-run again after clear
    irisWelcome();
  });
  // Wire audience select → state.irisAudience
  if (el.irisAudienceSelect) {
    el.irisAudienceSelect.addEventListener("change", () => {
      state.irisAudience = el.irisAudienceSelect.value;
    });
  }
  // Cmd/Ctrl+Enter submits chat from textarea
  el.draft.addEventListener("keydown", ev => {
    if (ev.key === "Enter" && (ev.metaKey || ev.ctrlKey)) {
      ev.preventDefault();
      el.chatForm.dispatchEvent(new Event("submit", { cancelable: true }));
    }
    if (ev.key === "Enter" && !ev.shiftKey && !ev.metaKey && !ev.ctrlKey) {
      ev.preventDefault();
      el.chatForm.dispatchEvent(new Event("submit", { cancelable: true }));
    }
    if (ev.key === "Escape") { el.draft.blur(); }
  });
  // Auto-resize textarea as user types
  el.draft.addEventListener("input", () => {
    el.draft.style.height = "auto";
    el.draft.style.height = Math.min(el.draft.scrollHeight, 110) + "px";
    syncChatSend();
  });
  syncIrisModeTabs();
  syncChatSend();
}

async function syncShellNow() {
  const mode = state.manager?.name || startModeFromUrl();
  el.scanBtn.disabled = true;
  try {
    await Promise.all([refreshHomeData(true), refreshReport(true),
      refreshStatus(true), refreshSettings(true)]);
    updateStatusIndex(state.homeData || {});
    state.manager?.reload();
    writeUrlState(mode);
  } catch (_) {
    return;
  } finally {
    el.scanBtn.disabled = false;
  }
}

function chooseIrisMode(ev) {
  const btn = ev.target.closest("button[data-imode]");
  if (!btn) return;
  state.irisMode = btn.dataset.imode;
  syncIrisModeTabs();

  const placeholders = {
    report:        "Ask Iris for a corpus report…",
    archive:       "Ask Iris to organize or rename files…",
    mirror:        "Run adversarial footprint analysis…",
    retune:        "Ask Iris to find noise and clean up…",
    entity:        "Ask about this file: what does it reveal?",
    compare:       "Compare selected files — what do they imply together?",
    audience:      "How would this audience read the selected files?",
    contradiction: "Scan selected files for contradictions…",
    audit:         "Generate a full identity audit for selected files…",
  };
  el.draft.placeholder = placeholders[state.irisMode] || "Ask Iris…";
  updateIrisChips(state.irisMode);
  updateEntityBar(state.irisMode);

  if (state.irisMode === "mirror" && !state.mirrorRan) {
    state.mirrorRan = true;
    streamIris("Run full adversarial footprint analysis");
  }
}

function syncIrisModeTabs() {
  if (!el.irisModebar) return;
  el.irisModebar.querySelectorAll("button[data-imode]").forEach(btn => {
    const on = btn.dataset.imode === state.irisMode;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
    btn.tabIndex = on ? 0 : -1;
  });
}

function updateEntityBar(mode) {
  if (!el.irisEntityBar) return;
  const identityModes = ["entity", "compare", "audience", "contradiction", "audit"];
  const show = identityModes.includes(mode);
  el.irisEntityBar.style.display = show ? "flex" : "none";
  if (el.irisAudienceSelect) {
    el.irisAudienceSelect.style.display = mode === "audience" ? "inline-flex" : "none";
  }
  if (show) refreshEntityLabel();
}

function refreshEntityLabel() {
  if (!el.irisEntityLabel) return;
  const ids = state.irisEntityIds;
  if (!ids.length) {
    el.irisEntityLabel.textContent = "No file selected — click a node";
    el.irisEntityLabel.className = "entity-label entity-label--empty";
  } else if (ids.length === 1) {
    const n = state.nodeById.get(ids[0]);
    const name = n ? (n.label || n.path?.split("/").pop() || ids[0]) : ids[0];
    el.irisEntityLabel.textContent = `Entity: ${name}`;
    el.irisEntityLabel.className = "entity-label entity-label--set";
  } else {
    el.irisEntityLabel.textContent = `${ids.length} entities selected`;
    el.irisEntityLabel.className = "entity-label entity-label--multi";
  }
}

const IDENTITY_MODES = new Set(["entity", "compare", "audience", "contradiction", "audit"]);

function selectNodeAsEntity(n, ev) {
  if (!IDENTITY_MODES.has(state.irisMode) || !n) return;
  if (ev && (ev.ctrlKey || ev.metaKey)) {
    const idx = state.irisEntityIds.indexOf(n.id);
    if (idx >= 0) {
      state.irisEntityIds.splice(idx, 1);
    } else if (state.irisEntityIds.length < 6) {
      state.irisEntityIds.push(n.id);
    }
  } else {
    state.irisEntityIds = [n.id];
  }
  refreshEntityLabel();
}

function updateIrisChips(mode) {
  const chipSets = {
    report:  [
      { q: "What's using the most space?", label: "Most space?" },
      { q: "Run a full corpus report",     label: "Full report" },
      { q: "What file types do I have?",   label: "File types" },
    ],
    archive: [
      { q: "Suggest renames for my top 10 largest files", label: "Rename top files" },
      { q: "Find files that don't belong in Downloads",   label: "Clean Downloads" },
      { q: "Organize my Desktop files",                   label: "Organize Desktop" },
    ],
    mirror: [
      { q: "What are my top 3 highest-risk exposures and exactly how to fix them?", label: "Top risks + fixes" },
      { q: "What can an adversary infer about my identity from these files?",        label: "Identity inference" },
      { q: "Show me the attacker's 1-hour plan against my footprint",               label: "Attack paths" },
    ],
    retune: [
      { q: "Find duplicate files",          label: "Find duplicates" },
      { q: "What should I delete?",         label: "What to delete?" },
      { q: "Find stale downloads",          label: "Stale downloads" },
    ],
    entity: [
      { q: "What does this file reveal about me?",             label: "What does it reveal?" },
      { q: "What risks does this file create?",                label: "Risks" },
      { q: "What would a recruiter infer from this file?",     label: "Recruiter view" },
      { q: "What signals does this file emit?",                label: "Signals" },
    ],
    compare: [
      { q: "What do these files collectively imply about my identity?", label: "Collective inference" },
      { q: "Which file dominates and why?",                             label: "Dominant entity" },
      { q: "What contradictions exist across these files?",             label: "Contradictions" },
    ],
    audience: [
      { q: "What would this audience notice first?",                    label: "First impression" },
      { q: "What would this audience penalise?",                        label: "Red flags" },
      { q: "How do I repair my signal for this audience?",              label: "Repair plan" },
    ],
    contradiction: [
      { q: "Find all contradictions across the selected files",         label: "Scan all" },
      { q: "Are there timeline conflicts in these files?",              label: "Timeline conflicts" },
      { q: "Do these files agree on skills and affiliations?",          label: "Skill conflicts" },
    ],
    audit: [
      { q: "Generate a complete identity audit for selected files",     label: "Full audit" },
      { q: "What is my dominant signal across all evidence?",           label: "Dominant signal" },
      { q: "Give me the repair map only",                               label: "Repair map" },
    ],
  };
  const chips = chipSets[mode] || chipSets.report;
  el.chips.innerHTML = chips.map(c =>
    `<button data-q="${esc(c.q)}">${esc(c.label)}</button>`
  ).join("");
}

async function changeRun() {
  writeUrlState(state.manager?.name || startModeFromUrl(), el.run.value);
  await loadGraph();
  await Promise.all([
    refreshHomeData(true),
    refreshReport(true),
    refreshStatus(true),
    refreshSimulations(true),
  ]);
  state.selected = null;
  state.manager.reload();
  renderPanel();
}

function search() {
  state.q = el.search.value.trim().toLowerCase();
  state.highlightCluster = null; // searching clears cluster focus
  state.nodes.forEach(n => n.glow = matches(n) ? 16 : 0);
  state.manager.mode.onSearch(state.q);
}

function chooseMode(ev) {
  const btn = ev.target.closest("button[data-mode]");
  if (!btn) return;
  state.manager.switch(btn.dataset.mode);
}

function key(ev) {
  if (ev.key === "Escape" && closeAudienceModal()) return;
  if (typing(ev.target)) return;
  if (ev.key === "Escape") return clearSelection();
  // '/' focuses search (like GitHub/Linear/etc.)
  if (ev.key === "/" || ev.key === "f") {
    ev.preventDefault();
    el.search.focus();
    el.search.select();
    return;
  }
  // Number keys 1-4 switch views
  if (ev.key === "1") return state.manager.switch("workstreams");
  if (ev.key === "2") return state.manager.switch("topology");
  if (ev.key === "3") return state.manager.switch("timeline");
  if (ev.key === "4") return state.manager.switch("universe");
  if (ev.key === "5") return state.manager.switch("iris");
  if (ev.key === "6") return state.manager.switch("vault");
  if (ev.key === "7") return state.manager.switch("audiences");
  if (ev.key === "8") return state.manager.switch("simulations");
  if (ev.key === "9") return state.manager.switch("exports");
  state.manager.mode.onKey(ev);
}

function typing(t) {
  return t && ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName);
}

function clearSelection() {
  state.selected = null;
  state.hover = null;
  state.highlightCluster = null;
  if (state.manager?.name === "topology" && state.manager.mode?.mapTool) {
    state.manager.mode.mapTool = "pan";
    state.manager.mode.syncMapToolbar?.();
    state.manager.mode.syncMapHint?.();
  }
  hideTip();
  renderPanel();
  state.manager?.mode?.draw?.();
}

// Canvas-based modes need a fresh <canvas>; div-based modes use their own containers.
const CANVAS_MODES = new Set(["topology", "timeline", "universe"]);

class ModeManager {
  constructor() {
    this.mode = null;
    this.name = "";
    this.modes = {
      workstreams: new WorkstreamsMode(),
      topology: new TopologyMode(),
      timeline: new TimelineMode(),
      universe: new UniverseMode(),
      iris: new IrisMode(),
      vault: new VaultMode(),
      audiences: new AudiencesMode(),
      simulations: new SimulationsMode(),
      exports: new ExportsMode(),
      onboard: new OnboardMode(),
    };
  }

  switch(name) {
    const next = this.modes[name];
    if (!next) return;
    if (this.mode) this.mode.unmount();
    this.name = name;
    writeUrlState(name);
    normalizeShellNav();
    // Toggle universe dark bg class on app root
    document.querySelector(".app").dataset.mode = name;
    this.mode = next;
    this.mark();
    const irisConsole = document.querySelector(".iris-console");
    if (irisConsole) irisConsole.hidden = true;
    document.querySelector(".side")?.classList.remove("side-chat");
    if (CANVAS_MODES.has(name)) {
      el.draft.placeholder = "Ask Iris about this map";
      this.resetCanvas();
      el.canvas.hidden = false;
      el.cards.hidden = true;
      el.onboard.hidden = true;
      this.mode.mount(el.canvas);
    } else if (name === "onboard") {
      el.draft.placeholder = "Ask Iris about your files…";
      el.canvas.hidden = true;
      el.cards.hidden = true;
      el.onboard.hidden = false;
      this.mode.mount(el.onboard);
    } else {
      el.draft.placeholder = "Ask Iris about your files…";
      el.canvas.hidden = true;
      el.onboard.hidden = true;
      el.cards.hidden = false;
      this.mode.mount(el.cards);
    }
    toggleTimelineHud(name === "timeline");
    renderPanel();
  }

  mark() {
    if (el.modeName) el.modeName.textContent = modeTitle[this.name] ||
      this.name;
    document.querySelectorAll("button[data-mode]").forEach(b => {
      b.classList.toggle("active", b.dataset.mode === this.name);
    });
  }

  reload() {
    this.mode.unmount();
    if (CANVAS_MODES.has(this.name)) {
      this.resetCanvas();
      this.mode.mount(el.canvas);
    } else if (this.name === "onboard") {
      this.mode.mount(el.onboard);
    } else {
      this.mode.mount(el.cards);
    }
    toggleTimelineHud(this.name === "timeline");
    renderPanel();
  }

  resetCanvas() {
    const next = document.createElement("canvas");
    next.id = "scene";
    next.tabIndex = 0;
    el.canvas.replaceWith(next);
    el.canvas = next;
  }
}

// ─── WorkstreamsMode ──────────────────────────────────────────────────────────

class WorkstreamsMode {
  constructor() {
    this.container = null;
    this.workstreams = [];
    this.filtered = [];
    this.category = "all";
    this.sortBy = "relevance";
    this.view = "grid";
    this.expanded = new Set();
    this.globeRaf = 0;
    this.globeTick = 0;
    this.globePts = [];
    this.onClick = ev => this.handleClick(ev);
    this.onChange = ev => this.handleChange(ev);
  }

  async mount(container) {
    this.container = container;
    this.renderLoading();
    el.draft.placeholder = "Ask Iris about your files…";
    try {
      let resp = {};
      const fromCache = state.workstreams.length > 0;
      if (!fromCache) {
        try {
          resp = await getJson("/api/workstreams");
        } catch (_) {}
      }
      const data = Array.isArray(resp) ? resp : (resp.workstreams || []);
      this.workstreams = data.length ? data : state.workstreams;
      this.workstreams = this.workstreams.map(ws => this.normWorkstream(ws));
      state.workstreams = this.workstreams;
      this.filtered = this.workstreams;
      if (!this.workstreams.length) {
        state.manager.switch("onboard");
        return;
      }
      await refreshHomeData();
      await refreshAudiences();
      this.updateStatusBar(this.workstreams);
      this.renderShell();
      this.applyFilters();
      this.renderInspector(this.workstreams);
      // If Gemma naming is still in progress, poll until ready then refresh
      if (!fromCache && !resp.cached) this.pollForGemmaNames();
    } catch (err) {
      this.container.innerHTML = `<div class="cards-empty">
        <p>Could not load workstreams: ${esc(err.message)}</p></div>`;
    }
  }

  unmount() {
    this.stopMiniGlobe();
    if (this.container) {
      this.container.removeEventListener("click", this.onClick);
      this.container.removeEventListener("change", this.onChange);
      this.container.innerHTML = "";
    }
  }

  renderLoading() {
    this.container.innerHTML = `<div class="cards-loading">
      <span class="pulse-dot"></span>
      <span>Loading workstreams…</span>
    </div>`;
  }

  renderShell() {
    this.container.innerHTML = `
      <section class="home-header">
        <h1 class="home-title">Home</h1>
        <p class="home-sub">Optic analyzes your digital footprint to
          surface what humans and algorithms infer about you.</p>
      </section>
      <section class="home-controls">
        <div class="cluster-tabs" id="clusterTabs">
          ${this.tab("all", "All clusters")}
          ${this.tab("identity", "Identity")}
          ${this.tab("work", "Work & skills")}
          ${this.tab("life", "Life")}
          ${this.tab("relations", "Relations")}
          ${this.tab("behavior", "Behavior")}
        </div>
        <div class="ws-controls-row">
          <label class="ws-sort-wrap">Sort:
            <select id="wsSort" class="ws-sort">
              ${this.sortOpt("relevance", "Relevance")}
              ${this.sortOpt("recent", "Recent")}
              ${this.sortOpt("size", "Size")}
              ${this.sortOpt("az", "A–Z")}
            </select>
          </label>
          <div class="ws-view" role="group" aria-label="View">
            <button class="ws-view-btn${this.view === "grid" ? " active" : ""}"
              data-view="grid" title="Grid view">⊞</button>
            <button class="ws-view-btn${this.view === "list" ? " active" : ""}"
              data-view="list" title="List view">☰</button>
          </div>
        </div>
      </section>
      <section id="wsList" class="cards-grid"></section>`;
    this.container.removeEventListener("click", this.onClick);
    this.container.removeEventListener("change", this.onChange);
    this.container.addEventListener("click", this.onClick);
    this.container.addEventListener("change", this.onChange);
  }

  tab(id, label) {
    const cls = id === this.category ? "cluster-tab active" : "cluster-tab";
    return `<button class="${cls}" data-tab="${id}">${label}</button>`;
  }

  sortOpt(id, label) {
    const sel = id === this.sortBy ? " selected" : "";
    return `<option value="${id}"${sel}>${label}</option>`;
  }

  updateStatusBar(cards) {
    const total = cards.reduce((s, c) => s + (c.file_count || 0), 0);
    if (!el.counts) return;
    el.counts.textContent = `${cards.length} workstreams · ${
      total.toLocaleString()} files`;
  }

  async renderInspector(cards) {
    const hd = state.homeData || {};
    const narr = this.narratives(cards);
    const total = Number(hd.signal_count || state.nodes.length || 0);
    const narrN = Number(hd.workstreams_count || cards.length || 0);
    const audRows = state.audiences.length ? state.audiences : defaultAudiences();
    const audN = audRows.length || 4;
    const ago = esc(hd.last_analyzed_ago || "—");
    const sum = state.homeSummary || hd.iris_summary || null;
    const sumTxt = sum ? esc(String(sum).slice(0, 170)) :
      "Iris summary is generating from your current run.";
    const quick = audRows.slice(0, 3).map(a => {
      const s = Number(a.score || 0);
      const tier = s >= 80 ? "High" : s >= 70 ? "Moderate" : "Watch";
      return `<div class="rail-quick-row">
        <span class="rail-quick-name">${esc(a.name || a.id || "Audience")}</span>
        <span class="rail-quick-score">${s}</span>
        <span class="rail-quick-tier">${tier}</span>
      </div>`;
    }).join("");
    el.inspector.innerHTML = `
      <section class="rail-card">
        <h2 class="rail-head">Your digital self</h2>
        <p class="rail-sub">Private · local · on-device</p>
        <div class="panel-globe"><canvas id="homeGlobe" width="176"
          height="176"></canvas></div>
        <div class="rail-metric-grid">
          <div class="rail-metric"><span>Files indexed</span><b>${
            total.toLocaleString()}</b></div>
          <div class="rail-metric"><span>Topics found</span><b>${narrN}</b></div>
          <div class="rail-metric"><span>Last analyzed</span><b>${ago}</b></div>
        </div>
      </section>
      <section class="rail-card">
        <div class="rail-card-head">
          <h3>Top inferred narratives</h3>
          <button class="rail-link" type="button">View all</button>
        </div>
        <div class="rail-chip-row">${narr.map(t =>
          `<span class="rail-chip">${esc(t)}</span>`).join("")}</div>
      </section>
      <section class="rail-card">
        <div class="rail-card-head">
          <h3>Iris quick view</h3>
          <button class="rail-link" type="button"
            data-mode-jump="iris">Go to Iris</button>
        </div>
        ${quick}
      </section>
      <section class="rail-card">
        <h3>Next best action</h3>
        <p class="muted">${sumTxt}</p>
        <button class="rail-cta" type="button"
          data-mode-jump="simulations">Run simulation</button>
      </section>`;
    const jump = el.inspector.querySelector("[data-mode-jump]");
    if (jump) {
      jump.addEventListener("click", () => {
        state.manager.switch(jump.dataset.modeJump);
      });
    }
    const iris = el.inspector.querySelector("[data-mode-jump='iris']");
    if (iris) {
      iris.addEventListener("click", () => {
        state.manager.switch("iris");
      });
    }
    const globe = el.inspector.querySelector("#homeGlobe");
    if (globe) this.startMiniGlobe(globe, Math.min(200, total || 120));
    updateStatusIndex(hd);
  }

  async pollForGemmaNames() {
    // Show subtle "naming in progress" indicator in status bar
    const orig = el.counts ? el.counts.textContent : "";
    if (el.counts) el.counts.textContent = `${orig} · naming…`;
    for (let i = 0; i < 20; i++) {
      await new Promise(r => setTimeout(r, 3000));
      try {
        const resp = await getJson("/api/workstreams");
        if (resp.cached) {
          const data = (resp.workstreams || []).map(ws =>
            this.normWorkstream(ws));
          this.workstreams = data;
          state.workstreams = data;
          this.filtered = data;
          this.updateStatusBar(data);
          this.applyFilters();
          this.renderInspector(data);
          return;
        }
      } catch (_) {}
    }
    // Polling timed out — remove indicator
    this.updateStatusBar(this.workstreams);
  }

  renderCards() {
    const list = this.container.querySelector("#wsList");
    if (!list) return;
    list.className = this.view === "list"
      ? "cards-grid view-list"
      : "cards-grid";
    if (!this.filtered.length) {
      list.innerHTML = `<div class="cards-empty">
        No workstreams match your filter.</div>`;
      return;
    }
    list.innerHTML = `${
      this.filtered.map(ws => this.cardHTML(ws)).join("")
    }`;
  }

  cardHTML(ws) {
    const pct = this.confPct(ws);
    const cat = this.wsCategory(ws);
    const level = pct >= 80 ? "high" : pct >= 50 ? "medium" : "low";
    const emoji = this.emoji(ws, cat);
    const iconBg = this.catColor(cat);
    const summary = esc((ws.summary || "").replace(/^"|"$/g, ""));
    const expanded = this.expanded.has(this.wsId(ws));
    const rows = this.evidenceRows(ws, expanded ? 99 : 3).map(row =>
      `<div class="ws-ev-row ws-evidence-row">
        <span class="ws-ev-ico ws-ev-icon">${row.icon}</span>
        <span class="ws-ev-name">${esc(row.name)}</span>
        <span class="ws-ev-loc">${esc(row.loc)}</span>
      </div>`).join("");
    return `<article class="ws-card ws-card2${expanded ? " ws-expanded" : ""}"
      data-ws-id="${esc(this.wsId(ws))}">
      <div class="ws-card-header ws-card2-head">
        <div class="ws-icon ws-icon2" style="background:${iconBg}">
          <span class="ws-emoji">${emoji}</span>
        </div>
        <div class="ws-card-body ws-title-block">
          <div class="ws-name ws-name2">${esc(ws.name || "Untitled")}</div>
          <div class="ws-conf2">
            <span class="ws-conf-dot ${level}"></span>
            <span class="ws-conf-pct">${pct}%</span>
          </div>
        </div>
      </div>
      <p class="ws-desc ws-desc2">${summary}</p>
      <div class="ws-evidence ws-evidence-block">
        <div class="ws-ev-label ws-evidence-label">Top evidence</div>
        ${rows || `<div class="ws-ev-row"><span class="ws-ev-name" style="color:var(--subtle)">No indexed files yet</span></div>`}
      </div>
      <div class="ws-footer ws-actions2">
        <button class="ws-act-link ws-action-primary" data-action="map">
          → View in map</button>
        <div class="ws-actions2-ghost">
          <button class="ws-act-btn ws-action-ghost" data-action="inspect">
            ${expanded ? "Collapse" : "Evidence"}</button>
          <button class="ws-act-btn ws-action-ghost" data-action="simulate">
            Simulate</button>
        </div>
      </div>
    </article>`;
  }

  viewFiles(id) {
    const ws = this.workstreams.find(w => (w.id || w.name || "") === id);
    if (!ws) return;
    this.focusCluster(ws);
  }

  showInGraph(id) {
    const ws = this.workstreams.find(w => (w.id || w.name || "") === id);
    if (!ws) return;
    this.focusCluster(ws);
  }

  _panToCluster(clusterId) {
    const mode = state.manager.mode;
    if (!mode?.cam) return;
    const id = String(clusterId || "");
    if (!id) return;
    if (typeof mode.focusCluster === "function" && mode.focusCluster(id)) {
      return;
    }
    const clusterNodes = state.nodes.filter(n =>
      String(n.cluster || "") === id);
    if (!clusterNodes.length) return;
    const pts = clusterNodes.map(n => ({
      x: Number.isFinite(n.x) ? n.x : (n.pcaX || 0),
      y: Number.isFinite(n.y) ? n.y : (n.pcaY || 0),
    }));
    const xs = pts.map(p => p.x);
    const ys = pts.map(p => p.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const cx = (minX + maxX) * 0.5;
    const cy = (minY + maxY) * 0.5;
    const w = mode.canvas?.getBoundingClientRect().width || 480;
    const h = mode.canvas?.getBoundingClientRect().height || 320;
    const span = Math.max(72, maxX - minX, maxY - minY);
    const room = Math.max(220, Math.min(w, h) - 112);
    mode.cam.x = -cx;
    mode.cam.y = -cy;
    mode.cam.k = clamp(room / span, 0.8, 3.4);
  }

  onSearch(q) {
    if (!this.workstreams.length) return;
    state.q = (q || "").toLowerCase();
    this.applyFilters();
  }

  onKey() {}
  draw() {}

  handleChange(ev) {
    const sel = ev.target.closest("#wsSort");
    if (!sel) return;
    this.sortBy = sel.value || "relevance";
    this.applyFilters();
  }

  handleClick(ev) {
    const tab = ev.target.closest("[data-tab]");
    if (tab) {
      this.category = tab.dataset.tab || "all";
      this.renderShell();
      this.applyFilters();
      return;
    }
    const view = ev.target.closest("[data-view]");
    if (view) {
      this.view = view.dataset.view || "grid";
      this.renderShell();
      this.applyFilters();
      return;
    }
    const btn = ev.target.closest("[data-action]");
    const card = ev.target.closest("[data-ws-id]");
    if (!btn || !card) return;
    const id = card.dataset.wsId;
    const ws = this.workstreams.find(w => this.wsId(w) === id);
    if (!ws) return;
    const act = btn.dataset.action;
    if (act === "map") return this.focusCluster(ws);
    if (act === "inspect") {
      this.toggleExpanded(this.wsId(ws));
      return;
    }
    if (act === "simulate") {
      openAudienceModal(this.audienceIdFor(ws));
    }
  }

  applyFilters() {
    const vals = this.workstreams.filter(ws => this.keepCategory(ws) &&
      this.keepSearch(ws));
    this.filtered = this.sort(vals);
    this.renderCards();
    if (!el.counts) return;
    const total = this.filtered.reduce((s, c) => s + (c.file_count || 0), 0);
    if (this.filtered.length < this.workstreams.length || state.q) {
      el.counts.textContent = `${this.filtered.length} of ${
        this.workstreams.length} workstreams · ${total.toLocaleString()} files`;
      return;
    }
    this.updateStatusBar(this.workstreams);
  }

  sort(vals) {
    const rows = [...vals];
    if (this.sortBy === "recent") {
      rows.sort((a, b) => this.newestMtime(b) - this.newestMtime(a));
      return rows;
    }
    if (this.sortBy === "size") {
      rows.sort((a, b) => this.totalSize(b) - this.totalSize(a));
      return rows;
    }
    if (this.sortBy === "az") {
      rows.sort((a, b) => (a.name || "").localeCompare(b.name || ""));
      return rows;
    }
    rows.sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
    return rows;
  }

  keepCategory(ws) {
    if (this.category === "all") return true;
    return this.wsCategory(ws) === this.category;
  }

  keepSearch(ws) {
    if (!state.q) return true;
    const text = `${ws.name || ""} ${ws.summary || ""} ${
      (ws.topics || []).join(" ")} ${(ws.folders || []).join(" ")}`.toLowerCase();
    return text.includes(state.q);
  }

  wsCategory(ws) {
    const map = {
      identity: ["identity", "personal", "bio", "profile", "resume", "cv",
        "social"],
      work: ["work", "code", "project", "career", "job", "research", "skill",
        "learning"],
      life: ["photo", "travel", "health", "fitness", "journal", "diary",
        "life"],
      relations: ["contact", "email", "message", "social", "people", "friend",
        "family"],
      behavior: ["habit", "finance", "purchase", "browse", "download",
        "activity"],
    };
    const text = this.topicText(ws);
    let best = "work";
    let max = 0;
    Object.entries(map).forEach(([cat, keys]) => {
      const hit = keys.reduce((s, k) => s + (text.includes(k) ? 1 : 0), 0);
      if (hit > max) {
        max = hit;
        best = cat;
      }
    });
    return max > 0 ? best : "work";
  }

  topicText(ws) {
    return `${(ws.topics || []).join(" ")} ${(ws.name || "")} ${
      ws.summary || ""}`.toLowerCase();
  }

  confPct(ws) {
    const raw = Number(ws.confidence || 0) * 100;
    return Math.round(clamp(raw, 0, 100));
  }

  catColor(cat) {
    const map = {
      identity: "rgba(99,102,241,.15)",
      work: "rgba(59,130,246,.15)",
      life: "rgba(16,185,129,.15)",
      relations: "rgba(236,72,153,.15)",
      behavior: "rgba(245,158,11,.15)",
    };
    return map[cat] || "rgba(124,130,145,.15)";
  }

  emoji(ws, cat) {
    const text = this.topicText(ws);
    if (text.includes("research") || text.includes("learning")) return "📚";
    if (text.includes("career") || text.includes("work")) return "💼";
    if (text.includes("social") || text.includes("message")) return "💬";
    if (text.includes("finance") || text.includes("purchase")) return "💳";
    if (text.includes("write") || text.includes("journal")) return "✍️";
    if (text.includes("photo") || text.includes("image")) return "📷";
    if (text.includes("travel")) return "✈️";
    if (text.includes("health") || text.includes("fitness")) return "🏃";
    if (text.includes("code") || text.includes("project")) return "💻";
    if (text.includes("config") || text.includes("system")) return "⚙️";
    const by = {
      identity: "📁",
      work: "💼",
      life: "📷",
      relations: "💬",
      behavior: "💳",
    };
    return by[cat] || "📁";
  }

  evidenceRows(ws, maxRows = 3) {
    const vals = (ws.key_files || []).map(v => this.normFile(v)).filter(v =>
      !!v.path);
    return vals.slice(0, maxRows).map(v => ({
      icon: this.fileIcon(v.path),
      name: displayName(base(v.path), v.path),
      loc: this.fileFolder(v.path),
      mtime: num(v.mtime || 0),
    }));
  }

  normFile(v) {
    if (!v) return { path: "" };
    if (typeof v === "string") return { path: v };
    if (typeof v === "object") {
      return {
        path: v.path || v.file || "",
        size: num(v.size || 0),
        mtime: num(v.mtime || 0),
      };
    }
    return { path: "" };
  }

  fileFolder(path) {
    const parts = String(path || "").split("/").filter(Boolean);
    return parts.length > 1 ? parts[parts.length - 2] : "root";
  }

  fileIcon(path) {
    const p = String(path || "").toLowerCase();
    if (p.endsWith(".pdf") || p.endsWith(".doc") || p.endsWith(".docx")) {
      return "📄";
    }
    if (p.endsWith(".md") || p.endsWith(".txt")) return "📝";
    if (p.endsWith(".json") || p.endsWith(".yml") || p.endsWith(".toml")) {
      return "⚙️";
    }
    if (p.endsWith(".js") || p.endsWith(".ts") || p.endsWith(".py")) return "💻";
    if (p.startsWith("http")) return "🔗";
    return "📄";
  }

  wsId(ws) {
    return String(ws.id || ws.cluster || ws.name || "");
  }

  toggleExpanded(id) {
    if (this.expanded.has(id)) this.expanded.delete(id);
    else this.expanded.add(id);
    this.renderCards();
  }

  focusCluster(ws) {
    const id = this.wsId(ws);
    state.q = "";
    el.search.value = "";
    state.highlightCluster = id;
    state.wsFocusCluster = id;
    const nodes = state.nodes.filter(n => n.cluster === id && !n.noise);
    state.selected = nodes.sort((a, b) => b.degree - a.degree)[0] || null;
    state.manager.switch("topology");
    this._panToCluster(id);
    state.manager?.mode?.draw?.();
    renderPanel();
  }

  audienceIdFor(ws) {
    const cat = this.wsCategory(ws);
    if (cat === "behavior") return "lender";
    if (cat === "relations" || cat === "life") return "stranger";
    if (cat === "identity") return "recruiter";
    const text = this.topicText(ws);
    if (text.includes("finance")) return "lender";
    if (text.includes("startup") || text.includes("invest")) return "investor";
    return "recruiter";
  }

  newestMtime(ws) {
    const fromFiles = this.evidenceRows(ws, 40).map(v => v.mtime || 0);
    const fromNodes = state.nodes.filter(n => n.cluster === this.wsId(ws))
      .map(n => n.mtime || 0);
    return Math.max(ws.mtime || 0, ...fromFiles, ...fromNodes, 0);
  }

  totalSize(ws) {
    const size = Number(ws.size || 0);
    if (size > 0) return size;
    const fromNodes = state.nodes.filter(n => n.cluster === this.wsId(ws))
      .reduce((s, n) => s + (n.size || 0), 0);
    if (fromNodes > 0) return fromNodes;
    return (ws.key_files || []).reduce((s, v) => {
      const row = this.normFile(v);
      return s + (row.size || 0);
    }, 0);
  }

  normWorkstream(ws) {
    const next = { ...ws };
    if (!Array.isArray(next.key_files)) next.key_files = [];
    if (!Array.isArray(next.topics)) next.topics = [];
    if (!Array.isArray(next.folders)) next.folders = [];
    return next;
  }

  // Topics that are filesystem noise — never show as narrative labels
  static NARRATIVE_NOISE = new Set([
    "name","path","users","ahmedm","home","root","local","mobile","desktop",
    "downloads","documents","inbox","library","folder","true","false","null",
    "none","https","http","www","com","org","json","html","default","used",
    "found","size","type","date","conf","pio","bash","text","file","files",
    "copy","temp","misc","version","new","old","stinct","ass","sch","pcb",
  ]);

  // Map topic keywords → human-readable narrative labels
  static NARRATIVE_MAP = [
    [/(python|numpy|pandas|scipy|torch|sklearn|fastapi|flask|django|anyio|trio|pytest)/i, "Python developer"],
    [/(swift|xcode|objc|appkit|uikit|cocoa|macos|ios)/i,                                 "Apple platform builder"],
    [/(kicad|pcb|schematic|circuit|board|eagle|arduino|platformio|embedded)/i,            "Electronics & hardware"],
    [/(scad|openscad|blender|stl|3d|cad|fusion|freecad)/i,                               "3D design & fabrication"],
    [/(ai|ml|llm|gpt|neural|model|embedding|vector|inference)/i,                          "AI & machine learning"],
    [/(code|engineer|software|develop|git|github|commit|deploy)/i,                        "Software engineer"],
    [/(research|learning|study|paper|article|essay|notes)/i,                              "Independent researcher"],
    [/(design|sketch|figma|ui|ux|interface|graphic|logo)/i,                              "Product & visual design"],
    [/(photo|camera|photography|landscape|portrait|raw)/i,                                "Photography"],
    [/(travel|city|architecture|urban|map|geography)/i,                                   "Urban explorer"],
    [/(music|audio|song|track|playlist|itunes|spotify)/i,                                 "Music lover"],
    [/(write|writing|journal|blog|story|novel|essay|draft)/i,                             "Writer"],
    [/(privacy|security|crypto|encrypt|vpn|risk)/i,                                       "Privacy conscious"],
    [/(finance|tax|invoice|budget|accounting|expense)/i,                                  "Financial planner"],
    [/(health|fitness|medical|nutrition|workout)/i,                                       "Health-focused"],
    [/(game|gaming|unity|unreal|godot)/i,                                                 "Game developer"],
    [/(cloud|aws|gcp|azure|docker|kubernetes|devops)/i,                                   "Cloud & DevOps"],
  ];

  narratives(cards) {
    const hits = new Map();
    cards.forEach(ws => {
      const wt = Number(ws.confidence || 0.3);
      (ws.topics || []).concat(ws.name ? [ws.name] : []).forEach(raw => {
        const key = String(raw || "").toLowerCase().trim();
        if (!key || key.length < 3) return;
        if (WorkstreamsMode.NARRATIVE_NOISE.has(key)) return;
        hits.set(key, (hits.get(key) || 0) + wt);
      });
    });
    const sorted = [...hits.entries()].sort((a, b) => b[1] - a[1]);
    const labels = new Set();
    for (const [k] of sorted) {
      const label = this.narrativeLabel(k);
      if (label) labels.add(label);
      if (labels.size >= 5) break;
    }
    return labels.size ? [...labels] : [];
  }

  narrativeLabel(key) {
    for (const [pattern, label] of WorkstreamsMode.NARRATIVE_MAP) {
      if (pattern.test(key)) return label;
    }
    return null; // don't show unrecognised topics
  }

  startMiniGlobe(canvas, count = 120) {
    this.stopMiniGlobe();
    if (window.THREE) {
      try {
        const w = canvas.width || 210;
        const h = canvas.height || 210;
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(42, w / h, 1, 800);
        camera.position.z = 170;
        const renderer = new THREE.WebGLRenderer({
          canvas,
          alpha: true,
          antialias: true,
        });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.setSize(w, h, false);
        const n = Math.max(40, Math.min(200, count || 120));
        const pos = new Float32Array(n * 3);
        const col = new Float32Array(n * 3);
        const vals = Object.values(palette);
        for (let i = 0; i < n; i++) {
          const u = Math.random() * 2 - 1;
          const a = Math.random() * Math.PI * 2;
          const rr = Math.sqrt(1 - u * u);
          const idx = i * 3;
          pos[idx] = rr * Math.cos(a) * 58;
          pos[idx + 1] = u * 58;
          pos[idx + 2] = rr * Math.sin(a) * 58;
          const cc = new THREE.Color(vals[i % vals.length]);
          col[idx] = cc.r;
          col[idx + 1] = cc.g;
          col[idx + 2] = cc.b;
        }
        const geo = new THREE.BufferGeometry();
        geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
        geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
        const mat = new THREE.PointsMaterial({
          size: 3.2,
          vertexColors: true,
          transparent: true,
          opacity: 0.9,
          depthWrite: false,
        });
        const cloud = new THREE.Points(geo, mat);
        scene.add(cloud);
        const shell = new THREE.Mesh(
          new THREE.SphereGeometry(60, 22, 22),
          new THREE.MeshBasicMaterial({
            color: 0xffffff,
            transparent: true,
            opacity: 0.08,
            wireframe: true,
          }),
        );
        scene.add(shell);
        this.globeRenderer = renderer;
        this.globeScene = scene;
        this.globeCamera = camera;
        this.globeGeo = geo;
        this.globeMat = mat;
        this.globeShell = shell;
        this.globeCloud = cloud;
        const draw3d = () => {
          this.globeRaf = requestAnimationFrame(draw3d);
          cloud.rotation.y += 0.004;
          cloud.rotation.x = Math.sin(Date.now() * 0.00045) * 0.22;
          shell.rotation.y -= 0.002;
          renderer.render(scene, camera);
        };
        draw3d();
        return;
      } catch (_) {}
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const n = Math.max(40, Math.min(220, count || 120));
    this.globePts = [];
    for (let i = 0; i < n; i++) {
      const u = Math.random() * 2 - 1;
      const a = Math.random() * Math.PI * 2;
      const rr = Math.sqrt(1 - u * u);
      this.globePts.push({ x: rr * Math.cos(a), y: u, z: rr * Math.sin(a) });
    }
    const colors = Object.values(palette);
    const draw = () => {
      this.globeRaf = requestAnimationFrame(draw);
      this.globeTick += 0.008;
      const w = canvas.width;
      const h = canvas.height;
      const cx = w * 0.5;
      const cy = h * 0.5;
      const rad = Math.min(w, h) * 0.36;
      ctx.clearRect(0, 0, w, h);
      ctx.beginPath();
      ctx.arc(cx, cy, rad + 8, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(255,255,255,.34)";
      ctx.fill();
      this.globePts.forEach((p, idx) => {
        const c = Math.cos(this.globeTick);
        const s = Math.sin(this.globeTick);
        const x = p.x * c - p.z * s;
        const z = p.x * s + p.z * c;
        const y = p.y;
        const depth = (z + 1) * 0.5;
        const dot = 1 + depth * 2.2;
        const alpha = 0.28 + depth * 0.58;
        ctx.fillStyle = hexToRgba(colors[idx % colors.length], alpha);
        ctx.beginPath();
        ctx.arc(cx + x * rad, cy + y * rad, dot, 0, Math.PI * 2);
        ctx.fill();
      });
    };
    draw();
  }

  stopMiniGlobe() {
    if (this.globeRaf) {
      cancelAnimationFrame(this.globeRaf);
      this.globeRaf = 0;
    }
    this.globeGeo?.dispose?.();
    this.globeMat?.dispose?.();
    this.globeShell?.geometry?.dispose?.();
    this.globeShell?.material?.dispose?.();
    this.globeRenderer?.dispose?.();
    this.globeRenderer = null;
    this.globeScene = null;
    this.globeCamera = null;
    this.globeGeo = null;
    this.globeMat = null;
    this.globeShell = null;
    this.globeCloud = null;
  }
}

class IrisMode {
  constructor() {
    this.container = null;
    this.onClick = ev => this.click(ev);
    this.onSubmit = ev => this.submit(ev);
  }

  async mount(container) {
    this.container = container;
    await Promise.all([refreshHomeData(), refreshReport(), refreshStatus()]);
    this.render();
    this.container.addEventListener("click", this.onClick);
    this.container.addEventListener("submit", this.onSubmit);
  }

  unmount() {
    this.container?.removeEventListener("click", this.onClick);
    this.container?.removeEventListener("submit", this.onSubmit);
    if (this.container) this.container.innerHTML = "";
  }

  render() {
    const rep = state.report || {};
    const sum = state.homeSummary || state.homeData?.iris_summary || "";
    const files = Number(rep?.corpus?.total_files || state.nodes.length || 0);
    const rows = (state.workstreams || []).slice(0, 3).map((ws, idx) => {
      const pct = Math.max(8, 42 - idx * 11);
      const conf = Math.max(56, Math.round((Number(ws.confidence || 0)) * 100));
      const ev = (ws.key_files || []).slice(0, 2).map(f =>
        `<span class="rail-chip">${esc(base(f.path || f || ""))}</span>`).join("");
      return `<div class="iris-theme-row">
        <div class="iris-theme-main">
          <div class="iris-theme-title">${esc(ws.name || "Theme")}</div>
          <p>${esc(ws.summary || "Signals grouped from your current run context.")}</p>
        </div>
        <div class="iris-theme-stats">
          <div><span>Coverage</span><b>${pct}%</b></div>
          <div><span>Confidence</span><b>${conf}%</b></div>
        </div>
        <div class="iris-theme-evidence">${ev || "<span class='rail-chip'>Evidence pending</span>"}</div>
      </div>`;
    }).join("");
    this.container.innerHTML = `<section class="route-wrap iris-page">
      <header class="route-head">
        <h1>Iris</h1>
        <p>Analytical intelligence for your digital universe.</p>
      </header>
      <div class="route-row iris-inline-tabs">
        <button class="route-cta" data-imode="report" data-ask="Run a full corpus report with top risks and repairs.">Report</button>
        <button class="route-btn" data-imode="entity" data-ask="What does the selected evidence reveal?">Entity</button>
        <button class="route-btn" data-imode="compare" data-ask="Compare the strongest themes in this run.">Compare</button>
        <button class="route-btn" data-imode="audience" data-ask="How do audiences read this run?">Audience</button>
        <button class="route-btn" data-imode="audit" data-ask="Generate a complete identity audit for this run.">Audit</button>
        <button class="route-btn" data-mode-jump="simulations">Open simulations</button>
      </div>
      <section class="route-card">
        <div class="iris-query-bubble">
          What are the main themes in my documents over the last 90 days?
        </div>
        <div class="iris-content">${sum ? (window.marked ?
          mdHtml(sum) : esc(sum)) :
          "Summary will appear after scan and report generation."}</div>
      </section>
      <section class="route-card">
        <h3>Top themes (${files.toLocaleString()} files analyzed)</h3>
        <div class="iris-theme-list">${rows || "<p class='muted'>No themes yet.</p>"}</div>
      </section>
      <section class="route-row">
        <button class="route-btn" data-ask="Drill into work and projects.">Drill into Work & Projects</button>
        <button class="route-btn" data-ask="Compare with previous 90 days.">Compare previous 90 days</button>
        <button class="route-btn" data-ask="Export this report.">Export this report</button>
      </section>
      <section class="route-card iris-inline-chat">
        <div class="iris-dialog-scroll" id="irisDialogScroll">
          <div class="iris-inline-empty">Ask Iris anything about your data.</div>
        </div>
        <div class="iris-inline-prompts">
          <button class="route-btn route-btn--sm" type="button" data-ask="What changed the most this week?">What changed most?</button>
          <button class="route-btn route-btn--sm" type="button" data-ask="Find duplicate or low-signal files I should archive.">What to delete?</button>
          <button class="route-btn route-btn--sm" type="button" data-ask="Summarize this run for a recruiter in 5 bullets.">Recruiter summary</button>
        </div>
        <form id="irisInlineForm" class="iris-inline-form">
          <input id="irisInlineInput" class="route-input"
            placeholder="Ask Iris anything about your data…" autocomplete="off">
          <button class="route-cta" type="submit">Send</button>
        </form>
      </section>
    </section>`;
  }

  click(ev) {
    const btn = ev.target.closest("button");
    if (!btn) return;
    if (btn.dataset.modeJump) {
      state.manager.switch(btn.dataset.modeJump);
      return;
    }
    const ask = btn.dataset.ask;
    if (!ask) return;
    const mode = btn.dataset.imode || "report";
    state.irisMode = mode;
    syncIrisModeTabs();
    updateIrisChips(mode);
    updateEntityBar(mode);
    streamIris(ask);
  }

  submit(ev) {
    const form = ev.target.closest("#irisInlineForm");
    if (!form) return;
    ev.preventDefault();
    const input = form.querySelector("#irisInlineInput");
    const q = String(input?.value || "").trim();
    if (!q) return;
    if (input) input.value = "";
    streamIris(q);
  }

  onSearch() {}
  onKey() {}
  draw() {}
}

class VaultMode {
  constructor() {
    this.container = null;
    this.analytics = {
      duplicates: [],
      stale: [],
      largest: [],
    };
    this.onClick = ev => this.click(ev);
  }

  async mount(container) {
    this.container = container;
    await Promise.all([refreshHomeData(), refreshStatus(), refreshReport()]);
    await this.loadAnalytics();
    this.render();
    this.container.addEventListener("click", this.onClick);
  }

  unmount() {
    this.container?.removeEventListener("click", this.onClick);
    if (this.container) this.container.innerHTML = "";
  }

  async loadAnalytics() {
    try {
      const [dups, stale, large] = await Promise.all([
        getJson("/api/analyze?kind=duplicates&limit=8"),
        getJson("/api/analyze?kind=old_downloads&limit=10"),
        getJson("/api/analyze?kind=largest&limit=10"),
      ]);
      this.analytics.duplicates = Array.isArray(dups?.groups) ? dups.groups : [];
      this.analytics.stale = Array.isArray(stale?.items) ? stale.items : [];
      this.analytics.largest = Array.isArray(large?.items) ? large.items : [];
    } catch (_) {
      this.analytics = { duplicates: [], stale: [], largest: [] };
    }
  }

  duplicateWaste(group) {
    const items = Array.isArray(group?.items) ? group.items : [];
    if (items.length < 2) return 0;
    const sizes = items.map(x => Number(x?.size || 0)).filter(n => n > 0);
    if (sizes.length < 2) return 0;
    return Math.max(0, sizes.reduce((a, b) => a + b, 0) - Math.min(...sizes));
  }

  render() {
    const home = state.homeData || {};
    const stat = state.status || {};
    const stage = stat?.progress?.stage || "idle";
    const st = stat?.progress?.stage_state || "ready";
    const run = stat?.last_run || "none";
    const files = Number(home.file_count || state.nodes.length || 0);
    const size = Number(home.total_size || 0);
    const rows = (this.analytics.largest.length ? this.analytics.largest :
      [...state.nodes]).slice(0, 10).map(n => {
      const cat = n.category || category({ path: n.path || "", ext: n.ext || "" });
      return `<tr>
      <td>${esc(base(n.path))}</td>
      <td>${esc(cat)}</td>
      <td>${humanSize(n.size || 0)}</td>
      <td>${esc(relTime(n.mtime))}</td>
      <td>✓</td>
    </tr>`;
    }).join("");
    const cats = ["Documents", "Code", "Images", "Video", "Other", "System"]
      .map(name => ({
        name,
        count: state.nodes.filter(n => n.category === name).length,
      }))
      .sort((a, b) => b.count - a.count);
    const catRows = cats.filter(c => c.count > 0).slice(0, 6);
    const dupGroups = this.analytics.duplicates.slice(0, 4);
    const dupRows = dupGroups.map(g => `<div class="vault-dup-row">
      <b>${esc(String(g.name || "").slice(0, 42))}</b>
      <span>${Number(g.count || 0)} copies · ${humanSize(this.duplicateWaste(g))} reclaimable</span>
      <button class="route-btn route-btn--sm" data-act="duplicates">Review</button>
    </div>`).join("");
    const dupWaste = this.analytics.duplicates.reduce((sum, g) =>
      sum + this.duplicateWaste(g), 0);
    const staleN = this.analytics.stale.length;
    this.container.innerHTML = `<section class="route-wrap">
      <header class="route-head">
        <h1>Vault (Local) <span class="rail-chip">On-device</span></h1>
        <p>Your private files and sources. Everything stays on this machine.</p>
      </header>
      <section class="route-row vault-toolbar">
        <button class="route-btn">All folders</button>
        <button class="route-btn">Type: All</button>
        <button class="route-btn">Size: Any</button>
        <button class="route-btn">Modified: Any time</button>
        <button class="route-btn">Source: All</button>
        <button class="route-btn">More filters</button>
        <input class="route-input" placeholder="Search in vault…">
      </section>
      <section class="vault-layout">
        <aside class="vault-tree route-card">
          <div class="vault-tree-row active"><span>All files</span><b>${
            files.toLocaleString()}</b></div>
          ${catRows.map(c => `<div class="vault-tree-row"><span>${esc(c.name)}</span><b>${c.count.toLocaleString()}</b></div>`).join("")}
          <div class="vault-tree-row"><span>Stale downloads</span><b>${staleN.toLocaleString()}</b></div>
          <button class="route-btn route-btn--sm">+ Add folder to vault</button>
        </aside>
        <section class="route-card vault-main">
          <div class="route-kpis">
            <div><span>Files indexed</span><b>${files.toLocaleString()}</b></div>
            <div><span>Total size</span><b>${humanSize(size)}</b></div>
            <div><span>Pipeline</span><b>${esc(stage)} · ${esc(st)}</b></div>
          </div>
          <table class="vault-table">
            <thead><tr><th>Name</th><th>Type</th><th>Size</th><th>Modified</th><th>In index</th></tr></thead>
            <tbody>${rows || "<tr><td colspan='5'>No files in view.</td></tr>"}</tbody>
          </table>
        </section>
      </section>
      <section class="route-card">
        <div class="route-card-head">
          <h3>Duplicate groups</h3>
          <span class="muted">${humanSize(dupWaste)} reclaimable</span>
        </div>
        <div class="vault-dup-list">${dupRows || "<p class='muted'>No duplicate groups found.</p>"}</div>
      </section>
      <div class="route-row">
        <button class="route-cta" data-act="reindex">Re-index Vault</button>
        <button class="route-btn" data-act="duplicates">Find Duplicates</button>
        <button class="route-btn" data-act="stale">Find Stale</button>
        <button class="route-btn" data-act="impact">Narrative Impact</button>
      </div>
      <section class="route-card">
        <h3>Last run</h3>
        <p class="muted">Run: ${esc(run)} · queue depth: ${Number(stat.queue_depth || 0)}</p>
      </section>
    </section>`;
  }

  click(ev) {
    const btn = ev.target.closest("button[data-act]");
    if (!btn) return;
    const act = btn.dataset.act;
    if (act === "reindex") return state.manager.switch("onboard");
    if (act === "duplicates") return analyzeLocal("duplicates");
    if (act === "stale") return analyzeLocal("old_downloads");
    if (act === "impact") {
      const run = state.status?.last_run || state.run || "latest";
      return streamIris(`Given run ${run}, explain how vault cleanup would change audience perception and what to remove first.`);
    }
  }

  onSearch() {}
  onKey() {}
  draw() {}
}

class AudiencesMode {
  constructor() {
    this.container = null;
    this.onClick = ev => this.click(ev);
  }

  async mount(container) {
    this.container = container;
    await refreshAudiences(true);
    this.render();
    this.container.addEventListener("click", this.onClick);
  }

  unmount() {
    this.container?.removeEventListener("click", this.onClick);
    if (this.container) this.container.innerHTML = "";
  }

  render() {
    const rows = state.audiences.length ? state.audiences : defaultAudiences();
    const cards = rows.map((r, idx) => `<article class="aud-card${
      idx === 0 ? " active" : ""}" data-aud="${esc(r.id)}">
      <h3>${esc(r.icon || "👤")} ${esc(r.name || r.id || "Audience")}</h3>
      <div class="aud-score-row">
        <b>${Number(r.score || 0)}%</b>
        <span>${Number(r.score || 0) >= 75 ? "High" : "Moderate"} confidence</span>
      </div>
      <p>${esc(r.summary || "")}</p>
      <span class="rail-chip">${idx % 2 ? "Execution" : "Technical"} signal</span>
    </article>`).join("");
    const cmpRows = rows.map(row => {
      const highs = Array.isArray(row.highlights) ? row.highlights : [];
      const risks = Array.isArray(row.risks) ? row.risks : [];
      const hi = highs.length ? highs.slice(0, 2).join(" · ") : "—";
      const rk = risks.length ? risks.slice(0, 2).join(" · ") : "—";
      return `<tr>
        <td>${esc(row.name || row.id || "Audience")}</td>
        <td>${Number(row.score || 0)}%</td>
        <td>${esc(hi)}</td>
        <td>${esc(rk)}</td>
      </tr>`;
    }).join("");
    this.container.innerHTML = `<section class="route-wrap">
      <header class="route-head">
        <h1>Audiences</h1>
        <p>See how different people and systems will perceive you.</p>
      </header>
      <div class="route-row">
        <button class="route-btn">Manage audiences</button>
        <button class="route-cta" data-aud="${esc(rows[0]?.id || "recruiter")}">Simulate top audience</button>
        <button class="route-btn" data-mode-jump="simulations">Open simulations</button>
      </div>
      <section class="aud-grid">${cards}</section>
      <section class="route-card">
        <div class="route-card-head">
          <h3>Audience comparison (live)</h3>
          <span class="muted">Based on current run graph</span>
        </div>
        <table class="aud-table">
          <thead><tr><th>Audience</th><th>Score</th><th>Top signals</th><th>Risks</th></tr></thead>
          <tbody>${cmpRows || "<tr><td colspan='4'>No audience data yet.</td></tr>"}</tbody>
        </table>
      </section>
      <section class="route-row">
        <button class="route-btn">+ Add custom audience</button>
        <button class="route-btn" data-mode-jump="simulations">Open simulations</button>
        <button class="route-cta">Export audience brief</button>
      </section>
    </section>`;
  }

  click(ev) {
    const jump = ev.target.closest("button[data-mode-jump]");
    if (jump) return state.manager.switch(jump.dataset.modeJump);
    const card = ev.target.closest("[data-aud]");
    if (card && !ev.target.closest("button[data-aud]")) {
      openAudienceModal(card.dataset.aud || "recruiter");
      return;
    }
    const btn = ev.target.closest("button[data-aud]");
    if (!btn) return;
    openAudienceModal(btn.dataset.aud || "recruiter");
  }

  onSearch() {}
  onKey() {}
  draw() {}
}

class SimulationsMode {
  constructor() {
    this.container = null;
    this.onClick = ev => this.click(ev);
    this.lastEval = null;
  }

  async mount(container) {
    this.container = container;
    await Promise.all([refreshAudiences(), refreshSimulations(true)]);
    this.render();
    this.container.addEventListener("click", this.onClick);
  }

  unmount() {
    this.container?.removeEventListener("click", this.onClick);
    if (this.container) this.container.innerHTML = "";
  }

  wsRows() {
    const mode = state.manager?.modes?.workstreams;
    const rows = mode?.workstreams?.length ? mode.workstreams : state.workstreams;
    return rows.slice(0, 16);
  }

  shiftStats() {
    const ref = this.lastEval || state.simulations[0];
    if (!ref) {
      return { before: "--", after: "--", delta: "--", cls: "" };
    }
    const before = Number(ref.before_score ?? ref.after_score ?? 0);
    const after = Number(ref.after_score ?? 0);
    const delta = after - before;
    return {
      before: Math.round(before),
      after: Math.round(after),
      delta: fmtDelta(Math.round(delta)),
      cls: delta >= 0 ? "good" : "bad",
    };
  }

  render() {
    const aud = state.audiences.length ? state.audiences : defaultAudiences();
    const ws = this.wsRows();
    const shift = this.shiftStats();
    const checks = ws.map((w, idx) => `<div class="sim-var-row">
      <label class="sim-check">
        <input type="checkbox" value="${esc(String(w.id || w.name || ""))}"${
        idx < 3 ? " checked" : ""}>
        <span>${esc(String(w.name || "Untitled"))}</span>
      </label>
      <div class="sim-slider">
        <span>Impact strength</span>
        <input type="range" min="1" max="10" value="${Math.max(4, 8 - idx)}">
      </div>
      <span class="sim-tier">${idx % 2 ? "Medium" : "High"}</span>
    </div>`).join("");
    const saved = state.simulations.map(s => `<div class="sim-saved-row">
      <span>${esc(s.name || "Scenario")}</span>
      <b>${Number(s.after_score || 0)} (${fmtDelta(s.delta)})</b>
    </div>`).join("") || `<p class="muted">No saved scenarios yet.</p>`;
    this.container.innerHTML = `<section class="route-wrap">
      <header class="route-head"><h1>Simulations</h1><p>Model how changes to your digital presence influence different audiences.</p></header>
      <div class="route-row">
        <button class="route-btn">Save scenario</button>
        <button class="route-btn">History</button>
        <button class="route-btn">Saved scenarios</button>
      </div>
      <section class="route-card">
        <div class="route-form-row">
          <input id="simName" placeholder="Scenario name" value="Identity uplift">
          <select id="simAudience">${aud.map(a => `<option value="${esc(a.id)}">${esc(a.name)}</option>`).join("")}</select>
        </div>
        <div class="sim-builder">${checks || "<p class='muted'>No workstreams loaded yet.</p>"}</div>
        <div class="route-row">
          <button class="route-cta" data-act="eval">Evaluate Scenario</button>
          <button class="route-btn" data-act="save">Save Scenario</button>
          <button class="route-btn" data-act="compare">Compare Last Two</button>
        </div>
        <div id="simResult" class="muted">Pick clusters, then evaluate.</div>
      </section>
      <section class="route-card">
        <h3>Projected perception shift</h3>
        <div class="sim-shift">
          <div><span>Before</span><b>${shift.before}</b></div>
          <div><span>After</span><b>${shift.after}</b></div>
          <div><span>Change</span><b class="${shift.cls}">${shift.delta}</b></div>
        </div>
      </section>
      <section class="route-card">
        <h3>Saved scenarios</h3>${saved}
      </section>
    </section>`;
  }

  payload() {
    const name = this.container.querySelector("#simName")?.value || "Scenario";
    const audience = this.container.querySelector("#simAudience")?.value || "recruiter";
    const ids = [...this.container.querySelectorAll(".sim-builder input:checked")]
      .map(inp => inp.value)
      .filter(Boolean);
    return {
      run: state.run,
      name: String(name).trim() || "Scenario",
      audience_id: audience,
      include_clusters: ids,
      exclude_clusters: [],
    };
  }

  showEval(rec, extra = "") {
    const out = this.container.querySelector("#simResult");
    if (!out) return;
    out.innerHTML = `Before: <b>${rec.before_score}</b> → After: <b>${rec.after_score}</b> (${fmtDelta(rec.delta)}) · CI ${rec.confidence_interval.low}-${rec.confidence_interval.high} ${extra}`;
  }

  async click(ev) {
    const btn = ev.target.closest("button[data-act]");
    if (!btn) return;
    const act = btn.dataset.act;
    if (act === "eval") {
      const out = await postJson("/api/simulations/evaluate", this.payload());
      this.lastEval = out.scenario;
      this.showEval(out.scenario);
      return;
    }
    if (act === "save") {
      const out = await postJson("/api/simulations/save", this.payload());
      this.lastEval = out.scenario;
      await refreshSimulations(true);
      this.render();
      this.showEval(out.scenario, "· saved");
      return;
    }
    if (act === "compare") {
      if (state.simulations.length < 2) {
        const out = this.container.querySelector("#simResult");
        if (out) out.textContent = "Need at least two saved scenarios to compare.";
        return;
      }
      const a = state.simulations[0];
      const b = state.simulations[1];
      const out = await postJson("/api/simulations/compare", {
        left_id: a.id, right_id: b.id,
      });
      const msg = `Compare ${a.name} vs ${b.name}: ${fmtDelta(out.delta.delta)} (${out.delta.before_score}→${out.delta.after_score})`;
      const box = this.container.querySelector("#simResult");
      if (box) box.textContent = msg;
    }
  }

  onSearch() {}
  onKey() {}
  draw() {}
}

class ExportsMode {
  constructor() {
    this.container = null;
    this.onClick = ev => this.click(ev);
  }

  async mount(container) {
    this.container = container;
    await Promise.all([refreshSettings(), this.refreshHistory()]);
    this.render();
    this.container.addEventListener("click", this.onClick);
  }

  unmount() {
    this.container?.removeEventListener("click", this.onClick);
    if (this.container) this.container.innerHTML = "";
  }

  async refreshHistory() {
    try {
      const out = await getJson("/api/exports/history");
      this.history = Array.isArray(out?.items) ? out.items : [];
    } catch (_) {
      this.history = [];
    }
  }

  render() {
    const red = !!(state.settings?.privacy?.redact_exports ?? true);
    const cards = [
      ["report", "Executive Report (PDF)",
        "Comprehensive narrative report with visuals and key insights."],
      ["audience", "Audience Snapshot",
        "Tailored summary for a specific audience perspective."],
      ["datapack", "Data Package (JSON)",
        "Raw signals and entities for technical consumption."],
      ["workstreams", "CSV Findings",
        "Structured findings for analysis in spreadsheets."],
    ].map(([id, title, sub], idx) => `<label class="exp-type-card${
      idx === 0 ? " active" : ""}">
      <input type="radio" name="expType" value="${id}"${
      idx === 0 ? " checked" : ""}>
      <div><b>${title}</b><p>${sub}</p></div>
    </label>`).join("");
    const rows = (this.history || []).map(r => `<div class="sim-saved-row">
      <span>${esc(r.kind)} · ${esc(String(r.run || "latest"))}</span>
      <b>${humanSize(Number(r.bytes || 0))}</b>
    </div>`).join("") || `<p class="muted">No exports yet.</p>`;
    this.container.innerHTML = `<section class="route-wrap">
      <header class="route-head"><h1>Exports</h1><p>Create and share reports, datasets, and analysis packages.</p></header>
      <section class="exp-type-grid">${cards}</section>
      <section class="exp-grid">
      <section class="route-card">
        <h3>Export configuration</h3>
        <div class="route-form-row">
          <select id="expKind">
            <option value="report">Report</option>
            <option value="workstreams">Workstreams</option>
            <option value="graph">Graph</option>
            <option value="datapack">Data Pack</option>
          </select>
          <input id="expDest" placeholder="Destination folder (optional)">
        </div>
        <div class="route-form-row">
          <label class="sim-check"><input type="checkbox" id="expRedact"${red ? " checked" : ""}><span>Redact sensitive patterns</span></label>
          <label class="sim-check"><input type="checkbox" id="expAllow"><span>Allow risky export</span></label>
        </div>
        <div class="route-card">
          <h3>Included modules</h3>
          <div class="rail-chip-row">
            <span class="rail-chip">Identity universe</span>
            <span class="rail-chip">Iris insights</span>
            <span class="rail-chip">Audience views</span>
            <span class="rail-chip">Evidence samples</span>
            <span class="rail-chip">Activity timeline</span>
          </div>
        </div>
      </section>
      <section class="route-card">
        <div class="route-card-head">
          <h3>Preview — Executive Report (PDF)</h3>
          <button class="route-btn route-btn--sm">Full preview</button>
        </div>
        <div class="exp-preview">
          <div class="exp-preview-head">Optic · Your Digital Identity Report</div>
          <div class="exp-preview-art"></div>
          <div class="exp-preview-pages">
            <span class="rail-chip">Cover</span>
            <span class="rail-chip">Executive summary</span>
            <span class="rail-chip">Identity universe</span>
            <span class="rail-chip">Top signals</span>
          </div>
        </div>
        <div class="route-row">
          <button class="route-cta" data-act="export">Generate Export</button>
          <button class="route-btn" data-act="refresh">Refresh History</button>
        </div>
        <div id="expMsg" class="muted">Ready.</div>
      </section>
      </section>
      <section class="route-card"><h3>Export history</h3>${rows}</section>
    </section>`;
    this.container.querySelectorAll("input[name='expType']").forEach(r => {
      r.addEventListener("change", () => {
        const v = r.value;
        const kind = this.container.querySelector("#expKind");
        if (kind) kind.value = v === "audience" ? "report" : v;
        this.container.querySelectorAll(".exp-type-card").forEach(card => {
          card.classList.toggle("active", card.contains(r) && r.checked);
        });
      });
    });
  }

  async click(ev) {
    const btn = ev.target.closest("button[data-act]");
    if (!btn) return;
    if (btn.dataset.act === "refresh") {
      await this.refreshHistory();
      this.render();
      return;
    }
    if (btn.dataset.act !== "export") return;
    const kind = this.container.querySelector("#expKind")?.value || "report";
    const dest = this.container.querySelector("#expDest")?.value || "";
    const redact = !!this.container.querySelector("#expRedact")?.checked;
    const allow = !!this.container.querySelector("#expAllow")?.checked;
    const msg = this.container.querySelector("#expMsg");
    if (msg) msg.textContent = "Exporting…";
    try {
      const out = await postJson("/api/exports", {
        run: state.run, kind, dest_dir: dest, redact, allow_risky: allow,
      });
      await this.refreshHistory();
      this.render();
      const next = this.container.querySelector("#expMsg");
      if (next) next.textContent = `Saved: ${out.export.path}`;
    } catch (err) {
      if (msg) msg.textContent = `Export failed: ${apiMsg(err)}`;
    }
  }

  onSearch() {}
  onKey() {}
  draw() {}
}

class SettingsMode {
  constructor() {
    this.container = null;
    this.workspace = null;
    this.members = [];
    this.invites = [];
    this.integrations = null;
    this.jobs = null;
    this.oauthEvents = null;
    this.connections = null;
    this.syncState = null;
    this.billing = null;
    this.usage = null;
    this.onClick = ev => this.click(ev);
  }

  async mount(container) {
    this.container = container;
    await Promise.all([
      refreshSettings(true),
      refreshStatus(true),
      this.refreshOps(),
      this.refreshBackups(),
      this.refreshWorkspace(),
      this.refreshMembers(),
      this.refreshInvites(),
      this.refreshIntegrations(),
      this.refreshJobs(),
      this.refreshOauthEvents(),
      this.refreshConnections(),
      this.refreshSyncState(),
      this.refreshBilling(),
      this.refreshUsage(),
    ]);
    this.render();
    this.container.addEventListener("click", this.onClick);
  }

  unmount() {
    this.container?.removeEventListener("click", this.onClick);
    if (this.container) this.container.innerHTML = "";
  }

  async refreshOps() {
    try {
      this.ops = await getJson("/api/ops/health");
    } catch (_) {
      this.ops = null;
    }
  }

  async refreshBackups() {
    try {
      const out = await getJson("/api/ops/backups");
      this.backups = Array.isArray(out?.items) ? out.items : [];
    } catch (_) {
      this.backups = [];
    }
  }

  async refreshWorkspace() {
    try {
      this.workspace = await getJson("/api/workspace");
    } catch (_) {
      this.workspace = null;
    }
  }

  async refreshMembers() {
    try {
      const out = await getJson("/api/workspace/members");
      this.members = Array.isArray(out?.members) ? out.members : [];
    } catch (_) {
      this.members = [];
    }
  }

  async refreshInvites() {
    try {
      const out = await getJson("/api/workspace/invites");
      this.invites = Array.isArray(out?.invites) ? out.invites : [];
    } catch (_) {
      this.invites = [];
    }
  }

  async refreshIntegrations() {
    try {
      this.integrations = await getJson("/api/integrations/state");
    } catch (_) {
      this.integrations = null;
    }
  }

  async refreshJobs() {
    try {
      this.jobs = await getJson("/api/integrations/jobs");
    } catch (_) {
      this.jobs = null;
    }
  }

  async refreshOauthEvents() {
    try {
      this.oauthEvents = await getJson("/api/integrations/oauth/events");
    } catch (_) {
      this.oauthEvents = null;
    }
  }

  async refreshConnections() {
    try {
      this.connections = await getJson("/api/integrations/connections");
    } catch (_) {
      this.connections = null;
    }
  }

  async refreshSyncState() {
    try {
      this.syncState = await getJson("/api/integrations/sync/state");
    } catch (_) {
      this.syncState = null;
    }
  }

  async refreshBilling() {
    try {
      this.billing = await getJson("/api/billing");
    } catch (_) {
      this.billing = null;
    }
  }

  async refreshUsage() {
    try {
      this.usage = await getJson("/api/billing/usage");
    } catch (_) {
      this.usage = null;
    }
  }

  render() {
    const set = state.settings || {};
    const scan = set.scan_rules || {};
    const prv = set.privacy || {};
    const intg = this.integrations?.integrations || {};
    const email = intg.email || {};
    const social = intg.social || {};
    const channels = intg.channels || {};
    const cal = channels.calendar || {};
    const crm = channels.crm || {};
    const store = channels.storage || {};
    const chatops = channels.chatops || {};
    const auto = intg.automation || {};
    const syncAuto = auto.sync || {};
    const providers = social.providers || {};
    const px = providers.x || {};
    const bill = this.billing?.billing || {};
    const use = this.usage?.usage || {};
    const jobs = this.jobs || {};
    const evs = Array.isArray(this.oauthEvents?.items) ?
      this.oauthEvents.items : [];
    const conns = Array.isArray(this.connections?.items) ?
      this.connections.items : [];
    const syncItems = Array.isArray(this.syncState?.items) ?
      this.syncState.items : [];
    const ops = this.ops || {};
    const ws = this.workspace?.workspace || null;
    const role = String(ws?.role || "viewer");
    const bkp = (this.backups || []).map(x => `<option value="${esc(x.id)}">${esc(x.id)}</option>`).join("");
    const members = (this.members || []).slice(0, 8).map(m => `<div class="route-row">
      <span>${esc(m.name || m.email || "Member")}</span>
      <span class="rail-chip">${esc(m.role || "member")}</span>
    </div>`).join("") || `<p class="muted">No members yet.</p>`;
    const invites = (this.invites || []).slice(0, 6).map(m => `<div
      class="route-row"><span>${esc(m.email || "")}</span><span
      class="muted">${esc(m.status || "pending")}</span></div>`).join("") ||
      `<p class="muted">No pending invites.</p>`;
    const jRows = (jobs.queued || []).slice(-4).map(j => `<div
      class="route-row"><span>${esc(j.kind || "job")} · ${esc(j.id || "")}</span>
      <span class="muted">try ${Number(j.attempt || 0)}</span></div>`).join("") ||
      `<p class="muted">No queued jobs.</p>`;
    const oRows = evs.slice(-5).reverse().map(row => {
      const ts = Number(row.ts || 0);
      const at = ts > 0 ? new Date(ts * 1000).toLocaleTimeString() : "now";
      const detail = String(row.detail || "").trim();
      const hint = detail ? ` · ${esc(detail)}` : "";
      return `<div class="route-row"><span>${esc(row.event || "event")} · ` +
        `${esc(row.provider || "oauth")} · ${esc(at)}${hint}</span></div>`;
    }).join("") || `<p class="muted">No OAuth events yet.</p>`;
    const connRows = conns.slice(0, 8).map(row => {
      const tone = String(row.status || "") === "connected" ? "ok" : "warn";
      const sync = String(row.sync_status || "idle");
      const label = `${row.channel || "channel"}:${row.provider || "provider"}`;
      const hint = row.account ? ` · ${row.account}` : "";
      return `<div class="route-row"><span>${esc(label)}${esc(hint)}</span>
        <span class="rail-chip rail-chip-${tone}">${esc(sync)}</span></div>`;
    }).join("") || `<p class="muted">No integration connections yet.</p>`;
    const syncRows = syncItems.slice(0, 6).map(row => {
      const ts = Number(row.updated_at || 0);
      const at = ts > 0 ? new Date(ts * 1000).toLocaleTimeString() : "n/a";
      return `<div class="route-row"><span>${esc(
        `${row.channel}:${row.provider}`
      )} · ${esc(row.status || "idle")}</span><span class="muted">${esc(
        at
      )}</span></div>`;
    }).join("") || `<p class="muted">No sync state yet.</p>`;
    this.container.innerHTML = `<section class="route-wrap">
      <header class="route-head"><h1>Settings</h1><p>Control how Optic works on this device.</p></header>
      <section class="route-card">
        <h3>Profile & account</h3>
        <div class="route-form-row">
          <input id="setName" placeholder="Display name"
            value="${esc(set.profile?.display_name || "Alex Morgan")}">
          <input id="setDays" type="number" min="1" max="365"
            value="${Number(set.profile?.session_days || 30)}">
        </div>
        <div class="route-form-row">
          <input id="setQueue" type="number" min="1" value="${Number(scan.queue_cap || 6)}" title="queue cap">
          <input id="setRetry" type="number" min="0" value="${Number(scan.retry_max || 2)}" title="retry max">
          <input id="setBackoff" type="number" min="0.1" step="0.1" value="${Number(scan.backoff_s || 3)}" title="backoff seconds">
          <input id="setTimeout" type="number" min="30" value="${Number(scan.timeout_s || 300)}" title="timeout seconds">
        </div>
        <div class="route-row">
          <label class="sim-check"><input type="checkbox" id="setRedact"${prv.redact_exports ? " checked" : ""}><span>Redact sensitive data in exports</span></label>
          <label class="sim-check"><input type="checkbox" checked><span>On-device mode</span></label>
          <label class="sim-check"><input type="checkbox" checked><span>Smart scan</span></label>
        </div>
        <div class="route-card">
          <h3>Integrations</h3>
          <div class="rail-chip-row">
            <span class="rail-chip">iCloud Drive</span>
            <span class="rail-chip">Google Drive</span>
            <span class="rail-chip">Slack</span>
            <span class="rail-chip">GitHub</span>
          </div>
        </div>
        <div class="route-row">
          <button class="route-cta" data-act="save">Save Settings</button>
        </div>
        <div id="setMsg" class="muted">Ready.</div>
      </section>
      <section class="route-card">
        <h3>System health</h3>
        <p class="muted">Runs: ${Number(ops?.index?.runs_total || 0)} · Latest: ${esc(ops?.index?.latest_run || "none")} · Queue: ${Number(ops?.index?.status?.queue_depth || 0)}</p>
        <p class="muted">Storage free: ${humanSize(Number(ops?.storage?.free_bytes || 0))} · Model: ${esc(ops?.model?.model || "")}</p>
      </section>
      <section class="route-card">
        <h3>Workspace</h3>
        <p class="muted">Name: ${esc(ws?.name || "Not initialized")} · Role:
          ${esc(role)} · Members: ${Number(ws?.member_count || 0)}</p>
        <div class="route-form-row">
          <input id="wsName" placeholder="Workspace name"
            value="${esc(ws?.name || "Optic Workspace")}">
          <input id="wsSlug" placeholder="workspace-slug"
            value="${esc(ws?.slug || "optic-workspace")}">
        </div>
        <div class="route-row">
          <button class="route-btn" data-act="saveWorkspace">Save workspace</button>
          <button class="route-btn" data-act="reloadWorkspace">Refresh</button>
        </div>
        <div class="route-card">
          <h3>Team members</h3>
          ${members}
        </div>
        <div class="route-card">
          <h3>Invites</h3>
          <div class="route-form-row">
            <input id="wsInviteEmail" placeholder="teammate@example.com">
            <select id="wsInviteRole">
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
            <button class="route-btn" data-act="inviteMember">Invite</button>
          </div>
          ${invites}
        </div>
      </section>
      <section class="route-card">
        <h3>Growth channels (foundation)</h3>
        <div class="route-form-row">
          <label class="sim-check"><input type="checkbox"
            id="intEmailEnabled"${email.enabled ? " checked" : ""}><span>Email enabled</span></label>
          <label class="sim-check"><input type="checkbox"
            id="intSocialEnabled"${social.enabled ? " checked" : ""}><span>Social enabled</span></label>
        </div>
        <div class="route-form-row">
          <select id="intEmailProvider">
            ${["smtp","ses","sendgrid","resend"].map(p => `<option value="${p}"${String(email.provider || "smtp") === p ? " selected" : ""}>${p.toUpperCase()}</option>`).join("")}
          </select>
          <input id="intFromEmail" placeholder="noreply@yourdomain.com"
            value="${esc(email.from_email || "")}">
          <input id="intXHandle" placeholder="@brand"
            value="${esc(px.handle || "")}">
        </div>
        <div class="route-form-row">
          <input id="intXTokenRef" placeholder="x token ref"
            value="${esc(px.token_ref || "")}">
          <input id="intXSecret" type="password"
            placeholder="x access token (saved locally)">
          <button class="route-btn" data-act="saveXSecret">Save X token</button>
        </div>
        <div class="route-form-row">
          <select id="intSecretProvider">
            ${["x", "linkedin", "youtube", "tiktok", "instagram", "threads",
              "calendar_google", "calendar_outlook", "crm_hubspot",
              "crm_salesforce", "storage_drive", "storage_dropbox",
              "storage_onedrive", "chatops_slack", "chatops_discord",
              "email_google", "email_outlook", "webhook",
              "email"].map(p => `<option value="${p}">${
                esc(p.toUpperCase())
              }</option>`).join("")}
          </select>
          <input id="intSecretRef" placeholder="token ref">
          <input id="intSecretVal" type="password"
            placeholder="provider token / secret">
          <button class="route-btn" data-act="saveSecret">Save token</button>
        </div>
        <div class="route-form-row">
          <input id="intSmtpHost" placeholder="smtp host"
            value="${esc(email.smtp_host || "")}">
          <input id="intSmtpPort" type="number" min="1" max="65535"
            value="${Number(email.smtp_port || 587)}">
          <input id="intSmtpUser" placeholder="smtp user"
            value="${esc(email.smtp_user || "")}">
        </div>
        <div class="route-row">
          <label class="sim-check"><input type="checkbox"
            id="intSmtpSsl"${email.smtp_use_ssl ? " checked" : ""}>
            <span>SMTP SSL</span></label>
          <label class="sim-check"><input type="checkbox"
            id="intSmtpTls"${email.smtp_starttls !== false ? " checked" : ""}>
            <span>SMTP STARTTLS</span></label>
        </div>
        <div class="route-row">
          <button class="route-btn" data-act="saveIntegrations">Save channels</button>
          <button class="route-btn" data-act="refreshJobs">Refresh jobs</button>
        </div>
        <div class="route-card">
          <h3>Future channels</h3>
          <div class="route-form-row">
            <label class="sim-check"><input type="checkbox"
              id="intCalEnabled"${cal.enabled ? " checked" : ""}>
              <span>Calendar</span></label>
            <select id="intCalProvider">
              ${["google", "outlook"].map(p => `<option value="${p}"${String(cal.provider || "google") === p ? " selected" : ""}>${p.toUpperCase()}</option>`).join("")}
            </select>
            <input id="intCalAccount" placeholder="account id/email"
              value="${esc(cal.account || "")}">
            <input id="intCalTokenRef" placeholder="token ref"
              value="${esc(cal.token_ref || "")}">
          </div>
          <div class="route-form-row">
            <label class="sim-check"><input type="checkbox"
              id="intCrmEnabled"${crm.enabled ? " checked" : ""}>
              <span>CRM</span></label>
            <select id="intCrmProvider">
              ${["hubspot", "salesforce"].map(p => `<option value="${p}"${String(crm.provider || "hubspot") === p ? " selected" : ""}>${p.toUpperCase()}</option>`).join("")}
            </select>
            <input id="intCrmAccount" placeholder="account id"
              value="${esc(crm.account || "")}">
            <input id="intCrmTokenRef" placeholder="token ref"
              value="${esc(crm.token_ref || "")}">
          </div>
          <div class="route-form-row">
            <label class="sim-check"><input type="checkbox"
              id="intStoreEnabled"${store.enabled ? " checked" : ""}>
              <span>Storage</span></label>
            <select id="intStoreProvider">
              ${["drive", "dropbox", "onedrive"].map(p => `<option value="${p}"${String(store.provider || "drive") === p ? " selected" : ""}>${p.toUpperCase()}</option>`).join("")}
            </select>
            <input id="intStoreAccount" placeholder="workspace id"
              value="${esc(store.account || "")}">
            <input id="intStoreTokenRef" placeholder="token ref"
              value="${esc(store.token_ref || "")}">
          </div>
          <div class="route-form-row">
            <label class="sim-check"><input type="checkbox"
              id="intChatopsEnabled"${chatops.enabled ? " checked" : ""}>
              <span>ChatOps</span></label>
            <select id="intChatopsProvider">
              ${["slack", "discord"].map(p => `<option value="${p}"${String(chatops.provider || "slack") === p ? " selected" : ""}>${p.toUpperCase()}</option>`).join("")}
            </select>
            <input id="intChatopsAccount" placeholder="#channel / server"
              value="${esc(chatops.account || "")}">
            <input id="intChatopsTokenRef" placeholder="token ref"
              value="${esc(chatops.token_ref || "")}">
          </div>
          <div class="route-form-row">
            <label class="sim-check"><input type="checkbox"
              id="intSyncEnabled"${syncAuto.enabled ? " checked" : ""}>
              <span>Auto sync</span></label>
            <input id="intSyncInterval" type="number" min="5" max="1440"
              value="${Number(syncAuto.interval_min || 30)}">
          </div>
          <div class="route-row">
            <button class="route-btn" data-act="connectCalendarOauth">
              Connect Calendar OAuth
            </button>
            <button class="route-btn" data-act="connectChatopsOauth">
              Connect ChatOps OAuth
            </button>
            <button class="route-btn" data-act="connectStorageOauth">
              Connect Storage OAuth
            </button>
            <button class="route-btn" data-act="refreshOauthToken">
              Refresh selected token
            </button>
            <button class="route-btn danger" data-act="revokeOauthToken">
              Revoke selected token
            </button>
          </div>
        </div>
        <div class="route-row">
          <button class="route-btn" data-act="queueDigest">Queue email digest</button>
          <button class="route-btn" data-act="queuePost">Queue social post</button>
          <button class="route-btn" data-act="queueCalSync">Queue calendar sync</button>
          <button class="route-btn" data-act="queueCrmSync">Queue CRM sync</button>
        </div>
        <div class="route-row">
          <button class="route-btn" data-act="queueStoreSync">Queue storage sync</button>
          <button class="route-btn" data-act="queueChatopsPost">Queue ChatOps post</button>
        </div>
        <div class="route-card">
          <h3>Automation queue</h3>
          <p class="muted">Queued: ${Number(jobs.queue_depth || 0)} · Done:
            ${Number((jobs.done || []).length)} · Dead:
            ${Number((jobs.dead || []).length)}</p>
          <div class="route-form-row">
            <select id="intReplayKind">
              <option value="">All replayable</option>
              <option value="email">Email</option>
              <option value="social">Social</option>
              <option value="channel">Channel</option>
            </select>
            <input id="intReplayLimit" type="number" min="1" max="20"
              value="8">
            <button class="route-btn" data-act="previewReplay">
              Preview replay
            </button>
            <button class="route-btn" data-act="runReplay">
              Replay dead jobs
            </button>
            <button class="route-btn" data-act="refreshOauthEvents">
              Refresh OAuth events
            </button>
            <button class="route-btn" data-act="refreshConnections">
              Refresh connections
            </button>
          </div>
          ${jRows}
          <div class="route-card">
            <h3>OAuth events</h3>
            ${oRows}
          </div>
          <div class="route-card">
            <h3>Connection health</h3>
            ${connRows}
          </div>
          <div class="route-card">
            <h3>Sync state</h3>
            ${syncRows}
          </div>
        </div>
      </section>
      <section class="route-card">
        <h3>Billing & entitlements</h3>
        <div class="route-form-row">
          <select id="billPlan">
            ${["free","pro","team","enterprise"].map(p => `<option value="${p}"${String(bill.plan || "free") === p ? " selected" : ""}>${p.toUpperCase()}</option>`).join("")}
          </select>
          <input id="billSeats" type="number" min="1" value="${Number(
            bill.seats || 1
          )}">
          <button class="route-btn" data-act="saveBilling">Save plan</button>
        </div>
        <div class="route-row">
          <button class="route-btn" data-act="checkoutBilling">
            Upgrade checkout
          </button>
          <button class="route-btn" data-act="portalBilling">
            Open billing portal
          </button>
        </div>
        <div class="route-row">
          <span class="muted">Status: ${esc(String(bill.status || "active"))}</span>
          <span class="muted">Files: ${Number(use.files || 0).toLocaleString()}</span>
          <span class="muted">API hits: ${Number(use.api_hits || 0).toLocaleString()}</span>
        </div>
      </section>
      <section class="route-card">
        <h3>Backups and danger zone</h3>
        <div class="route-form-row">
          <button class="route-btn" data-act="backup">Backup now</button>
          <select id="setRestoreSel">${bkp}</select>
          <button class="route-btn" data-act="restore">Restore</button>
        </div>
        <div class="route-row">
          <button class="route-btn danger" data-act="clearDead">Clear Dead Letters</button>
          <button class="route-btn danger" data-act="resetSummary">Reset Home Summary</button>
        </div>
      </section>
    </section>`;
  }

  payload() {
    return {
      settings: {
        profile: {
          display_name: this.container.querySelector("#setName")?.value || "",
          session_days: Number(this.container.querySelector("#setDays")?.value || 30),
        },
        scan_rules: {
          queue_cap: Number(this.container.querySelector("#setQueue")?.value || 6),
          retry_max: Number(this.container.querySelector("#setRetry")?.value || 2),
          backoff_s: Number(this.container.querySelector("#setBackoff")?.value || 3),
          timeout_s: Number(this.container.querySelector("#setTimeout")?.value || 300),
        },
        privacy: {
          redact_exports: !!this.container.querySelector("#setRedact")?.checked,
        },
      },
    };
  }

  queueIdem(kind, payload) {
    const row = payload && typeof payload === "object" ? payload : {};
    const channel = String(row.channel || row.provider || "core");
    const action = String(row.action || row.subject || kind || "job");
    const bucket = new Date().toISOString().slice(0, 16);
    return `ui_${kind}_${channel}_${action}_${bucket}`
      .replace(/[^A-Za-z0-9_.:-]/g, "_")
      .slice(0, 120);
  }

  replayReq(dryRun) {
    const kind = this.container.querySelector("#intReplayKind")?.value || "";
    const lim = Number(this.container.querySelector("#intReplayLimit")
      ?.value || 8);
    const body = {
      confirm: "REPLAY",
      limit: Math.max(1, Math.min(20, lim || 8)),
      dry_run: !!dryRun,
    };
    if (kind) body.kind = kind;
    return body;
  }

  async click(ev) {
    const btn = ev.target.closest("button[data-act]");
    if (!btn) return;
    const act = btn.dataset.act;
    const msg = this.container.querySelector("#setMsg");
    if (act === "reloadWorkspace") {
      await Promise.all([
        this.refreshWorkspace(),
        this.refreshMembers(),
        this.refreshInvites(),
      ]);
      this.render();
      const next = this.container.querySelector("#setMsg");
      if (next) next.textContent = "Workspace refreshed.";
      return;
    }
    if (act === "saveWorkspace") {
      try {
        const name = this.container.querySelector("#wsName")?.value || "";
        const slug = this.container.querySelector("#wsSlug")?.value || "";
        await postJson("/api/workspace", { name, slug });
        await this.refreshWorkspace();
        this.render();
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = "Workspace saved.";
      } catch (err) {
        if (msg) msg.textContent = `Workspace save failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "inviteMember") {
      try {
        const email = this.container.querySelector("#wsInviteEmail")?.value ||
          "";
        const role = this.container.querySelector("#wsInviteRole")?.value ||
          "member";
        await postJson("/api/workspace/invites", { email, role });
        await this.refreshInvites();
        this.render();
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = "Invite created.";
      } catch (err) {
        if (msg) msg.textContent = `Invite failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "saveIntegrations") {
      try {
        const emailEnabled = !!this.container.querySelector(
          "#intEmailEnabled"
        )?.checked;
        const socialEnabled = !!this.container.querySelector(
          "#intSocialEnabled"
        )?.checked;
        const emailProvider = this.container.querySelector(
          "#intEmailProvider"
        )?.value || "smtp";
        const fromEmail = this.container.querySelector("#intFromEmail")?.value
          || "";
        const smtpHost = this.container.querySelector("#intSmtpHost")?.value
          || "";
        const smtpPort = Number(this.container.querySelector("#intSmtpPort")
          ?.value || 587);
        const smtpUser = this.container.querySelector("#intSmtpUser")?.value
          || "";
        const smtpSsl = !!this.container.querySelector("#intSmtpSsl")?.checked;
        const smtpTls = !!this.container.querySelector("#intSmtpTls")?.checked;
        const xHandle = this.container.querySelector("#intXHandle")?.value ||
          "";
        const calEnabled = !!this.container.querySelector(
          "#intCalEnabled"
        )?.checked;
        const crmEnabled = !!this.container.querySelector(
          "#intCrmEnabled"
        )?.checked;
        const storeEnabled = !!this.container.querySelector(
          "#intStoreEnabled"
        )?.checked;
        const chatopsEnabled = !!this.container.querySelector(
          "#intChatopsEnabled"
        )?.checked;
        const syncEnabled = !!this.container.querySelector(
          "#intSyncEnabled"
        )?.checked;
        const syncInterval = Number(this.container.querySelector(
          "#intSyncInterval"
        )?.value || 30);
        const syncChannels = [];
        if (calEnabled) syncChannels.push("calendar");
        if (crmEnabled) syncChannels.push("crm");
        if (storeEnabled) syncChannels.push("storage");
        if (chatopsEnabled) syncChannels.push("chatops");
        await postJson("/api/integrations/state", {
          integrations: {
            email: {
              enabled: emailEnabled,
              provider: emailProvider,
              from_email: fromEmail,
              smtp_host: smtpHost,
              smtp_port: smtpPort,
              smtp_user: smtpUser,
              smtp_use_ssl: smtpSsl,
              smtp_starttls: smtpTls,
            },
            social: {
              enabled: socialEnabled,
              providers: {
                x: {
                  enabled: socialEnabled,
                  handle: xHandle,
                  token_ref: this.container.querySelector("#intXTokenRef")
                    ?.value || "",
                },
              },
            },
            channels: {
              calendar: {
                enabled: calEnabled,
                provider: this.container.querySelector("#intCalProvider")
                  ?.value || "google",
                account: this.container.querySelector("#intCalAccount")
                  ?.value || "",
                token_ref: this.container.querySelector("#intCalTokenRef")
                  ?.value || "",
              },
              crm: {
                enabled: crmEnabled,
                provider: this.container.querySelector("#intCrmProvider")
                  ?.value || "hubspot",
                account: this.container.querySelector("#intCrmAccount")
                  ?.value || "",
                token_ref: this.container.querySelector("#intCrmTokenRef")
                  ?.value || "",
              },
              storage: {
                enabled: storeEnabled,
                provider: this.container.querySelector("#intStoreProvider")
                  ?.value || "drive",
                account: this.container.querySelector("#intStoreAccount")
                  ?.value || "",
                token_ref: this.container.querySelector("#intStoreTokenRef")
                  ?.value || "",
              },
              chatops: {
                enabled: chatopsEnabled,
                provider: this.container.querySelector("#intChatopsProvider")
                  ?.value || "slack",
                account: this.container.querySelector("#intChatopsAccount")
                  ?.value || "",
                token_ref: this.container.querySelector("#intChatopsTokenRef")
                  ?.value || "",
              },
            },
            automation: {
              sync: {
                enabled: syncEnabled,
                interval_min: Math.max(5, Math.min(1440, syncInterval || 30)),
                channels: syncChannels,
              },
            },
          },
        });
        await Promise.all([
          this.refreshIntegrations(),
          this.refreshConnections(),
        ]);
        this.render();
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = "Channels saved.";
      } catch (err) {
        if (msg) msg.textContent = `Channel save failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "saveXSecret") {
      try {
        const token_ref = this.container.querySelector("#intXTokenRef")?.value
          || "";
        const secret = this.container.querySelector("#intXSecret")?.value
          || "";
        await postJson("/api/integrations/secrets", {
          provider: "x",
          token_ref,
          secret,
        });
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = "X token saved.";
      } catch (err) {
        if (msg) msg.textContent = `Secret save failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "saveSecret") {
      try {
        const provider = this.container.querySelector("#intSecretProvider")
          ?.value || "";
        const token_ref = this.container.querySelector("#intSecretRef")
          ?.value || "";
        const secret = this.container.querySelector("#intSecretVal")
          ?.value || "";
        await postJson("/api/integrations/secrets", {
          provider,
          token_ref,
          secret,
        });
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = `${provider} token saved.`;
      } catch (err) {
        if (msg) msg.textContent = `Secret save failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "connectCalendarOauth") {
      try {
        const prv = this.container.querySelector("#intCalProvider")?.value ||
          "google";
        const map = {
          google: "calendar_google",
          outlook: "calendar_outlook",
        };
        const provider = map[prv] || "";
        if (!provider) throw new Error("Unsupported calendar provider.");
        const token_ref = this.container.querySelector("#intCalTokenRef")
          ?.value || `${provider}_main`;
        const out = await postJson("/api/integrations/oauth/start", {
          provider,
          token_ref,
        });
        const url = String(out.auth_url || "").trim();
        if (!url) throw new Error("OAuth URL missing.");
        window.open(url, "_blank", "noopener,noreferrer");
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = "OAuth flow opened for Calendar.";
      } catch (err) {
        if (msg) msg.textContent = `OAuth start failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "connectStorageOauth") {
      try {
        const prv = this.container.querySelector("#intStoreProvider")?.value ||
          "drive";
        const map = {
          drive: "storage_drive",
          onedrive: "storage_onedrive",
        };
        const provider = map[prv] || "";
        if (!provider) throw new Error("OAuth not available for provider.");
        const token_ref = this.container.querySelector("#intStoreTokenRef")
          ?.value || `${provider}_main`;
        const out = await postJson("/api/integrations/oauth/start", {
          provider,
          token_ref,
        });
        const url = String(out.auth_url || "").trim();
        if (!url) throw new Error("OAuth URL missing.");
        window.open(url, "_blank", "noopener,noreferrer");
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = "OAuth flow opened for Storage.";
      } catch (err) {
        if (msg) msg.textContent = `OAuth start failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "connectChatopsOauth") {
      try {
        const prv = this.container.querySelector("#intChatopsProvider")
          ?.value || "slack";
        const provider = prv === "slack" ? "chatops_slack" : "";
        if (!provider) throw new Error("ChatOps OAuth currently supports Slack only.");
        const token_ref = this.container.querySelector("#intChatopsTokenRef")
          ?.value || "chatops_slack_main";
        const out = await postJson("/api/integrations/oauth/start", {
          provider,
          token_ref,
        });
        const url = String(out.auth_url || "").trim();
        if (!url) throw new Error("OAuth URL missing.");
        window.open(url, "_blank", "noopener,noreferrer");
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = "OAuth flow opened for ChatOps.";
      } catch (err) {
        if (msg) msg.textContent = `OAuth start failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "refreshOauthToken") {
      try {
        const provider = this.container.querySelector("#intSecretProvider")
          ?.value || "";
        const token_ref = this.container.querySelector("#intSecretRef")
          ?.value || "";
        if (!provider || !token_ref) throw new Error("Choose provider + token ref.");
        const out = await postJson("/api/integrations/oauth/refresh", {
          provider,
          token_ref,
        });
        const next = this.container.querySelector("#setMsg");
        const ts = Number(out.expires_at || 0);
        if (next) next.textContent = ts > 0
          ? `Token refreshed. Expires: ${new Date(ts * 1000).toLocaleString()}`
          : "Token refreshed.";
      } catch (err) {
        if (msg) msg.textContent = `OAuth refresh failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "revokeOauthToken") {
      try {
        const provider = this.container.querySelector("#intSecretProvider")
          ?.value || "";
        const token_ref = this.container.querySelector("#intSecretRef")
          ?.value || "";
        if (!provider || !token_ref) throw new Error("Choose provider + token ref.");
        await postJson("/api/integrations/oauth/revoke", {
          provider,
          token_ref,
          revoke_remote: true,
        });
        await Promise.all([
          this.refreshIntegrations(),
          this.refreshOauthEvents(),
          this.refreshConnections(),
        ]);
        this.render();
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = "Token revoked.";
      } catch (err) {
        if (msg) msg.textContent = `OAuth revoke failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "refreshJobs") {
      await Promise.all([this.refreshJobs(), this.refreshSyncState()]);
      this.render();
      const next = this.container.querySelector("#setMsg");
      if (next) next.textContent = "Job queue refreshed.";
      return;
    }
    if (act === "refreshOauthEvents") {
      await Promise.all([
        this.refreshOauthEvents(),
        this.refreshConnections(),
      ]);
      this.render();
      const next = this.container.querySelector("#setMsg");
      if (next) next.textContent = "OAuth events refreshed.";
      return;
    }
    if (act === "refreshConnections") {
      await Promise.all([
        this.refreshConnections(),
        this.refreshSyncState(),
      ]);
      this.render();
      const next = this.container.querySelector("#setMsg");
      if (next) next.textContent = "Connections refreshed.";
      return;
    }
    if (act === "previewReplay") {
      try {
        const out = await postJson(
          "/api/integrations/jobs/replay",
          this.replayReq(true),
        );
        const cnt = Number(out.requested || 0);
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = `Replay preview ready: ${cnt} candidate(s).`;
      } catch (err) {
        if (msg) msg.textContent = `Replay preview failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "runReplay") {
      try {
        const out = await postJson(
          "/api/integrations/jobs/replay",
          this.replayReq(false),
        );
        await this.refreshJobs();
        this.render();
        const next = this.container.querySelector("#setMsg");
        const ok = Number(out.accepted_count || 0);
        const skip = Array.isArray(out.skipped) ? out.skipped.length : 0;
        if (next) next.textContent = `Replay queued: ${ok}, skipped: ${skip}.`;
      } catch (err) {
        if (msg) msg.textContent = `Replay failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "queueDigest") {
      try {
        const to = this.container.querySelector("#intFromEmail")?.value ||
          "team@local";
        const rep = state.report || await refreshReport(true);
        const corpus = rep?.corpus || {};
        const topWs = (state.workstreams || []).slice(0, 3)
          .map(w => `- ${w.name || "Untitled"} (${Number(w.file_count || 0)})`)
          .join("\n");
        const body = [
          `Run: ${state.run || "latest"}`,
          `Files indexed: ${Number(corpus.total_files || 0).toLocaleString()}`,
          `Corpus size: ${humanSize(Number(corpus.total_bytes || 0))}`,
          `Signals this week: ${Number(corpus.recent_week || 0).toLocaleString()}`,
          topWs ? `Top workstreams:\n${topWs}` : "Top workstreams: none yet",
        ].join("\n");
        await postJson("/api/integrations/jobs", {
          kind: "email",
          payload: {
            to,
            subject: "Optic daily digest",
            body,
          },
          idempotency_key: this.queueIdem("email", {
            to,
            subject: "Optic daily digest",
          }),
        });
        await this.refreshJobs();
        this.render();
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = "Email digest job queued.";
      } catch (err) {
        if (msg) msg.textContent = `Queue failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "queuePost") {
      try {
        const handle = this.container.querySelector("#intXHandle")?.value
          || "@optic";
        const token_ref = this.container.querySelector("#intXTokenRef")?.value
          || "";
        const rep = state.report || await refreshReport(true);
        const files = Number(rep?.corpus?.total_files || state.nodes.length || 0);
        const topAud = (state.audiences && state.audiences.length) ?
          state.audiences[0] : null;
        const sig = topAud ? `${topAud.name}: ${Number(topAud.score || 0)}%` :
          "signal baseline pending";
        const content = `Optic update: ${files.toLocaleString()} files indexed. ` +
          `${sig}. Run ${state.run || "latest"}.`;
        await postJson("/api/integrations/jobs", {
          kind: "social",
          payload: {
            provider: "x",
            account: handle,
            content,
            token_ref,
          },
          idempotency_key: this.queueIdem("social", {
            provider: "x",
            account: handle,
            action: "post",
          }),
        });
        await this.refreshJobs();
        this.render();
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = "Social post job queued.";
      } catch (err) {
        if (msg) msg.textContent = `Queue failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "queueCalSync") {
      try {
        await postJson("/api/integrations/jobs", {
          kind: "channel",
          payload: {
            channel: "calendar",
            provider: this.container.querySelector("#intCalProvider")
              ?.value || "google",
            account: this.container.querySelector("#intCalAccount")
              ?.value || "",
            token_ref: this.container.querySelector("#intCalTokenRef")
              ?.value || "",
            action: "sync_events",
            data: { window_days: 14 },
          },
          idempotency_key: this.queueIdem("channel", {
            channel: "calendar",
            provider: this.container.querySelector("#intCalProvider")
              ?.value || "google",
            action: "sync_events",
          }),
        });
        await this.refreshJobs();
        this.render();
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = "Calendar sync job queued.";
      } catch (err) {
        if (msg) msg.textContent = `Queue failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "queueCrmSync") {
      try {
        await postJson("/api/integrations/jobs", {
          kind: "channel",
          payload: {
            channel: "crm",
            provider: this.container.querySelector("#intCrmProvider")
              ?.value || "hubspot",
            account: this.container.querySelector("#intCrmAccount")
              ?.value || "",
            token_ref: this.container.querySelector("#intCrmTokenRef")
              ?.value || "",
            action: "sync_contacts",
            data: { include_companies: true },
          },
          idempotency_key: this.queueIdem("channel", {
            channel: "crm",
            provider: this.container.querySelector("#intCrmProvider")
              ?.value || "hubspot",
            action: "sync_contacts",
          }),
        });
        await this.refreshJobs();
        this.render();
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = "CRM sync job queued.";
      } catch (err) {
        if (msg) msg.textContent = `Queue failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "queueStoreSync") {
      try {
        await postJson("/api/integrations/jobs", {
          kind: "channel",
          payload: {
            channel: "storage",
            provider: this.container.querySelector("#intStoreProvider")
              ?.value || "drive",
            account: this.container.querySelector("#intStoreAccount")
              ?.value || "",
            token_ref: this.container.querySelector("#intStoreTokenRef")
              ?.value || "",
            action: "sync_files",
            data: { include_shared: true },
          },
          idempotency_key: this.queueIdem("channel", {
            channel: "storage",
            provider: this.container.querySelector("#intStoreProvider")
              ?.value || "drive",
            action: "sync_files",
          }),
        });
        await this.refreshJobs();
        this.render();
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = "Storage sync job queued.";
      } catch (err) {
        if (msg) msg.textContent = `Queue failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "queueChatopsPost") {
      try {
        const run = state.run || "latest";
        const files = Number(state.nodes?.length || 0).toLocaleString();
        const text = `Optic sync: ${files} files indexed in run ${run}.`;
        await postJson("/api/integrations/jobs", {
          kind: "channel",
          payload: {
            channel: "chatops",
            provider: this.container.querySelector("#intChatopsProvider")
              ?.value || "slack",
            account: this.container.querySelector("#intChatopsAccount")
              ?.value || "",
            token_ref: this.container.querySelector("#intChatopsTokenRef")
              ?.value || "",
            action: "post_status",
            data: { text },
          },
          idempotency_key: this.queueIdem("channel", {
            channel: "chatops",
            provider: this.container.querySelector("#intChatopsProvider")
              ?.value || "slack",
            action: "post_status",
          }),
        });
        await this.refreshJobs();
        this.render();
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = "ChatOps post job queued.";
      } catch (err) {
        if (msg) msg.textContent = `Queue failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "saveBilling") {
      try {
        const plan = this.container.querySelector("#billPlan")?.value || "free";
        const seats = Number(this.container.querySelector("#billSeats")?.value
          || 1);
        await postJson("/api/billing/plan", { plan, seats });
        await Promise.all([this.refreshBilling(), this.refreshUsage()]);
        this.render();
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = "Plan saved.";
      } catch (err) {
        if (msg) msg.textContent = `Plan save failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "checkoutBilling") {
      try {
        const plan = this.container.querySelector("#billPlan")?.value || "pro";
        const seats = Number(this.container.querySelector("#billSeats")?.value
          || 1);
        const out = await postJson("/api/billing/checkout", { plan, seats });
        const url = String(out.checkout_url || "").trim();
        if (!url) throw new Error("Checkout URL missing.");
        window.open(url, "_blank", "noopener,noreferrer");
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = "Checkout opened in new tab.";
      } catch (err) {
        if (msg) msg.textContent = `Checkout failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "portalBilling") {
      try {
        const out = await postJson("/api/billing/portal", {});
        const url = String(out.portal_url || "").trim();
        if (!url) throw new Error("Portal URL missing.");
        window.open(url, "_blank", "noopener,noreferrer");
        const next = this.container.querySelector("#setMsg");
        if (next) next.textContent = "Billing portal opened in new tab.";
      } catch (err) {
        if (msg) msg.textContent = `Portal failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "save") {
      try {
        const out = await postJson("/api/settings", this.payload());
        state.settings = out.settings;
        if (msg) msg.textContent = "Saved.";
      } catch (err) {
        if (msg) msg.textContent = `Save failed: ${apiMsg(err)}`;
      }
      return;
    }
    if (act === "backup") {
      await postJson("/api/ops/backup", { tag: "ui" });
      await this.refreshBackups();
      this.render();
      return;
    }
    if (act === "restore") {
      const id = this.container.querySelector("#setRestoreSel")?.value || "";
      if (!id) return;
      await postJson("/api/ops/restore", { backup_id: id, confirm: "RESTORE" });
      if (msg) msg.textContent = `Restored ${id}. Reload page to refresh data.`;
      return;
    }
    if (act === "clearDead") {
      await postJson("/api/ops/danger", {
        action: "clear_dead_letters", confirm: "I UNDERSTAND",
      });
      await refreshStatus(true);
      if (msg) msg.textContent = "Dead letters cleared.";
      return;
    }
    if (act === "resetSummary") {
      await postJson("/api/ops/danger", {
        action: "reset_home_summary", confirm: "I UNDERSTAND",
      });
      await refreshHomeData(true);
      if (msg) msg.textContent = "Home summary reset.";
    }
  }

  onSearch() {}
  onKey() {}
  draw() {}
}

function fmtDelta(v) {
  const n = Number(v || 0);
  const s = n > 0 ? "+" : "";
  return `${s}${n}`;
}

// ─── OnboardMode ──────────────────────────────────────────────────────────────

const DEFAULT_FOLDERS = [
  { name: "Desktop", checked: true },
  { name: "Documents", checked: true },
  { name: "Downloads", checked: true },
  { name: "Screenshots", checked: true },
  { name: "Music", checked: false },
  { name: "Movies", checked: false },
];

class OnboardMode {
  constructor() {
    this.container = null;
    this.scanning = false;
    this.pollId = null;
    this.pollBusy = false;
  }

  mount(container) {
    this.container = container;
    this.render();
  }

  unmount() {
    this.stopPoll();
    if (this.container) this.container.innerHTML = "";
  }

  render() {
    this.container.innerHTML = `
      <div class="onboard">
        <div class="onboard-logo">Optic</div>
        <h2>What should Optic analyze?</h2>
        <div class="folder-grid" id="folderGrid">
          ${DEFAULT_FOLDERS.map(f => `
            <label class="folder-check${f.checked ? " checked" : ""}">
              <input type="checkbox" value="${esc(f.name)}"${f.checked ? " checked" : ""}>
              ${f.checked ? "☑" : "☐"} ${esc(f.name)}
            </label>`).join("")}
        </div>
        <label class="folder-check" id="addCustom" style="margin-bottom:16px;border-style:dashed">
          + Add custom folder...
        </label>
        <button class="scan-btn" id="startScan">Start Analysis →</button>
        <p class="privacy-note">Optic runs entirely on your Mac.<br>Nothing leaves your device.</p>
        <div id="scanStatus" class="scan-status" hidden>
          <span class="pulse-dot"></span>
          <span id="scanStatusText">Analyzing your files…</span>
        </div>
      </div>`;

    // Toggle checked state on folder labels
    this.container.querySelectorAll(".folder-check input").forEach(inp => {
      this.bindFolderInput(inp);
    });

    this.container.querySelector("#addCustom").addEventListener("click", ev => {
      ev.preventDefault();
      this.addCustomFolder();
    });

    this.container.querySelector("#startScan").addEventListener("click", () => {
      this.startScan();
    });
  }

  bindFolderInput(inp) {
    inp.addEventListener("change", () => this.syncFolderLabel(inp));
  }

  syncFolderLabel(inp) {
    const label = inp.closest(".folder-check");
    if (!label) return;
    label.classList.toggle("checked", inp.checked);
    label.textContent = `${inp.checked ? "☑" : "☐"} ${inp.value}`;
    label.prepend(inp);
  }

  addCustomFolder() {
    const raw = window.prompt("Enter folder path to analyze:", "");
    const path = String(raw || "").trim();
    if (!path) return;
    const dup = [...this.container.querySelectorAll(".folder-check input")]
      .some(inp => inp.value === path);
    if (dup) return this.showStatus(`Folder already added: ${path}`, false, true);
    const label = document.createElement("label");
    const inp = document.createElement("input");
    label.className = "folder-check checked";
    inp.type = "checkbox";
    inp.checked = true;
    inp.value = path;
    label.append(inp, `☑ ${path}`);
    this.container.querySelector("#folderGrid").append(label);
    this.bindFolderInput(inp);
    this.showStatus(`Added folder: ${path}`, false, false);
  }

  selectedFolders() {
    const home = state.home || "/Users/" +
      (document.cookie.match(/user=([^;]+)/) || ["", ""])[1];
    const rows = [...this.container.querySelectorAll(".folder-check input:checked")]
      .map(inp => {
        const v = inp.value;
        // Map friendly names to absolute macOS paths
        if (v === "Screenshots") return `${home}/Pictures/Screenshots`;
        if (v === "Desktop")   return `${home}/Desktop`;
        if (v === "Documents") return `${home}/Documents`;
        if (v === "Downloads") return `${home}/Downloads`;
        if (v === "Music")     return `${home}/Music`;
        if (v === "Movies")    return `${home}/Movies`;
        // Already absolute or custom path
        return v.startsWith("/") ? v : `${home}/${v}`;
      });
    return [...new Set(rows)];
  }

  async startScan() {
    if (this.scanning) return;
    const folders = this.selectedFolders();
    if (!folders.length) {
      this.showStatus("Select at least one folder to analyze.", false, true);
      return;
    }
    const btn = this.container.querySelector("#startScan");
    this.scanning = true;
    btn.disabled = true;
    btn.textContent = "Starting…";
    this.showStatus("Starting analysis…", true, false);

    try {
      await postJson("/api/scan", { folders });
      btn.textContent = "Scan running…";
      this.showStatus("Analyzing your files…", true, false);
      this.pollScan();
    } catch (err) {
      if (apiCode(err) === "scan_already_running") {
        btn.textContent = "Scan in progress…";
        this.showStatus("Scan already running. Tracking status…", true, false);
        this.pollScan();
        return;
      }
      this.failScan(apiMsg(err));
    }
  }

  pollScan(delay = 900) {
    this.stopPoll();
    this.pollId = setTimeout(() => this.tickScan(), delay);
  }

  async tickScan() {
    if (!this.scanning || this.pollBusy) return;
    this.pollBusy = true;
    try {
      const st = await getJson("/api/status");
      const txt = this.scanStatusText(st);
      this.showStatus(txt, st.scanning !== false, false);
      if (st.scanning) this.pollScan(1200);
      else if (this.scanFailed(st)) this.failScanStatus(st);
      else await this.finishScan(st);
    } catch (_) {
      this.showStatus("Waiting for scan status…", true, false);
      this.pollScan(2000);
    } finally {
      this.pollBusy = false;
    }
  }

  async finishScan(st) {
    this.stopPoll();
    this.scanning = false;
    const btn = this.container.querySelector("#startScan");
    btn.disabled = false;
    btn.textContent = "Start Analysis →";
    let msg = st?.last_run ? `Run ready: ${st.last_run}` : "Analysis complete";
    const runId = st?.last_run ? String(st.last_run) : "";
    if (runId) {
      try {
        const rep = await getJson(`/api/report?run=${encodeURIComponent(runId)}`);
        const ws = Number(rep?.workstreams?.count || 0).toLocaleString();
        const fs = Number(rep?.corpus?.total_files || 0).toLocaleString();
        msg = `Run ready: ${runId} · ${ws} workstreams · ${fs} files`;
      } catch (_) {}
    }
    this.showStatus(`${msg}. Loading workstreams…`, false, false);
    setTimeout(() => state.manager.switch("workstreams"), 700);
  }

  failScan(err) {
    this.stopPoll();
    this.scanning = false;
    const btn = this.container.querySelector("#startScan");
    btn.disabled = false;
    btn.textContent = "Start Analysis →";
    this.showStatus(`Could not start analysis: ${this.scanErr(err)}`,
      false, true);
  }

  failScanStatus(st) {
    this.stopPoll();
    this.scanning = false;
    const btn = this.container.querySelector("#startScan");
    btn.disabled = false;
    btn.textContent = "Start Analysis →";
    const err = this.scanFailText(st);
    this.showStatus(`Analysis failed: ${err}`, false, true);
  }

  scanErr(err) {
    if (err === "folders_required") return "select at least one folder";
    if (err === "scan_already_running") return "scan already running";
    return String(err || "unknown error");
  }

  scanFailed(st) {
    if (st?.scanning || st?.last_run) return false;
    const p = st?.progress || {};
    if (p.state === "dead") return true;
    const fail = st?.recent_failure || {};
    return !!(fail.err || p.stderr);
  }

  scanFailText(st) {
    const p = st?.progress || {};
    const fail = st?.recent_failure || {};
    const raw = fail.err || p.stderr || p.state || "unknown_error";
    const txt = String(raw).replace(/\s+/g, " ").trim();
    return txt || "unknown_error";
  }

  scanStatusText(st) {
    const p = st?.progress || {};
    if (p.stage) {
      const stage = String(p.stage).replace(/_/g, " ");
      const stateTxt = String(p.stage_state || "");
      if (stateTxt === "running") return `Pipeline: ${stage}…`;
      if (stateTxt === "ok") return `Completed: ${stage}`;
      if (stateTxt === "error") return `Failed at: ${stage}`;
    }
    if (p.state === "retrying") {
      const n = num(p.attempts);
      const wait = Number(p.retry_in_s || 0);
      if (n && wait > 0) return `Retrying analysis (attempt ${n}) in ${wait}s…`;
      if (n) return `Retrying analysis (attempt ${n})…`;
      return "Retrying analysis…";
    }
    if (p.state === "dead") return "Analysis failed";
    const pct = Number(p.pct ?? p.percent ?? p.progress);
    if (Number.isFinite(pct) && pct >= 0) return `Analyzing… ${pct|0}%`;
    const done = num(p.done ?? p.files_done ?? p.count);
    const total = num(p.total ?? p.files_total);
    if (done && total) return `Analyzing… ${done}/${total} files`;
    if (done) return `Analyzing… ${done} files processed`;
    if (st?.scanning) return "Analyzing your files…";
    return "Scan complete";
  }

  showStatus(msg, busy, err) {
    const box = this.container.querySelector("#scanStatus");
    const dot = box.querySelector(".pulse-dot");
    const txt = this.container.querySelector("#scanStatusText");
    box.hidden = false;
    txt.textContent = msg;
    dot.style.display = busy ? "" : "none";
    txt.style.color = err ? "#ff7f73" : "";
  }

  stopPoll() {
    if (!this.pollId) return;
    clearTimeout(this.pollId);
    this.pollId = null;
  }

  onSearch() {}
  onKey() {}
  draw() {}
}

// ─── Helper: deterministic color per cluster id ───────────────────────────────

function clusterColor(id) {
  const colors = Object.values(palette);
  let h = 2166136261;
  for (const ch of String(id)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return colors[(h >>> 0) % colors.length];
}

class CanvasMode {
  constructor() {
    this.canvas = null;
    this.ctx = null;
    this.cam = { x: 0, y: 0, k: 1 };
    this.drag = null;
  }

  mount(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.resize = () => this.draw();
    this.bind();
    this.draw();
  }

  unmount() {
    this.unbind();
  }

  bind() {
    window.addEventListener("resize", this.resize);
    this.canvas.onpointermove = ev => this.move(ev);
    this.canvas.onpointerdown = ev => this.down(ev);
    this.canvas.onpointerup = ev => this.up(ev);
    this.canvas.onpointercancel = ev => this.cancel(ev);
    this.canvas.onpointerleave = () => this.leave();
    this.canvas.onwheel = ev => this.wheel(ev);
    this.canvas.ondblclick = ev => this.dbl(ev);
  }

  unbind() {
    window.removeEventListener("resize", this.resize);
    this.canvas.onpointermove = null;
    this.canvas.onpointerdown = null;
    this.canvas.onpointerup = null;
    this.canvas.onpointercancel = null;
    this.canvas.onpointerleave = null;
    this.canvas.onwheel = null;
    this.canvas.ondblclick = null;
  }

  size() {
    const r = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.floor(r.width * devicePixelRatio);
    this.canvas.height = Math.floor(r.height * devicePixelRatio);
    this.ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    return r;
  }

  screen(p) {
    const r = this.canvas.getBoundingClientRect();
    return { x: r.width / 2 + (p.x + this.cam.x) * this.cam.k,
      y: r.height / 2 + (p.y + this.cam.y) * this.cam.k };
  }

  world(ev) {
    const r = this.canvas.getBoundingClientRect();
    return { x: (ev.clientX - r.left - r.width / 2) / this.cam.k -
      this.cam.x, y: (ev.clientY - r.top - r.height / 2) / this.cam.k -
      this.cam.y };
  }

  zoomAt(clientX, clientY, scale) {
    const r = this.canvas.getBoundingClientRect();
    const px = clientX - r.left;
    const py = clientY - r.top;
    const oldK = this.cam.k;
    const nextK = clamp(oldK * scale, 0.12, 8);
    if (!Number.isFinite(nextK) || nextK === oldK) return;
    const wx = (px - r.width / 2) / oldK - this.cam.x;
    const wy = (py - r.height / 2) / oldK - this.cam.y;
    this.cam.x = (px - r.width / 2) / nextK - wx;
    this.cam.y = (py - r.height / 2) / nextK - wy;
    this.cam.k = nextK;
  }

  zoomCenter(scale) {
    const r = this.canvas.getBoundingClientRect();
    this.zoomAt(r.left + r.width / 2, r.top + r.height / 2, scale);
  }

  down(ev) {
    if (ev.button !== 0) return;
    this.drag = { x: ev.clientX, y: ev.clientY, cam: { ...this.cam },
      moved: false };
    this.canvas.setPointerCapture(ev.pointerId);
  }

  up(ev) {
    if (!this.drag) return;
    if (!this.drag.moved) this.pick(ev);
    if (this.canvas.hasPointerCapture?.(ev.pointerId)) {
      this.canvas.releasePointerCapture(ev.pointerId);
    }
    this.drag = null;
  }

  cancel(ev) {
    if (this.canvas.hasPointerCapture?.(ev.pointerId)) {
      this.canvas.releasePointerCapture(ev.pointerId);
    }
    this.drag = null;
    hideTip();
    this.draw();
  }

  leave() {
    state.hover = null;
    hideTip();
    this.draw();
  }

  wheel(ev) {
    ev.preventDefault();
    const k = ev.deltaY > 0 ? 0.88 : 1.12;
    this.zoomAt(ev.clientX, ev.clientY, k);
    this.draw();
  }

  onKey(ev) {
    const step = 80 / this.cam.k;
    if (["w", "ArrowUp"].includes(ev.key))    this.cam.y += step;
    else if (["s", "ArrowDown"].includes(ev.key))  this.cam.y -= step;
    else if (["a", "ArrowLeft"].includes(ev.key))  this.cam.x += step;
    else if (["d", "ArrowRight"].includes(ev.key)) this.cam.x -= step;
    else if (ev.key === "0") { // reset camera
      this.cam.x = 0; this.cam.y = 0; this.cam.k = 1;
    }
    else if (ev.key === "z" && state.selected) { // zoom to selected node
      this.cam.x = -(state.selected.x || 0);
      this.cam.y = -(state.selected.y || 0);
      this.cam.k = clamp(this.cam.k < 2 ? 3 : 1, 0.3, 8);
    }
    else return;
    ev.preventDefault();
    this.draw();
  }

  onSearch() {
    this.draw();
  }

  dbl(ev) {
    const n = this.nearest(ev);
    if (n) openFinder(n);
  }
}

class TopologyMode extends CanvasMode {
  mount(canvas) {
    this.edgeSet = new Set();
    this.edges = topEdges(300);
    this.edges.forEach(l => this.edgeSet.add(`${l.a}:${l.b}`));
    this.hero = false;
    this.heroHubs = [];
    super.mount(canvas);
    this.layout();
    this.mapTool = "pan";
    this.mountMapChrome();
  }

  unmount() {
    this.unmountMapChrome();
    this.clearClusterLabels();
    super.unmount();
    if (this.sim) this.sim.stop();
  }

  layout() {
    this.hero = this.shouldHeroMap();
    if (this.hero) {
      this.layoutHero();
      this.draw();
      return;
    }
    // Use PCA x,y directly - semantically similar files are already near each other
    state.nodes.forEach(n => { n.x = n.pcaX; n.y = n.pcaY; });
    if (!window.d3) { this.seedFallback(); return; }
    // Light repulsion only to prevent overlap, no centering force
    const nodes = state.nodes;
    this.sim = d3.forceSimulation(nodes)
      .force("collide", d3.forceCollide(d => d.r + 1.5).strength(0.6))
      .force("charge", d3.forceManyBody().strength(-4).distanceMax(60))
      .alphaDecay(0.08)
      .on("tick", () => this.draw());
  }

  onKey(ev) {
    if (ev.key === "0") {
      this.resetViewport(false);
      ev.preventDefault();
      this.draw();
      return;
    }
    if (ev.key.toLowerCase() === "z" && state.selected) {
      this.focusSelection();
      ev.preventDefault();
      this.draw();
      return;
    }
    super.onKey(ev);
  }

  shouldHeroMap() {
    if (state.nodes.length === 0) return true;
    return state.nodes.length <= 8 && uniqueClusters() < 2;
  }

  layoutHero() {
    this.heroHubs = [
      { key: "people", label: "People", x: -220, y: -120, color: "#8d63f7" },
      { key: "projects", label: "Projects", x: -8, y: -142, color: "#4f86ef" },
      { key: "documents", label: "Documents", x: 206, y: -14, color: "#25b8b5" },
      { key: "skills", label: "Skills & Topics", x: -170, y: 36,
        color: "#3dbf79" },
      { key: "systems", label: "Systems", x: -22, y: 112, color: "#e0a53e" },
      { key: "events", label: "Events", x: -166, y: 168, color: "#e95f9f" },
      { key: "outcomes", label: "Outcomes", x: 210, y: 128, color: "#9a6cf9" },
      { key: "locations", label: "Locations", x: 60, y: 214,
        color: "#2fc9d5" },
      { key: "strategy", label: "Project Strategy", x: 0, y: 0,
        color: "#3b6ff0", core: true },
    ];
    const byKey = new Map(this.heroHubs.map(h => [h.key, h]));
    const spread = ["projects", "people", "skills", "documents", "systems",
      "events", "outcomes", "locations"];
    state.nodes.forEach((n, idx) => {
      let key = this.heroBucket(n);
      if (key === "documents" && state.nodes.length < 140) {
        key = spread[idx % spread.length];
      }
      const hub = byKey.get(key) || byKey.get("strategy");
      const a = hash(`${n.id}:${idx}`);
      const rr = hub.core ? 48 + (idx % 8) * 7 : 18 + (idx % 7) * 9;
      n.x = hub.x + Math.cos(a) * rr;
      n.y = hub.y + Math.sin(a) * rr * 0.75;
      n.mapColor = hub.color;
      n.mapHub = hub.key;
    });
    this.heroCloud = this.heroHubs.filter(h => !h.core).flatMap(h => {
      const vals = [];
      for (let i = 0; i < 75; i++) {
        const a = hash(`${h.key}:dust:${i}`);
        const t = (Math.sin(i * 17.3 + h.x * 0.01) + 1) * 0.5;
        const rr = 20 + t * 96;
        vals.push({
          x: h.x + Math.cos(a) * rr,
          y: h.y + Math.sin(a) * rr * 0.72,
          r: 0.9 + t * 2.1,
          a: 0.08 + t * 0.24,
          color: h.color,
        });
      }
      return vals;
    });
  }

  heroBucket(n) {
    const t = `${n.label || ""} ${n.path || ""}`.toLowerCase();
    if (/(people|team|contact|persona|recruiter|audience)/.test(t)) {
      return "people";
    }
    if (/(project|roadmap|plan|strategy|work)/.test(t)) return "projects";
    if (/(doc|pdf|deck|notes|report|brief)/.test(t)) return "documents";
    if (/(skill|topic|iris|insight|analysis)/.test(t)) return "skills";
    if (/(system|config|index|state|json)/.test(t)) return "systems";
    if (/(timeline|event|history|log|scan)/.test(t)) return "events";
    if (/(output|result|goal|outcome|export)/.test(t)) return "outcomes";
    if (/(city|location|map|travel|remote)/.test(t)) return "locations";
    return "strategy";
  }

  seedFallback() {
    state.nodes.forEach(n => Object.assign(n, seed(n)));
    this.draw();
  }

  move(ev) {
    if (this.drag) return this.dragMove(ev);
    state.hover = this.nearest(ev);
    tooltip(ev, state.hover);
    this.draw();
  }

  dragMove(ev) {
    const dx = ev.clientX - this.drag.x;
    const dy = ev.clientY - this.drag.y;
    if (Math.hypot(dx, dy) > 3) this.drag.moved = true;
    if (this.mapTool === "focus") {
      hideTip();
      return;
    }
    this.cam.x = this.drag.cam.x + dx / this.cam.k;
    this.cam.y = this.drag.cam.y + dy / this.cam.k;
    hideTip();
    this.draw();
  }

  pick(ev) {
    const n = this.nearest(ev, true);
    state.selected = n;
    if (this.mapTool === "focus") {
      if (n) {
        state.highlightCluster = String(n.cluster || "");
        this.focusSelection();
      } else {
        state.highlightCluster = null;
      }
      this.mapTool = "pan";
    }
    if (!n) state.highlightCluster = null; // blank click clears cluster focus
    selectNodeAsEntity(n, ev);
    renderPanel();
    this.syncMapToolbar();
    this.draw();
  }

  nearest(ev, forPick = false) {
    const p = this.world(ev);
    let best = null;
    const touch = ev?.pointerType === "touch";
    const px = forPick ? (touch ? 34 : 24) : 18;
    let dist = px / this.cam.k;
    for (const n of visibleNodes()) {
      const d = Math.hypot(n.x - p.x, n.y - p.y);
      if (d < dist) [best, dist] = [n, d];
    }
    return best;
  }

  draw() {
    syncSelected();
    const r = this.size();
    this.ctx.clearRect(0, 0, r.width, r.height);
    if (this.hero) this.drawHeroBackdrop(r);
    this.drawClusterNebulae(r);
    this.drawFocusHalo();
    // Only draw edges when a node is selected or hovered — reduces spaghetti
    if (state.selected || state.hover) this.drawEdges();
    this.drawCentroids();
    this.drawNodes();
    this.renderClusterLabels();
    this.drawLabels();
    this.syncMapToolbar();
    this.syncMapHint();
    const edgeCount = (state.selected || state.hover) ? this.edges.length : 0;
    drawCounts(state.nodes.length, edgeCount);
  }

  drawEdges() {
    const ctx = this.ctx;
    const focus = state.selected || state.hover;
    // Always include ALL edges of the selected node (not just top 300)
    // so "Connections: N" in the inspector actually shows N edges
    let edgesToDraw = this.edges;
    if (state.selected) {
      const selId = state.selected.id;
      const selEdges = state.links.filter(l => {
        if (l.a !== selId && l.b !== selId) return false;
        if (!state.highlightCluster) return true;
        const aa = state.nodeById.get(l.a);
        const bb = state.nodeById.get(l.b);
        const cid = String(state.highlightCluster || "");
        return String(aa?.cluster || "") === cid &&
          String(bb?.cluster || "") === cid;
      });
      // Merge: add selected node edges that aren't already in top-300 set
      const extra = selEdges.filter(l => !this.edgeSet.has(`${l.a}:${l.b}`) &&
                                         !this.edgeSet.has(`${l.b}:${l.a}`));
      edgesToDraw = extra.length ? [...this.edges, ...extra] : this.edges;
    }
    for (const l of edgesToDraw) {
      const a = state.nodeById.get(l.a);
      const b = state.nodeById.get(l.b);
      if (!a || !b) continue;
      const hi = edgeSelected(a, b);
      if (!state.selected && focus &&
          a.id !== focus.id && b.id !== focus.id) continue;
      if (!edgeVisible(a, b)) continue;
      ctx.strokeStyle = hi ? "rgba(0,0,0,0.45)" : edgeAlpha();
      ctx.lineWidth = hi ? 1.6 : 0.55 + l.score * 1.4;
      const pa = this.screen(a);
      const pb = this.screen(b);
      line(ctx, pa.x, pa.y, pb.x, pb.y);
    }
  }

  drawCentroids() {
    if (this.hero) {
      const ctx = this.ctx;
      this.heroHubs.forEach(h => {
        const s = this.screen(h);
        const cnt = this.heroSignalCount(h);
        const rr = h.core ? 38 : 16;
        ctx.fillStyle = "rgba(255,255,255,0.9)";
        ctx.strokeStyle = `${h.color}80`;
        ctx.lineWidth = h.core ? 3 : 2;
        ctx.beginPath();
        ctx.arc(s.x, s.y, rr * this.cam.k, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = "#1a2444";
        ctx.font = h.core ? "700 19px Sora, Manrope, sans-serif" :
          "650 13px Sora, Manrope, sans-serif";
        ctx.fillText(h.label, s.x + 16 * this.cam.k, s.y + 2);
        ctx.fillStyle = "rgba(36,56,108,0.78)";
        ctx.font = "500 11px Manrope, sans-serif";
        ctx.fillText(`${cnt} signals`, s.x + 16 * this.cam.k, s.y + 19);
      });
      return;
    }
    if (this.cam.k < 0.4) return;
    const ctx = this.ctx;
    const catCentroids = computeCategoryCentroids();
    for (const [cat, p] of Object.entries(catCentroids)) {
      const s = this.screen(p);
      ctx.fillStyle = `${palette[cat]}cc`;
      const fs = Math.round(clamp(10 + this.cam.k * 1.2, 10, 14));
      ctx.font = `600 ${fs}px system-ui`;
      ctx.fillText(cat, s.x, s.y);
    }
  }

  drawNodes() {
    const ctx = this.ctx;
    const focusId = String(state.highlightCluster || "");
    const zoom = this.cam.k;
    for (const n of visibleNodes()) {
      const s = this.screen(n);
      const a = opacityFor(n);
      const rank = nodePriority(n);
      const inFocus = focusId && String(n.cluster || "") === focusId;
      const relSel = state.selected ? related(n, state.selected) : false;
      const relHover = state.hover ? related(n, state.hover) : false;
      const damp = zoom < 0.66 && !inFocus && !relSel ? 0.84 : 1;
      const bump = n === state.selected ? 1.72 :
        n === state.hover ? 1.36 :
        relSel ? 1.18 :
        relHover ? 1.09 : 1;
      const rr = Math.max(1.8, n.r * zoom * damp * bump);
      if (n.glow) glow(ctx, s, n);
      const wNorm = clamp((n.pcaW + 320) / 640, 0, 1);
      const baseColor = n.mapColor || palette[n.category];
      ctx.fillStyle = baseColor;
      ctx.globalAlpha = clamp(a * (0.42 + wNorm * 0.46) *
        (0.88 + Math.min(rank, 24) / 56), 0.04, 1);
      ctx.beginPath();
      ctx.arc(s.x, s.y, rr, 0, Math.PI * 2);
      ctx.fill();
      if (n === state.selected || n === state.hover) {
        ctx.globalAlpha = n === state.selected ? 0.9 : 0.56;
        ctx.strokeStyle = "rgba(13,28,62,0.78)";
        ctx.lineWidth = n === state.selected ? 1.8 : 1.2;
        ctx.beginPath();
        ctx.arc(s.x, s.y, rr + (n === state.selected ? 3.8 : 2.5), 0,
          Math.PI * 2);
        ctx.stroke();
      }
      ctx.shadowBlur = 0;
    }
    ctx.globalAlpha = 1;
  }

  drawLabels() {
    if (this.hero) return;
    if (this.cam.k < 0.58) return;
    const r = this.canvas.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const boxes = [];
    const blocked = this.clusterBoxes || [];
    const anchors = [];
    const ctx = this.ctx;
    const focused = !!state.highlightCluster;
    const prof = mapDetailProfile(this.cam.k, state.nodes.length, focused);
    const sparse = this.cam.k < 1.1 && !focused;
    const spacingBase = focused ? (this.cam.k < 1 ? 60 : 48) :
      this.cam.k < 0.92 ? 84 : this.cam.k < 1.7 ? 66 : 52;
    const spacingMul = state.nodes.length > 1800 ? 1.22 :
      state.nodes.length > 1000 ? 1.12 :
      state.nodes.length > 500 ? 1.06 : 1;
    const spacing = Math.round(spacingBase * spacingMul);
    const fs = Math.round(clamp(9 + this.cam.k * 1.4, 9, 14));
    let shown = 0;
    ctx.font = `${fs}px system-ui`;
    for (const n of labelNodes(this.cam.k, this.hero)) {
      if (shown >= prof.cap) break;
      if (sparse && n !== state.hover && n !== state.selected &&
          n.degree < prof.minDeg + 5) {
        continue;
      }
      const s = this.screen(n);
      if (anchors.some(a => Math.hypot(a.x - s.x, a.y - s.y) < spacing)) {
        continue;
      }
      if (this.label(ctx, n, boxes, fs, blocked, r, s)) {
        shown++;
        anchors.push(s);
      }
    }
  }

  label(ctx, n, boxes, fs, blocked = [], r = null, s = null) {
    if (n.noise) return false;
    if (opacityFor(n) < 0.45 && n !== state.hover && n !== state.selected) {
      return false;
    }
    if (this.cam.k < 0.9 && n !== state.selected && n !== state.hover &&
        n.degree < 12) {
      return false;
    }
    const point = s || this.screen(n);
    const view = r || this.canvas.getBoundingClientRect();
    const px = point.x;
    const py = point.y;
    if (px < -20 || px > view.width + 20 || py < -20 || py > view.height + 20) {
      return false;
    }
    const cap = this.cam.k < 0.85 ? 14 : this.cam.k < 1.45 ? 22 : 32;
    const txt = n.label.slice(0, cap);
    if (!txt) return false;
    const w = ctx.measureText(txt).width;
    const pad = this.cam.k < 1 ? 7 : 4;
    const h = fs + 2;
    const ww = w + pad * 2;
    const pos = [
      [8, -h * 0.8],
      [-(ww + 8), -h * 0.8],
      [8, 4],
      [-(ww + 8), 4],
      [-(ww * 0.5), -(h + 9)],
      [-(ww * 0.5), 10],
      [12, -(h + 10)],
      [-(ww + 12), 10],
    ];
    const start = hash(String(n.id || "")) % pos.length;
    let box = null;
    const padHit = this.cam.k < 1 ? 7 : 5;
    for (let i = 0; i < pos.length; i++) {
      const [ox, oy] = pos[(start + i) % pos.length];
      const cand = { x: px + ox, y: py + oy, w: ww, h };
      if (cand.x < 2 || cand.y < 2 || cand.x + cand.w > view.width - 2 ||
          cand.y + cand.h > view.height - 2) {
        continue;
      }
      if (boxes.some(b => hitBoxPad(b, cand, padHit))) continue;
      if (blocked.some(b => hitBoxPad(b, cand, 12))) continue;
      box = cand;
      break;
    }
    if (!box) return false;
    boxes.push(box);
    const tx = box.x + pad;
    const ty = box.y + h - 3;
    const emph = n === state.selected || n === state.hover;
    ctx.strokeStyle = emph ? "rgba(255,255,255,0.90)" : "rgba(255,255,255,0.75)";
    ctx.lineWidth = emph ? (fs > 11 ? 2.5 : 2.1) : (fs > 11 ? 2.2 : 1.7);
    ctx.strokeText(txt, tx, ty);
    ctx.fillStyle = emph ? "rgba(6,19,49,0.96)" : "rgba(0,0,0,0.80)";
    ctx.fillText(txt, tx, ty);
    return true;
  }

  drawClusterNebulae() {
    const groups = new Map();
    for (const n of visibleNodes()) {
      const id = n.mapHub || n.cluster || n.category || "other";
      if (!groups.has(id)) groups.set(id, []);
      groups.get(id).push(n);
    }
    for (const vals of groups.values()) {
      if (vals.length < 3) continue;
      const pts = vals.map(n => this.screen(n));
      const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
      const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
      const d2 = pts.reduce((s, p) => s + (p.x - cx) ** 2 + (p.y - cy) ** 2,
        0) / pts.length;
      const rr = Math.max(40, Math.sqrt(d2) * 1.8);
      const col = vals[0].mapColor || palette[vals[0].category] || "#7c8291";
      const grad = this.ctx.createRadialGradient(cx, cy, 0, cx, cy, rr);
      grad.addColorStop(0, `${col}28`);
      grad.addColorStop(0.6, `${col}10`);
      grad.addColorStop(1, `${col}00`);
      this.ctx.beginPath();
      this.ctx.arc(cx, cy, rr, 0, Math.PI * 2);
      this.ctx.fillStyle = grad;
      this.ctx.fill();
    }
  }

  drawFocusHalo() {
    const id = String(state.highlightCluster || "");
    if (!id || this.hero) return;
    const vals = visibleNodes().filter(n => String(n.cluster || "") === id);
    if (vals.length < 2) return;
    const pts = vals.map(n => this.screen(n));
    const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
    const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
    const rr = Math.max(56, pts.reduce((m, p) =>
      Math.max(m, Math.hypot(p.x - cx, p.y - cy)), 0) + 26);
    const sample = vals[0];
    const color = sample?.mapColor || palette[sample?.category] || "#4f86ef";
    const ctx = this.ctx;
    const fill = ctx.createRadialGradient(cx, cy, rr * 0.3, cx, cy, rr);
    fill.addColorStop(0, hexToRgba(color, 0.10));
    fill.addColorStop(0.72, hexToRgba(color, 0.05));
    fill.addColorStop(1, hexToRgba(color, 0));
    ctx.fillStyle = fill;
    ctx.beginPath();
    ctx.arc(cx, cy, rr, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = hexToRgba(color, 0.32);
    ctx.lineWidth = 1.2;
    ctx.setLineDash([6, 4]);
    ctx.beginPath();
    ctx.arc(cx, cy, rr + 2, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  clearClusterLabels() {
    const layer = ensureClusterLabelLayer();
    layer.innerHTML = "";
    layer.hidden = true;
    this.clusterBoxes = [];
  }

  renderClusterLabels() {
    if (this.hero) return this.clearClusterLabels();
    const layer = ensureClusterLabelLayer();
    if (this.cam.k < 0.4) {
      layer.hidden = true;
      layer.innerHTML = "";
      this.clusterBoxes = [];
      return;
    }
    const wsById = new Map((state.workstreams || []).map(ws => [
      String(ws.id || ws.name || ""),
      ws,
    ]));
    const groups = new Map();
    const focusId = String(state.highlightCluster || "");
    const pinId = focusId || String(state.selected?.cluster || "");
    const hoverId = focusId ? "" : String(state.hover?.cluster || "");
    for (const n of visibleNodes()) {
      if (focusId && String(n.cluster || "") !== focusId) {
        continue;
      }
      if (state.q && !matches(n)) continue;
      if (opacityFor(n) < 0.14) continue;
      const id = String(n.cluster || n.category || "cluster");
      if (!groups.has(id)) groups.set(id, []);
      groups.get(id).push(n);
    }
    const rows = [];
    for (const [cid, vals] of groups.entries()) {
      if (vals.length < 2) continue;
      const sx = vals.reduce((s, n) => s + this.screen(n).x, 0) / vals.length;
      const sy = vals.reduce((s, n) => s + this.screen(n).y, 0) / vals.length;
      rows.push({ cid, vals, sx, sy });
    }
    rows.sort((a, b) => {
      const af = a.cid === pinId ? 2 : a.cid === hoverId ? 1 : 0;
      const bf = b.cid === pinId ? 2 : b.cid === hoverId ? 1 : 0;
      return bf - af || b.vals.length - a.vals.length ||
        a.cid.localeCompare(b.cid);
    });
    const detail = this.cam.k < 0.95 ? 1 : this.cam.k < 1.6 ? 2 : 3;
    const denseCap = state.nodes.length > 2600 ? 2 :
      state.nodes.length > 1700 ? 3 :
      state.nodes.length > 1000 ? 4 :
      state.nodes.length > 550 ? 5 :
      state.nodes.length > 300 ? 7 : 8;
    const zoomCap = this.cam.k < 0.8 ? 2 : this.cam.k < 1.5 ? 4 : 7;
    const cap = Math.min(denseCap, zoomCap + (focusId ? 1 : 0));
    const spacingBase = this.cam.k < 0.95 ? 196 :
      this.cam.k < 1.6 ? 154 : 124;
    const spacingMul = state.nodes.length > 1800 ? 1.18 :
      state.nodes.length > 900 ? 1.08 : 1;
    const spacing = Math.round(spacingBase * spacingMul);
    const anchors = [];
    const placed = [];
    layer.hidden = false;
    const vw = layer.clientWidth || el.viewport?.clientWidth || 0;
    const vh = layer.clientHeight || el.viewport?.clientHeight || 0;
    layer.classList.toggle("cluster-labels-dense", cap <= 4 || detail === 1);
    layer.classList.toggle("cluster-labels-compact", detail === 1);
    layer.innerHTML = "";
    let shown = 0;
    for (const row of rows) {
      if (shown >= cap) break;
      if (detail === 1 && row.vals.length < 6 && row.cid !== pinId &&
          row.cid !== hoverId) {
        continue;
      }
      if (anchors.some(p => Math.hypot(p.x - row.sx, p.y - row.sy) < spacing)) {
        continue;
      }
      const ws = wsById.get(row.cid);
      const rawName = ws?.name || cleanName(row.cid);
      const name = rawName.length > 34 ? `${rawName.slice(0, 31)}…` : rawName;
      const desc = detail === 1 ? `${row.vals.length}` :
        `${row.vals.length} signals`;
      const estW = Math.min(232, Math.max(130, name.length * 7.2 + 60));
      const estH = cap <= 4 ? 44 : 54;
      const tries = [
        { x: row.sx, y: row.sy - 8 },
        { x: row.sx + 26, y: row.sy - 4 },
        { x: row.sx - 26, y: row.sy - 4 },
        { x: row.sx + 18, y: row.sy - 20 },
        { x: row.sx - 18, y: row.sy - 20 },
        { x: row.sx, y: row.sy - 26 },
        { x: row.sx + 42, y: row.sy + 2 },
        { x: row.sx - 42, y: row.sy + 2 },
      ];
      let pos = null;
      let box = null;
      for (const t of tries) {
        const cand = {
          x: t.x - estW * 0.5,
          y: t.y - estH * 0.58,
          w: estW,
          h: estH,
        };
        if (vw && vh) {
          if (cand.x < 6 || cand.y < 6 || cand.x + cand.w > vw - 6 ||
              cand.y + cand.h > vh - 6) {
            continue;
          }
        }
        if (placed.some(p => hitBoxPad(p, cand, 12))) continue;
        pos = t;
        box = cand;
        break;
      }
      if (!pos || !box) continue;
      anchors.push({ x: row.sx, y: row.sy });
      placed.push(box);
      const emoji = ws ? this.wsEmoji(ws) : "📁";
      const div = document.createElement("div");
      div.className = "cluster-label";
      if (row.cid === pinId) div.dataset.focus = "1";
      if (row.cid === hoverId) div.dataset.hover = "1";
      if (row.cid === String(state.selected?.cluster || "")) {
        div.dataset.selected = "1";
      }
      div.dataset.cid = row.cid;
      div.style.left = `${pos.x}px`;
      div.style.top = `${pos.y}px`;
      div.innerHTML = `<span class="cluster-label-icon">${emoji}</span>
        <div><div class="cluster-label-name">${esc(name)}</div>
        <div class="cluster-label-desc">${esc(desc)}</div></div>`;
      layer.appendChild(div);
      shown++;
    }
    layer.hidden = shown === 0;
    this.clusterBoxes = placed;
  }

  focusNode(n, k = 2.8) {
    if (!n) return;
    const x = Number.isFinite(n.x) ? n.x : (n.pcaX || 0);
    const y = Number.isFinite(n.y) ? n.y : (n.pcaY || 0);
    this.cam.x = -x;
    this.cam.y = -y;
    this.cam.k = clamp(k, 0.12, 8);
  }

  focusCluster(clusterId) {
    const id = String(clusterId || "");
    if (!id) return false;
    const vals = state.nodes.filter(n => String(n.cluster || "") === id &&
      !n.noise);
    if (!vals.length) return false;
    const xs = vals.map(n => Number.isFinite(n.x) ? n.x : (n.pcaX || 0));
    const ys = vals.map(n => Number.isFinite(n.y) ? n.y : (n.pcaY || 0));
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const w = this.canvas?.getBoundingClientRect().width || 480;
    const h = this.canvas?.getBoundingClientRect().height || 320;
    const span = Math.max(64, maxX - minX, maxY - minY);
    const room = Math.max(200, Math.min(w, h) - 104);
    this.cam.x = -(minX + maxX) * 0.5;
    this.cam.y = -(minY + maxY) * 0.5;
    this.cam.k = clamp(room / span, 0.8, 3.6);
    return true;
  }

  focusSelection() {
    const n = state.selected || state.hover;
    if (!n && state.highlightCluster) {
      this.focusCluster(state.highlightCluster);
      return;
    }
    if (!n) return;
    const cid = String(n.cluster || "");
    if (cid) state.highlightCluster = cid;
    const fit = cid ? this.focusCluster(cid) : false;
    const next = fit ? Math.max(this.cam.k, 1.45) :
      (this.cam.k < 2 ? 2.8 : this.cam.k);
    this.focusNode(n, next);
  }

  resetViewport(clearFocus = false) {
    if (clearFocus) {
      state.highlightCluster = null;
      state.selected = null;
      state.hover = null;
      this.mapTool = "pan";
      hideTip();
    }
    const vals = visibleNodes().filter(n => !n.noise);
    if (!vals.length) {
      this.cam.x = 0;
      this.cam.y = 0;
      this.cam.k = 1;
      return;
    }
    const xs = vals.map(n => Number.isFinite(n.x) ? n.x : (n.pcaX || 0));
    const ys = vals.map(n => Number.isFinite(n.y) ? n.y : (n.pcaY || 0));
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const w = this.canvas?.getBoundingClientRect().width || 480;
    const h = this.canvas?.getBoundingClientRect().height || 320;
    const span = Math.max(120, maxX - minX, maxY - minY);
    const room = Math.max(220, Math.min(w, h) - 112);
    this.cam.x = -(minX + maxX) * 0.5;
    this.cam.y = -(minY + maxY) * 0.5;
    this.cam.k = clamp(room / span, 0.65, 3.2);
  }

  clusterName(id) {
    const cid = String(id || "");
    if (!cid) return "Cluster";
    const ws = (state.workstreams || []).find(w =>
      String(w.id || w.name || "") === cid);
    return ws?.name || cleanName(cid);
  }

  focusHintText() {
    if (this.mapTool === "focus" && !state.selected && !state.highlightCluster) {
      return "Focus armed · click a node to center";
    }
    if (state.selected) {
      const n = state.selected;
      const cid = String(n.cluster || "");
      const name = this.clusterName(cid);
      const degree = Number(n.degree || 0);
      const file = String(n.label || base(n.path) || "Untitled");
      return `${file} · ${degree} links · ${name}`;
    }
    if (state.highlightCluster) {
      const cid = String(state.highlightCluster);
      const count = state.nodes.filter(n => String(n.cluster || "") === cid)
        .length;
      return `${this.clusterName(cid)} · ${count} signals · Esc clears focus`;
    }
    return "Drag to pan · Scroll to zoom · Click to select";
  }

  drawHeroBackdrop(r) {
    const ctx = this.ctx;
    ctx.save();
    const gg = ctx.createLinearGradient(0, 0, 0, r.height);
    gg.addColorStop(0, "#fbfcff");
    gg.addColorStop(1, "#f5f8ff");
    ctx.fillStyle = gg;
    ctx.fillRect(0, 0, r.width, r.height);
    for (let i = 0; i < 18; i++) {
      const x = ((i * 97) % Math.max(1, r.width - 80)) + 40;
      const y = ((i * 53) % Math.max(1, r.height - 120)) + 60;
      ctx.fillStyle = "rgba(75,112,203,0.05)";
      ctx.beginPath();
      ctx.arc(x, y, 1.2, 0, Math.PI * 2);
      ctx.fill();
    }
    const links = [
      ["people", "strategy"], ["projects", "strategy"], ["documents", "strategy"],
      ["skills", "strategy"], ["systems", "strategy"], ["events", "strategy"],
      ["outcomes", "strategy"], ["locations", "strategy"], ["people", "projects"],
      ["documents", "outcomes"], ["skills", "systems"], ["events", "locations"],
    ];
    const by = new Map(this.heroHubs.map(h => [h.key, h]));
    ctx.strokeStyle = "rgba(95,120,186,0.10)";
    ctx.lineWidth = 1.1;
    links.forEach(([a, b]) => {
      const pa = this.screen(by.get(a));
      const pb = this.screen(by.get(b));
      line(ctx, pa.x, pa.y, pb.x, pb.y);
    });
    (this.heroCloud || []).forEach(dot => {
      const p = this.screen(dot);
      ctx.fillStyle = dot.color;
      ctx.globalAlpha = dot.a;
      ctx.beginPath();
      ctx.arc(p.x, p.y, dot.r * this.cam.k, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.globalAlpha = 1;
    ctx.fillStyle = "#1b2446";
    ctx.font = "700 48px Sora, Manrope, sans-serif";
    ctx.fillText("Map", 36, 78);
    ctx.fillStyle = "rgba(47,63,108,0.78)";
    ctx.font = "500 20px Manrope, sans-serif";
    ctx.fillText("Explore how your data connects across signals.",
      36, 108);
    ctx.restore();
  }

  heroSignalCount(h) {
    const own = state.nodes.filter(n => n.mapHub === h.key).length;
    const base = Math.max(1, state.nodes.length);
    const weights = {
      people: 0.11, projects: 0.17, documents: 0.28, skills: 0.15,
      systems: 0.10, events: 0.07, outcomes: 0.08, locations: 0.04,
      strategy: 0.26,
    };
    const est = Math.round(base * (weights[h.key] || 0.1));
    return Math.max(own, est);
  }

  wsEmoji(ws) {
    const text = `${(ws.topics || []).join(" ")} ${ws.name || ""}`
      .toLowerCase();
    if (text.includes("research") || text.includes("learning")) return "📚";
    if (text.includes("work") || text.includes("career")) return "💼";
    if (text.includes("finance")) return "💳";
    if (text.includes("social") || text.includes("people")) return "💬";
    if (text.includes("photo") || text.includes("travel")) return "📷";
    if (text.includes("code") || text.includes("project")) return "💻";
    return "📁";
  }

  mountMapChrome() {
    const map = ensureMapToolbar();
    const hint = ensureMapHint();
    map.root.hidden = false;
    hint.hidden = false;
    map.root.onclick = ev => {
      const tool = ev.target.closest(".map-tool");
      if (tool) {
        const nextTool = tool.dataset.tool || "pan";
        if (nextTool === "focus") {
          if (state.selected || state.highlightCluster || state.hover) {
            this.mapTool = "pan";
            this.focusSelection();
          } else {
            this.mapTool = "focus";
          }
        } else {
          this.mapTool = "pan";
        }
        this.syncMapToolbar();
        this.draw();
        return;
      }
      if (ev.target.closest(".map-reset")) {
        this.mapTool = "pan";
        this.resetViewport(true);
        renderPanel();
        this.draw();
        return;
      }
      if (ev.target.closest(".map-zoom-in")) {
        this.zoomCenter(1.12);
        this.draw();
        return;
      }
      if (ev.target.closest(".map-zoom-out")) {
        this.zoomCenter(0.88);
        this.draw();
      }
    };
    this.syncMapToolbar();
    this.syncMapHint();
  }

  unmountMapChrome() {
    const map = ensureMapToolbar();
    const hint = ensureMapHint();
    map.root.hidden = true;
    hint.hidden = true;
    map.root.onclick = null;
    hint.textContent = "Drag to pan · Scroll to zoom · Click to select";
    hint.dataset.state = "idle";
  }

  syncMapToolbar() {
    const map = ensureMapToolbar();
    map.zoom.textContent = `${Math.round(this.cam.k * 100)}%`;
    map.root.querySelectorAll(".map-tool").forEach(btn => {
      const on = btn.dataset.tool === this.mapTool;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  syncMapHint() {
    const hint = ensureMapHint();
    const hasSel = !!state.selected;
    const hasFocus = !!state.highlightCluster;
    hint.dataset.state = hasSel ? "selected" : hasFocus ? "focus" : "idle";
    hint.textContent = this.focusHintText();
  }
}

class TimelineMode extends CanvasMode {
  mount(canvas) {
    super.mount(canvas);
    this.brush = null;
    this.tFilter = null;
    this.preset = "all";
    this.scope = [];
    this.hero = this.shouldHeroTimeline();
    this.ghost = [];
    this.cam = { x: 0, y: 0, k: 1 };
    updateTimelineHud();
  }

  shouldHeroTimeline() {
    if (state.nodes.length < 180) return true;
    const cats = new Set(state.nodes.map(n => n.category));
    return cats.size < 3;
  }

  down(ev) {
    const r = this.canvas.getBoundingClientRect();
    if (ev.offsetY > r.height - 60) {
      this.brush = { x0: ev.offsetX, x1: ev.offsetX };
      return;
    }
    super.down(ev);
  }

  up(ev) {
    if (this.brush) return this.finishBrush(ev);
    super.up(ev);
  }

  move(ev) {
    if (this.brush) return this.dragBrush(ev);
    if (this.drag) return this.dragMove(ev);
    state.hover = this.nearest(ev);
    tooltip(ev, state.hover);
    this.draw();
  }

  dragMove(ev) {
    const dx = ev.clientX - this.drag.x;
    const dy = ev.clientY - this.drag.y;
    if (Math.hypot(dx, dy) > 3) this.drag.moved = true;
    this.cam.x = this.drag.cam.x + dx / this.cam.k;
    this.cam.y = this.drag.cam.y + dy / this.cam.k;
    this.draw();
  }

  dragBrush(ev) {
    this.brush.x1 = ev.offsetX;
    this.draw();
  }

  finishBrush(ev) {
    this.brush.x1 = ev.offsetX;
    const r = this.canvas.getBoundingClientRect();
    const a = Math.min(this.brush.x0, this.brush.x1);
    const b = Math.max(this.brush.x0, this.brush.x1);
    this.tFilter = b - a > 12 ? [this.timeAt(a, r), this.timeAt(b, r)] : null;
    this.preset = this.tFilter ? "custom" : "all";
    this.brush = null;
    this.draw();
  }

  setRangePreset(key) {
    this.extents();
    if (!this.scope.length) return;
    if (key === "all") this.tFilter = null;
    if (key === "90d") this.tFilter = [Math.max(this.minT, this.maxT -
      90 * 86400), this.maxT];
    if (key === "1y") this.tFilter = [Math.max(this.minT, this.maxT -
      365 * 86400), this.maxT];
    this.preset = key;
    this.draw();
  }

  timeAt(x, r) {
    const v = x / this.cam.k - this.cam.x;
    return map(v, 48, r.width - 28, this.minT, this.maxT);
  }

  pick(ev) {
    state.selected = this.nearest(ev);
    renderPanel();
    this.draw();
  }

  point(n, r) {
    const t = n.mtime || Date.now() / 1000;
    const x = map(t, this.minT, this.maxT, 48, r.width - 28);
    const yv = Math.log10((n.size || 1) + 1);
    const y = map(yv, this.minS, this.maxS, r.height - 74, 34);
    return { x: (x + this.cam.x) * this.cam.k, y: (y + this.cam.y) *
      this.cam.k };
  }

  nearest(ev) {
    const r = this.canvas.getBoundingClientRect();
    let best = null;
    let dist = 15;
    for (const n of this.nodes()) {
      const p = this.point(n, r);
      const d = Math.hypot(p.x - ev.offsetX, p.y - ev.offsetY);
      if (d < dist) [best, dist] = [n, d];
    }
    return best;
  }

  draw() {
    const r = this.size();
    this.extents();
    if (!this.scope.length) {
      this.ctx.clearRect(0, 0, r.width, r.height);
      drawCounts(0, 0);
      updateTimelineHud({ shown: 0, total: 0, preset: this.preset });
      return;
    }
    const shown = this.nodes();
    this.bg(r);
    this.hist(r);
    this.dots(r);
    this.callouts(r);
    this.drawFilter(r);
    this.drawBrush(r);
    drawCounts(shown.length, 0);
    updateTimelineHud({ shown: shown.length, total: this.scope.length,
      tFilter: this.tFilter, minT: this.minT, maxT: this.maxT,
      preset: this.preset });
  }

  extents() {
    this.scope = visibleNodes();
    if (!this.scope.length) {
      this.minT = 0;
      this.maxT = 0;
      this.minS = 0;
      this.maxS = 1;
      return;
    }
    if (this.hero) {
      const now = Date.now() / 1000;
      this.minT = now - 365 * 86400;
      this.maxT = now;
      this.minS = Math.log10(1024 + 1);
      this.maxS = Math.log10(1024 * 1024 * 1024 + 1);
      if (!this.ghost.length) this.seedGhost();
      return;
    }
    const ts = this.scope.map(n => n.mtime || Date.now() / 1000);
    const ss = this.scope.map(n => Math.log10((n.size || 1) + 1));
    this.minT = Math.min(...ts);
    this.maxT = Math.max(...ts);
    this.minS = Math.min(...ss);
    this.maxS = Math.max(...ss);
  }

  seedGhost() {
    const cats = Object.keys(palette);
    const vals = [];
    const rows = Math.max(260, Math.min(720, state.nodes.length * 10));
    for (let i = 0; i < rows; i++) {
      const t = this.minT + (this.maxT - this.minT) * ((i * 37 % rows) / rows);
      const sz = 1024 + Math.pow(((i * 19) % rows) / rows, 3.2) *
        (1024 * 1024 * 300);
      const cat = cats[i % cats.length];
      vals.push({
        id: `ghost-${i}`,
        mtime: t,
        size: sz,
        category: cat,
        r: 2.2 + (((i * 7) % 10) / 10) * 2.6,
        label: this.ghostLabel(i, cat),
      });
    }
    this.ghost = vals;
  }

  ghostLabel(i, cat) {
    const tags = {
      Documents: ["Executive summary", "Project plan", "Q2 deck",
        "Roadmap review"],
      Images: ["Design assets", "Screenshots", "Export board", "City photo"],
      Code: ["Build log", "API patch", "Infra notes", "Schema draft"],
      Video: ["Demo capture", "Walkthrough", "Interview clip", "Screen cast"],
      System: ["Index state", "Pipeline run", "Sync event", "Cache snapshot"],
      Other: ["Research notes", "Topic digest", "Weekly brief", "Audit memo"],
    };
    const pool = tags[cat] || tags.Other;
    return pool[i % pool.length];
  }

  bg(r) {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, r.width, r.height);
    ctx.strokeStyle = "rgba(0,0,0,0.06)";
    for (let x = 48; x < r.width; x += 90) line(ctx, x, 28, x, r.height - 58);
    for (let y = 38; y < r.height - 58; y += 54) line(ctx, 38, y, r.width, y);
    this.drawSizeAxis(r);
    this.drawDateAxis(r);
  }

  drawSizeAxis(r) {
    const ctx = this.ctx;
    const SIZES = [[1024,"1 KB"],[65536,"64 KB"],[1048576,"1 MB"],
                   [16777216,"16 MB"],[104857600,"100 MB"]];
    ctx.save();
    ctx.font = "9px system-ui";
    ctx.textAlign = "left";
    for (const [sz, label] of SIZES) {
      const lv = Math.log10(sz + 1);
      if (lv < this.minS || lv > this.maxS) continue;
      const dy = map(lv, this.minS, this.maxS, r.height - 74, 34);
      const sy = (dy + this.cam.y) * this.cam.k;
      if (sy < 20 || sy > r.height - 62) continue;
      ctx.fillStyle = "rgba(0,0,0,0.35)";
      ctx.fillText(label, 3, sy + 3);
    }
    ctx.restore();
  }

  drawDateAxis(r) {
    // Adaptive month ticks: keep labels readable over long date ranges
    const ctx = this.ctx;
    ctx.save();
    ctx.font = "9px system-ui";
    ctx.textAlign = "center";
    const DAY = 86400;
    const monthSpan = Math.max(1, Math.round((this.maxT - this.minT) /
      (30 * DAY)));
    const stepMonths = monthSpan > 120 ? 12 :
      monthSpan > 72 ? 6 :
      monthSpan > 36 ? 3 :
      monthSpan > 18 ? 2 : 1;
    const start = new Date(this.minT * 1000);
    start.setUTCDate(1);
    start.setUTCHours(0, 0, 0, 0);
    let lastYear = -1;
    for (let dt = new Date(start.getTime());
         dt.getTime() / 1000 <= this.maxT + 31 * DAY;
         dt.setUTCMonth(dt.getUTCMonth() + stepMonths)) {
      const t = dt.getTime() / 1000;
      const dx = map(t, this.minT, this.maxT, 48, r.width - 28);
      const sx = (dx + this.cam.x) * this.cam.k;
      if (sx < 38 || sx > r.width - 4) continue;
      const year = dt.getUTCFullYear();
      const isYear = dt.getUTCMonth() === 0 || year !== lastYear;
      if (isYear) {
        // Year marker: brighter line + label
        ctx.strokeStyle = "rgba(0,0,0,0.20)";
        ctx.lineWidth = 1;
        line(ctx, sx, 14, sx, r.height - 60);
        ctx.fillStyle = "rgba(0,0,0,0.55)";
        ctx.font = "bold 9px system-ui";
        ctx.fillText(String(year), sx, 13);
        lastYear = year;
      } else {
        // Month tick: subtle
        ctx.strokeStyle = "rgba(0,0,0,0.07)";
        ctx.lineWidth = 0.5;
        line(ctx, sx, 20, sx, r.height - 60);
        const mon = dt.toLocaleString("en-US", { month: "short",
          timeZone: "UTC" });
        ctx.fillStyle = "rgba(0,0,0,0.30)";
        ctx.font = "9px system-ui";
        ctx.fillText(stepMonths >= 3 ? `${mon}-${String(year).slice(-2)}` : mon,
          sx, 22);
      }
    }
    ctx.restore();
  }

  dots(r) {
    const ctx = this.ctx;
    if (this.hero) {
      for (const n of this.ghost) {
        const p = this.point(n, r);
        ctx.globalAlpha = 0.14;
        ctx.fillStyle = palette[n.category] || "#6b7280";
        ctx.beginPath();
        ctx.arc(p.x, p.y, Math.max(1.6, n.r * 0.7), 0, Math.PI * 2);
        ctx.fill();
      }
    }
    for (const n of this.nodes()) {
      const p = this.point(n, r);
      const base = opacityFor(n);
      ctx.globalAlpha = Math.max(0.16, base);
      if (n.glow) glow(ctx, p, n);
      ctx.fillStyle = palette[n.category];
      ctx.beginPath();
      ctx.arc(p.x, p.y, Math.max(2.2, n.r * 0.58), 0, Math.PI * 2);
      ctx.fill();
      if (state.selected && n.id === state.selected.id) {
        ctx.globalAlpha = 1;
        ctx.strokeStyle = "rgba(0,0,0,0.60)";
        ctx.lineWidth = 1.2;
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
  }

  hist(r) {
    const bins = monthBins(this.scope, this.minT, this.maxT);
    if (!bins.length) return;
    const max = Math.max(1, ...bins.map(b => b.count));
    const W = Math.max(1, r.width - 76);
    const w = W / Math.max(1, bins.length);
    const ctx = this.ctx;
    ctx.save();
    ctx.font = "8px system-ui";
    ctx.textAlign = "left";
    let lastYear = "";
    bins.forEach((b, i) => {
      const h = map(b.count, 0, max, 2, 38);
      const x = 38 + i * w;
      ctx.fillStyle = "rgba(59,111,240,0.35)";
      ctx.fillRect(x, r.height - h - 8, Math.max(1.4, w - 0.6), h);
      // Year label at year boundaries
      const year = b.month.slice(0, 4);
      if (year !== lastYear) {
        ctx.fillStyle = "rgba(0,0,0,0.35)";
        ctx.fillText(year, x + 2, r.height - 2);
        lastYear = year;
      }
    });
    ctx.restore();
  }

  callouts(r) {
    const top = this.hero ? this.ghost.slice(0, 8) :
      largestByMonth(this.nodes()).slice(0, 8);
    const boxes = [];
    this.ctx.font = "11px system-ui";
    top.forEach(n => this.callout(n, r, boxes));
  }

  callout(n, r, boxes) {
    if (n.noise) return;
    const p = this.point(n, r);
    const txt = n.label.slice(0, 36);
    const w = this.ctx.measureText(txt).width;
    const x = clamp(p.x + 8, 42, r.width - w - 10);
    const y = clamp(p.y - 7, 18, r.height - 70);
    const box = { x: x - 4, y: y - 10, w: w + 8, h: 14 };
    if (boxes.some(b => hitBox(b, box))) return;
    boxes.push(box);
    this.ctx.fillStyle = "rgba(255,255,255,0.82)";
    this.ctx.fillRect(box.x, box.y, box.w, box.h);
    this.ctx.strokeStyle = "rgba(59,111,240,0.28)";
    this.ctx.lineWidth = 1;
    this.ctx.strokeRect(box.x, box.y, box.w, box.h);
    this.ctx.fillStyle = "rgba(0,0,0,0.75)";
    this.ctx.fillText(txt, x, y);
  }

  drawFilter(r) {
    if (!this.tFilter) return;
    const a = map(this.tFilter[0], this.minT, this.maxT, 48, r.width - 28);
    const b = map(this.tFilter[1], this.minT, this.maxT, 48, r.width - 28);
    const x = Math.min(a, b);
    const w = Math.max(2, Math.abs(b - a));
    const y = r.height - 56;
    this.ctx.fillStyle = "rgba(59,111,240,0.10)";
    this.ctx.fillRect(x, y, w, 46);
    this.ctx.strokeStyle = "rgba(59,111,240,0.40)";
    this.ctx.strokeRect(x + 0.5, y + 0.5, Math.max(1, w - 1), 45);
  }

  drawBrush(r) {
    if (!this.brush) return;
    const x = Math.min(this.brush.x0, this.brush.x1);
    const w = Math.max(2, Math.abs(this.brush.x1 - this.brush.x0));
    const y = r.height - 56;
    this.ctx.fillStyle = "rgba(59,111,240,0.10)";
    this.ctx.fillRect(x, y, w, 46);
    this.ctx.strokeStyle = "rgba(59,111,240,0.55)";
    this.ctx.strokeRect(x + 0.5, y + 0.5, w - 1, 45);
    this.ctx.fillStyle = "rgba(59,111,240,0.70)";
    this.ctx.fillRect(x, y + 8, 2, 30);
    this.ctx.fillRect(x + w - 2, y + 8, 2, 30);
  }

  nodes() {
    const baseNodes = this.scope.length ? this.scope : visibleNodes();
    const nodes = this.hero ? [...this.ghost, ...baseNodes] : baseNodes;
    if (!this.tFilter) return nodes;
    return nodes.filter(n => n.mtime >= this.tFilter[0] &&
      n.mtime <= this.tFilter[1]);
  }
}

class UniverseMode {
  constructor() {
    this.rot = { x: 0.1, y: 0.2 };
    this.cam = { z: 760 };
    this.drag = null;
    this.fallback2d = false;
    this.cam2d = { x: 0, y: 0, k: 0.85 };
    this.hoverNode = null;
  }

  mount(canvas) {
    this.canvas = canvas;
    this.init();
    this.bind();
    this.animate();
  }

  unmount() {
    cancelAnimationFrame(this.raf);
    this.unbind();
    this.ctx = null;
    this.uNodes = null;
    this.uEdges = null;
    this.uDust = null;
    this.uCenters = null;
    this.renderer?.dispose();
  }

  init() {
    this.fallback2d = false;
    if (!window.THREE) {
      this.init2d();
      return;
    }
    const r = this.canvas.getBoundingClientRect();
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(55, r.width / r.height, 1, 5000);
    this.camera.position.z = this.cam.z;
    try {
      this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas,
        antialias: true });
    } catch (_) {
      this.init2d();
      return;
    }
    if (!this.renderer) {
      this.init2d();
      return;
    }
    this.renderer.setClearColor(0x05050e, 1);
    this.renderer.setSize(r.width, r.height, false);
    this.ray = new THREE.Raycaster();
    this.mouse = new THREE.Vector2();
    this.stars();
    this.labels();
  }

  init2d() {
    this.fallback2d = true;
    this.ctx = this.canvas.getContext("2d");
    this.uNodes = state.nodes.map(n => ({ n, p: universePoint(n) }));
    this.uEdges = topEdges(Math.max(260, Math.min(900, state.links.length)));
    this.uCenters = this.computeCenters3d();
    this.uDust = this.seedDust();
  }

  computeCenters3d() {
    const sums = {};
    const counts = {};
    Object.keys(palette).forEach(cat => {
      sums[cat] = { x: 0, y: 0, z: 0 };
      counts[cat] = 0;
    });
    this.uNodes.forEach(({ n, p }) => {
      if (!sums[n.category]) return;
      sums[n.category].x += p.x;
      sums[n.category].y += p.y;
      sums[n.category].z += p.z;
      counts[n.category] += 1;
    });
    const out = {};
    Object.keys(palette).forEach((cat, idx) => {
      const c = counts[cat];
      if (c > 0) {
        out[cat] = {
          x: sums[cat].x / c,
          y: sums[cat].y / c,
          z: sums[cat].z / c,
        };
        return;
      }
      const a = idx / Object.keys(palette).length * Math.PI * 2;
      out[cat] = { x: Math.cos(a) * 280, y: Math.sin(a) * 180, z: 0 };
    });
    return out;
  }

  seedDust() {
    const out = [];
    const cats = Object.keys(palette);
    cats.forEach((cat, cidx) => {
      const ctr = this.uCenters[cat];
      const base = 54;
      for (let i = 0; i < base; i++) {
        const a = hash(`${cat}:${i}`);
        const t = (Math.sin((i + 1) * 23.17 + cidx * 11.2) + 1) * 0.5;
        const rr = 34 + t * 130;
        const zz = (Math.cos((i + 5) * 9.9 + cidx * 7.3) * 90);
        out.push({
          cat,
          size: 0.7 + t * 1.7,
          alpha: 0.09 + t * 0.23,
          p: {
            x: ctr.x + Math.cos(a) * rr,
            y: ctr.y + Math.sin(a) * rr * 0.78,
            z: ctr.z + zz,
          },
        });
      }
    });
    return out;
  }

  bind() {
    window.addEventListener("resize", this.resize = () => this.fit());
    if (this.fallback2d) {
      this.canvas.onpointerdown = ev => this.down2d(ev);
      this.canvas.onpointermove = ev => this.move2d(ev);
      this.canvas.onpointerup = () => this.drag = null;
      this.canvas.onclick = ev => this.pick2d(ev);
      this.canvas.onwheel = ev => this.wheel2d(ev);
      this.canvas.ondblclick = ev => this.open2d(ev);
      return;
    }
    this.canvas.onpointerdown = ev => this.down(ev);
    this.canvas.onpointermove = ev => this.move(ev);
    this.canvas.onpointerup = () => this.drag = null;
    this.canvas.onclick = ev => this.pick(ev);
    this.canvas.onwheel = ev => this.wheel(ev);
    this.canvas.ondblclick = ev => this.open(ev);
  }

  unbind() {
    window.removeEventListener("resize", this.resize);
    this.canvas.onpointerdown = null;
    this.canvas.onpointermove = null;
    this.canvas.onpointerup = null;
    this.canvas.onclick = null;
    this.canvas.onwheel = null;
    this.canvas.ondblclick = null;
  }

  stars() {
    this.group = new THREE.Group();
    this.objects = [];
    state.nodes.forEach(n => this.star(n));
    this.scene.add(this.group);
    this.trails();
  }

  star(n) {
    const g = new THREE.SphereGeometry(Math.max(1.5, n.r * 0.7 * (0.7 + (n.pcaW + 320)/640 * 0.6)), 6, 6);
    const m = new THREE.MeshBasicMaterial({ color: bright(n), transparent: true,
      opacity: matches(n) ? 1 : 0.05 });
    const mesh = new THREE.Mesh(g, m);
    const p = universePoint(n);
    mesh.position.set(p.x, p.y, p.z);
    mesh.userData.id = n.id;
    this.objects.push(mesh);
    this.group.add(mesh);
  }

  labels() {
    // Compute actual category centroids in universe space from real node positions
    const sums = {};
    const counts = {};
    for (const cat of Object.keys(palette)) { sums[cat] = {x:0,y:0,z:0}; counts[cat] = 0; }
    for (const n of state.nodes) {
      if (sums[n.category]) {
        const p = universePoint(n);
        sums[n.category].x += p.x;
        sums[n.category].y += p.y;
        sums[n.category].z += p.z;
        counts[n.category]++;
      }
    }
    for (const cat of Object.keys(palette)) {
      if (counts[cat] > 0) {
        const pos = {
          x: sums[cat].x / counts[cat],
          y: sums[cat].y / counts[cat] + 30, // offset above centroid
          z: sums[cat].z / counts[cat],
        };
        this.group.add(labelSprite(cat, pos));
      }
    }
  }

  trails() {
    const now = Date.now() / 1000;
    state.nodes.filter(n => now - n.mtime < 604800).slice(0, 80)
      .forEach(n => this.trail(n));
  }

  trail(n) {
    const p = universePoint(n);
    const pts = [new THREE.Vector3(p.x - 26, p.y + 10, p.z),
      new THREE.Vector3(p.x + 22, p.y - 8, p.z)];
    const geo = new THREE.BufferGeometry().setFromPoints(pts);
    const mat = new THREE.LineBasicMaterial({ color: palette[n.category],
      transparent: true, opacity: 0.78 });
    this.group.add(new THREE.Line(geo, mat));
  }

  animate() {
    this.raf = requestAnimationFrame(() => this.animate());
    if (this.fallback2d) {
      if (!this.drag) this.rot.y += 0.0012;
      this.draw2d();
      drawCounts(visibleNodes().length, this.uEdges?.length || 0);
      return;
    }
    if (!this.drag) this.rot.y += 0.0014;
    if (this.group) this.group.rotation.set(this.rot.x, this.rot.y, 0);
    this.renderer?.render(this.scene, this.camera);
    drawCounts(visibleNodes().length, 0);
  }

  fit() {
    if (this.fallback2d) {
      this.draw2d();
      return;
    }
    if (!this.renderer) return;
    const r = this.canvas.getBoundingClientRect();
    this.camera.aspect = r.width / r.height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(r.width, r.height, false);
  }

  down(ev) {
    this.drag = { x: ev.clientX, y: ev.clientY, rot: { ...this.rot } };
  }

  move(ev) {
    if (!this.drag) return;
    this.rot.y = this.drag.rot.y + (ev.clientX - this.drag.x) * 0.006;
    this.rot.x = this.drag.rot.x + (ev.clientY - this.drag.y) * 0.006;
  }

  wheel(ev) {
    ev.preventDefault();
    this.camera.position.z = clamp(this.camera.position.z +
      Math.sign(ev.deltaY) * 60, 160, 1800);
  }

  pick(ev) {
    if (this.fallback2d) return this.pick2d(ev);
    const hit = this.hit(ev);
    state.selected = hit ? state.nodeById.get(hit.userData.id) : null;
    this.focus(hit);
    selectNodeAsEntity(state.selected, ev);
    renderPanel();
  }

  focus(hit) {
    if (!hit || !this.group) return this.group?.position.set(0, 0, 0);
    this.group.position.set(-hit.position.x, -hit.position.y, -hit.position.z);
    this.camera.position.z = 320;
  }

  open(ev) {
    if (this.fallback2d) return this.open2d(ev);
    const hit = this.hit(ev);
    if (hit) openFinder(state.nodeById.get(hit.userData.id));
  }

  hit(ev) {
    const r = this.canvas.getBoundingClientRect();
    this.mouse.x = ((ev.clientX - r.left) / r.width) * 2 - 1;
    this.mouse.y = -((ev.clientY - r.top) / r.height) * 2 + 1;
    this.ray.setFromCamera(this.mouse, this.camera);
    return this.ray.intersectObjects(this.objects)[0]?.object || null;
  }

  onSearch() {
    if (this.fallback2d) {
      this.draw2d();
      return;
    }
    this.objects.forEach(o => {
      const n = state.nodeById.get(o.userData.id);
      o.material.opacity = matches(n) ? 1 : 0.05;
    });
  }

  onKey(ev) {
    if (this.fallback2d) {
      const step = 52 / this.cam2d.k;
      const k = ev.key.toLowerCase();
      if (k === "a") this.cam2d.x += step;
      else if (k === "d") this.cam2d.x -= step;
      else if (k === "w") this.cam2d.y += step;
      else if (k === "s") this.cam2d.y -= step;
      else if (k === "q") this.cam2d.k = clamp(this.cam2d.k * 1.08, 0.35, 3);
      else if (k === "e") this.cam2d.k = clamp(this.cam2d.k * 0.92, 0.35, 3);
      else return;
      ev.preventDefault();
      this.draw2d();
      return;
    }
    const k = ev.key.toLowerCase();
    if (k === "a") this.rot.y -= 0.08;
    else if (k === "d") this.rot.y += 0.08;
    else if (k === "w") this.rot.x -= 0.08;
    else if (k === "s") this.rot.x += 0.08;
    else if (k === "q") this.camera.position.z -= 42;
    else if (k === "e") this.camera.position.z += 42;
    else return;
    ev.preventDefault();
  }

  size2d() {
    const r = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.floor(r.width * devicePixelRatio);
    this.canvas.height = Math.floor(r.height * devicePixelRatio);
    this.ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    return r;
  }

  project(p) {
    const cy = Math.cos(this.rot.y);
    const sy = Math.sin(this.rot.y);
    const cx = Math.cos(this.rot.x);
    const sx = Math.sin(this.rot.x);
    const rx = p.x * cy - p.z * sy;
    const rz = p.x * sy + p.z * cy;
    const ry = p.y * cx - rz * sx;
    const rz2 = p.y * sx + rz * cx;
    return { x: rx, y: ry, z: rz2, d: clamp((rz2 + 560) / 1120, 0, 1) };
  }

  screen2d(pr, r) {
    return {
      x: r.width / 2 + (pr.x + this.cam2d.x) * this.cam2d.k,
      y: r.height / 2 + (pr.y + this.cam2d.y) * this.cam2d.k,
    };
  }

  world2d(ev, r) {
    return {
      x: (ev.clientX - r.left - r.width / 2) / this.cam2d.k - this.cam2d.x,
      y: (ev.clientY - r.top - r.height / 2) / this.cam2d.k - this.cam2d.y,
    };
  }

  down2d(ev) {
    this.drag = { x: ev.clientX, y: ev.clientY, cam: { ...this.cam2d },
      moved: false };
    this.canvas.setPointerCapture(ev.pointerId);
  }

  move2d(ev) {
    const r = this.canvas.getBoundingClientRect();
    if (this.drag) {
      const dx = ev.clientX - this.drag.x;
      const dy = ev.clientY - this.drag.y;
      if (Math.hypot(dx, dy) > 3) this.drag.moved = true;
      this.cam2d.x = this.drag.cam.x + dx / this.cam2d.k;
      this.cam2d.y = this.drag.cam.y + dy / this.cam2d.k;
      this.draw2d();
      return;
    }
    const n = this.nearest2d(ev, r);
    state.hover = n;
    this.hoverNode = n;
    tooltip(ev, n);
    this.draw2d();
  }

  wheel2d(ev) {
    ev.preventDefault();
    const k = ev.deltaY > 0 ? 0.9 : 1.1;
    this.cam2d.k = clamp(this.cam2d.k * k, 0.35, 3);
    this.draw2d();
  }

  nearest2d(ev, r) {
    const p = this.world2d(ev, r);
    let best = null;
    let dist = 20 / this.cam2d.k;
    this.uNodes.forEach(({ n, p: src }) => {
      const pr = this.project(src);
      const d = Math.hypot(pr.x - p.x, pr.y - p.y);
      if (d < dist) {
        dist = d;
        best = n;
      }
    });
    return best;
  }

  pick2d(ev) {
    if (this.drag?.moved) return;
    const r = this.canvas.getBoundingClientRect();
    const n = this.nearest2d(ev, r);
    state.selected = n || null;
    if (n) this.focus2d(n);
    selectNodeAsEntity(state.selected, ev);
    renderPanel();
    this.draw2d();
  }

  focus2d(n) {
    const pr = this.project(universePoint(n));
    this.cam2d.x = -pr.x;
    this.cam2d.y = -pr.y;
    this.cam2d.k = clamp(this.cam2d.k < 1.25 ? 1.6 : this.cam2d.k, 0.35, 3);
  }

  open2d(ev) {
    const r = this.canvas.getBoundingClientRect();
    const n = this.nearest2d(ev, r);
    if (n) openFinder(n);
  }

  draw2d() {
    if (!this.ctx) return;
    const r = this.size2d();
    const ctx = this.ctx;
    const bg = ctx.createLinearGradient(0, 0, 0, r.height);
    bg.addColorStop(0, "#05060f");
    bg.addColorStop(1, "#03050b");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, r.width, r.height);
    this.drawNebulae2d(ctx, r);
    this.drawEdges2d(ctx, r);
    this.drawDust2d(ctx, r);
    this.drawNodes2d(ctx, r);
    this.drawLabels2d(ctx, r);
  }

  drawNebulae2d(ctx, r) {
    const uni = this.universeGroups();
    for (const grp of uni) {
      const p = this.screen2d(this.project(grp.center), r);
      const rad = 130 * this.cam2d.k * (grp.boost || 1);
      const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, rad);
      g.addColorStop(0, `${grp.color}44`);
      g.addColorStop(0.55, `${grp.color}16`);
      g.addColorStop(1, `${grp.color}00`);
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(p.x, p.y, rad, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  drawEdges2d(ctx, r) {
    ctx.lineWidth = 1;
    ctx.strokeStyle = "rgba(176,196,255,0.14)";
    for (const l of this.uEdges || []) {
      const a = state.nodeById.get(l.a);
      const b = state.nodeById.get(l.b);
      if (!a || !b) continue;
      if (!matches(a) && !matches(b)) continue;
      const pa = this.screen2d(this.project(universePoint(a)), r);
      const pb = this.screen2d(this.project(universePoint(b)), r);
      ctx.globalAlpha = 0.07 + l.score * 0.12;
      line(ctx, pa.x, pa.y, pb.x, pb.y);
    }
    ctx.globalAlpha = 1;
  }

  drawDust2d(ctx, r) {
    (this.uDust || []).forEach(pt => {
      const s = this.screen2d(this.project(pt.p), r);
      ctx.globalAlpha = pt.alpha;
      ctx.fillStyle = palette[pt.cat];
      ctx.beginPath();
      ctx.arc(s.x, s.y, pt.size * this.cam2d.k, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.globalAlpha = 1;
  }

  drawNodes2d(ctx, r) {
    (this.uNodes || []).forEach(({ n, p }) => {
      const pr = this.project(p);
      const s = this.screen2d(pr, r);
      const r0 = Math.max(1.6, n.r * 0.5 * this.cam2d.k * (0.8 + pr.d * 0.7));
      ctx.globalAlpha = opacityFor(n) * (0.38 + pr.d * 0.62);
      ctx.fillStyle = palette[n.category];
      ctx.beginPath();
      ctx.arc(s.x, s.y, r0, 0, Math.PI * 2);
      ctx.fill();
      if (state.selected?.id === n.id) {
        ctx.globalAlpha = 1;
        ctx.strokeStyle = "rgba(255,255,255,0.9)";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(s.x, s.y, r0 + 3.5, 0, Math.PI * 2);
        ctx.stroke();
      }
    });
    ctx.globalAlpha = 1;
  }

  drawLabels2d(ctx, r) {
    ctx.font = "600 17px Inter, system-ui, sans-serif";
    ctx.fillStyle = "rgba(232,238,255,0.9)";
    this.universeGroups().forEach(grp => {
      const s = this.screen2d(this.project(grp.center), r);
      ctx.fillText(grp.label, s.x + 14, s.y - 8);
    });
  }

  universeGroups() {
    const c = this.uCenters || {};
    const docs = c.Documents || { x: 0, y: 0, z: 0 };
    const imgs = c.Images || { x: 150, y: 170, z: 10 };
    const code = c.Code || { x: -120, y: 150, z: -20 };
    const vids = c.Video || { x: -160, y: -120, z: 8 };
    const oth = c.Other || { x: 140, y: -130, z: 24 };
    const sys = c.System || { x: -100, y: -90, z: -10 };
    return [
      { label: "Work", color: "#4f86ef", center: docs, boost: 1.12 },
      { label: "Money", color: "#34c37b", center: {
        x: docs.x + 160, y: docs.y - 118, z: docs.z + 44,
      }, boost: 1.0 },
      { label: "Reputation", color: "#f15fa6", center: vids, boost: 1.0 },
      { label: "Interests", color: "#e7b04a", center: oth, boost: 1.0 },
      { label: "Relationships", color: "#9a6cf9", center: {
        x: oth.x + 126, y: oth.y + 28, z: oth.z - 6,
      }, boost: 1.0 },
      { label: "Location", color: "#5db7ff", center: imgs, boost: 1.02 },
      { label: "Health", color: "#2ac6b4", center: {
        x: code.x + 92, y: code.y + 70, z: code.z - 24,
      }, boost: 0.94 },
      { label: "Expression", color: "#f39b4f", center: code, boost: 1.0 },
      { label: "System", color: "#8493ab", center: sys, boost: 0.92 },
    ];
  }

  draw() {}
}

function topEdges(limit) {
  return [...state.links].sort((a, b) => b.score - a.score).slice(0, limit);
}

function centers() {
  const cats = Object.keys(palette);
  const out = {};
  cats.forEach((cat, i) => {
    const a = Math.PI * 2 * i / cats.length - Math.PI / 2;
    out[cat] = { x: Math.cos(a) * 330, y: Math.sin(a) * 230 };
  });
  return out;
}

function computeCategoryCentroids() {
  const sums = {};
  const counts = {};
  for (const cat of Object.keys(palette)) { sums[cat] = {x:0,y:0}; counts[cat] = 0; }
  for (const n of state.nodes) {
    if (sums[n.category]) {
      sums[n.category].x += n.x || 0;
      sums[n.category].y += n.y || 0;
      counts[n.category]++;
    }
  }
  const out = {};
  for (const cat of Object.keys(palette)) {
    if (counts[cat] > 0) out[cat] = { x: sums[cat].x/counts[cat], y: sums[cat].y/counts[cat] };
  }
  return out;
}

function center(cat) {
  return centers()[cat] || centers().Other;
}

function seed(n) {
  const c = center(n.category);
  const h = hash(n.id);
  return { x: c.x + Math.cos(h) * 60, y: c.y + Math.sin(h) * 60 };
}

function visibleNodes() {
  return state.nodes;
}

function matches(n) {
  if (!state.q) return true;
  return `${n.label} ${n.path} ${n.category}`.toLowerCase().includes(state.q);
}

function opacityFor(n) {
  // Cluster focus: dim everything outside the highlighted cluster
  if (state.highlightCluster) {
    const cid = String(state.highlightCluster || "");
    if (String(n.cluster || "") !== cid) return 0.06;
    if (state.selected && String(state.selected.cluster || "") === cid) {
      return related(n, state.selected) ? 1 : 0.26;
    }
    return matches(n) ? 1 : 0.18;
  }
  if (state.selected) return related(n, state.selected) ? 1 : 0.2;
  return matches(n) ? 1 : 0.05;
}

function edgeVisible(a, b) {
  if (state.highlightCluster) {
    const cid = String(state.highlightCluster || "");
    if (String(a.cluster || "") !== cid || String(b.cluster || "") !== cid) {
      return false;
    }
  }
  if (!matches(a) && !matches(b)) return false;
  if (!state.selected) return true;
  return a.id === state.selected.id || b.id === state.selected.id;
}

function edgeSelected(a, b) {
  return state.selected && (a.id === state.selected.id ||
    b.id === state.selected.id);
}

function edgeAlpha() {
  return state.selected ? "rgba(0,0,0,0.10)" : "rgba(0,0,0,0.06)";
}

function related(a, b) {
  if (!b) return true;
  if (a.id === b.id) return true;
  return state.links.some(l => (l.a === a.id && l.b === b.id) ||
    (l.b === a.id && l.a === b.id));
}

function nodePriority(n) {
  const deg = Number(n?.degree || 0);
  const sz = Math.log10(Number(n?.size || 0) + 1);
  return deg * 1.8 + sz;
}

function mapDetailProfile(zoom = 1, total = state.nodes.length,
  focused = false) {
  let minDeg = zoom < 0.55 ? 24 :
    zoom < 0.85 ? 15 :
    zoom < 1.25 ? 10 :
    zoom < 1.9 ? 6 : 4;
  if (total > 2500) minDeg += 5;
  else if (total > 1500) minDeg += 3;
  else if (total > 800) minDeg += 2;
  if (focused) minDeg = Math.max(3, minDeg - 3);
  let cap = zoom < 0.55 ? 6 :
    zoom < 0.85 ? 10 :
    zoom < 1.25 ? 16 :
    zoom < 1.9 ? 28 : 44;
  if (total > 2500) cap -= 7;
  else if (total > 1500) cap -= 5;
  else if (total > 900) cap -= 3;
  if (focused) cap = Math.min(cap + 6, 54);
  return {
    minDeg: Math.max(3, minDeg),
    cap: Math.max(6, cap),
  };
}

function labelNodes(zoom = 1, hero = false) {
  const focus = !!state.highlightCluster;
  const prof = mapDetailProfile(zoom, state.nodes.length, focus);
  const minDeg = prof.minDeg;
  const cap = hero ? Math.max(10, Math.floor(prof.cap * 0.72)) : prof.cap;
  const priority = new Set([state.hover, state.selected].filter(Boolean));
  let relatedIds = null;
  if (state.selected) {
    relatedIds = new Set([state.selected.id]);
    for (const l of state.links) {
      if (l.a === state.selected.id) relatedIds.add(l.b);
      if (l.b === state.selected.id) relatedIds.add(l.a);
    }
  }
  const vals = state.nodes.filter(n => {
    if (n.noise) return false;
    if (priority.has(n)) return true;
    if (relatedIds && !relatedIds.has(n.id)) return false;
    if (state.highlightCluster && String(n.cluster || "") !==
        String(state.highlightCluster || "")) {
      return false;
    }
    if (state.q && !matches(n)) return false;
    if (n.degree < minDeg) return false;
    return true;
  });
  const sorted = vals.sort((a, b) => {
    // Always show hover/selected first
    if (priority.has(a) && !priority.has(b)) return -1;
    if (priority.has(b) && !priority.has(a)) return 1;
    return nodePriority(b) - nodePriority(a) ||
      String(a.id || "").localeCompare(String(b.id || ""));
  });
  // Deduplicate: only show the highest-degree node for each unique label
  const seenLabels = new Set();
  const result = [];
  for (const n of sorted) {
    const lbl = (n.label || base(n.path) || "").trim().toLowerCase();
    if (!lbl && !priority.has(n)) continue;
    if (priority.has(n) || !seenLabels.has(lbl)) {
      seenLabels.add(lbl);
      result.push(n);
      if (result.length >= cap) break;
    }
  }
  return result;
}

function category(n) {
  const p = `${n.path || ""} ${n.ext || ""}`.toLowerCase();
  if (labelNoise(p)) return "System";
  if (p.includes("/documents/") || docExt(p)) return "Documents";
  if (imgExt(p) || p.includes("/pictures/")) return "Images";
  if (codeExt(p) || p.includes("/developer/")) return "Code";
  if (videoExt(p) || p.includes("/movies/")) return "Video";
  return "Other";
}

function labelNoise(path) {
  const p = String(path).toLowerCase();
  return ["index.spotlightv3", ".fseventsd", ".ds_store", ".localized",
    "spotlight-v100", "corespotlight", ".metadata_never_index"].some(x =>
    p.includes(x));
}

function docExt(p) {
  return [".pdf", ".doc", ".docx", ".rtf", ".pages", ".txt", ".md"]
    .some(x => p.endsWith(x));
}

function imgExt(p) {
  return [".png", ".jpg", ".jpeg", ".heic", ".webp", ".gif", ".tiff"]
    .some(x => p.endsWith(x));
}

function codeExt(p) {
  return [".js", ".ts", ".py", ".swift", ".json", ".tsx", ".css", ".html"]
    .some(x => p.endsWith(x));
}

function videoExt(p) {
  return [".mov", ".mp4", ".m4v", ".avi", ".mkv"].some(x => p.endsWith(x));
}

function radius(size) {
  return clamp(Math.log((size || 0) + 1) / 2.5, 2.2, 12);
}

// Words that are tool/app names or generic OS noise — stripped from display names
const _DISPLAY_NOISE = new Set([
  "removebg","preview","image","img","pic","photo","picture","screenshot",
  "screen","capture","scan","copy","backup","final","draft","temp",
  "untitled","export","output","version","new","old","test","sample",
  "example","misc","file","document","archive",
]);

function cleanName(name) {
  return String(name || "Untitled")
    // Strip trailing hex IDs
    .replace(/[-_ ]+[a-f0-9]{8,}(\.[^.]+)?$/i, "$1")
    // Collapse separators
    .replace(/[ _-]+/g, " ")
    // Fix "word .ext" → "word.ext" (space before extension)
    .replace(/\s+(\.[a-z0-9]{1,8})$/i, "$1")
    .trim() || "Untitled";
}

const _HEX_TOKEN = /^[0-9a-f]{5,}$/i;
const _YEAR_ONLY = /^20\d{2}$|^19\d{2}$/;

function cleanDisplayTokens(stem) {
  // Remove extension, split on separators, drop noise words, bare numbers, and hex fragments
  const tokens = stem.replace(/\.[^.]+$/, "")
    .split(/[\s_\-\.]+/)
    .filter(t =>
      t.length > 1 &&
      !/^\d+$/.test(t) &&                  // drop bare numbers
      !_HEX_TOKEN.test(t) &&               // drop hex hashes (Be3ec4352a, etc.)
      !_YEAR_ONLY.test(t) &&               // drop bare years (2026, 2025)
      !_DISPLAY_NOISE.has(t.toLowerCase()) // drop tool/generic words
    );
  if (!tokens.length) return "";
  return tokens.map(t => t.charAt(0).toUpperCase() + t.slice(1)).join(" ");
}

function displayName(name, path) {
  const raw = String(name || "").trim();
  const pathBase = base(path);
  const src = raw || pathBase;

  // Handle date-prefixed filenames: 2026-05-11-some-topic-here.png → "May 11 · some topic here"
  const dateMatch = src.match(/^(\d{4})-(\d{2})-(\d{2})[_\-\s](.+)$/);
  if (dateMatch) {
    const months = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    const m = months[parseInt(dateMatch[2], 10)] || dateMatch[2];
    const d = parseInt(dateMatch[3], 10);
    const topic = cleanName(dateMatch[4]).slice(0, 38);
    return `${m} ${d} · ${topic}`;
  }

  // Fix space-before-extension artifacts (e.g. "image removebg preview 2 .png")
  const fixed = src.replace(/\s+(\.[a-z0-9]{1,8})$/i, "$1");
  const ext = fixed.includes(".") ? fixed.split(".").pop().toLowerCase() : "";
  const stem = fixed.replace(/\.[^.]+$/, "");

  // Try to produce a clean human label from the stem tokens
  const cleaned = cleanDisplayTokens(stem);
  if (cleaned.length >= 3 && !randomName(cleaned)) return cleaned.slice(0, 48);

  // Stem is all noise/hex — fall back to most-specific non-generic parent folder
  const parts = String(path).split("/").filter(Boolean);
  const parent = [...parts.slice(1, -1)].reverse()
    .find(p => !randomName(p) && !genericFolder(p));
  if (parent && !_YEAR_ONLY.test(parent)) {
    const parentClean = cleanDisplayTokens(parent);
    const extLabel = ext ? `.${ext}` : "";
    const base_ = (parentClean || parent).slice(0, 44);
    return extLabel ? `${base_} file` : base_;
  }

  // Last resort: raw basename cleaned
  const val = cleanName(src);
  if (!randomName(val)) return val.slice(0, 48);
  return ext ? `.${ext} file` : "Untitled";
}

function randomName(txt) {
  const stem = String(txt).replace(/\.[^.]+$/, "").replace(/[-_ ]/g, "");
  return /^[a-f0-9]{10,}$/i.test(stem) || /^[0-9a-f]{6,}/i.test(stem);
}

const GENERIC_DIRS = new Set([
  "documents","downloads","desktop","pictures","movies","music","users",
  "library","mobile documents","shared","home","ahmedm","ahmed",
  "icloud drive","icloudrive","application support","preferences",
  "inbox","archives","misc","other","temp","tmp","new folder",
]);

function genericFolder(p) {
  return GENERIC_DIRS.has(String(p).toLowerCase().trim());
}

function base(path) {
  return String(path || "").split("/").filter(Boolean).pop() || "Untitled";
}

function renderPanel() {
  const n = syncSelected();
  if (n) return renderFile(n);
  // Workstreams mode manages its own inspector — don't overwrite it
  if (state.manager?.name === "workstreams") return;
  if (state.manager?.name === "topology") {
    renderTopologySummary();
    return;
  }
  renderSummary();
}

function renderSummary() {
  const mode = state.manager?.name || "";
  if (mode === "vault") return renderVaultRail();
  if (mode === "audiences") return renderAudienceRail();
  if (mode === "simulations") return renderSimulationRail();
  if (mode === "exports") return renderExportRail();
  if (mode === "iris") return renderIrisRail();
  if (mode === "universe") return renderUniverseRail();

  const cats = Object.keys(palette).map(cat => [cat, countCat(cat)])
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1]);
  const largest = [...state.nodes].sort((a, b) => b.size - a.size).slice(0, 6);
  const todayCount = modifiedToday();
  const modeLabel = modeTitle[mode] || "Summary";
  const audRows = state.audiences.length ? state.audiences : defaultAudiences();
  const aud = audRows[0] || { name: "Recruiter", score: 79, summary: "" };
  const byType = cats.map(([cat, val]) => `<div class="rail-type-row">
    <span>${esc(cat)}</span><b>${val.toLocaleString()}</b></div>`).join("");
  const lgRows = largest.map(n => `<div class="rail-file-row" title="${
    esc(n.path)}"><span>${esc(n.label.slice(0, 28))}</span><b>${
    humanSize(n.size)}</b></div>`).join("");
  el.inspector.innerHTML = `
    <section class="rail-card">
      <h2 class="rail-head">${modeLabel} summary</h2>
      <div class="rail-metric-grid">
        <div class="rail-metric"><span>Files shown</span><b>${
          state.nodes.length.toLocaleString()}</b></div>
        <div class="rail-metric"><span>Clusters</span><b>${uniqueClusters()}</b></div>
        <div class="rail-metric"><span>Modified today</span><b>${
          todayCount.toLocaleString()}</b></div>
      </div>
    </section>
    <section class="rail-card">
      <div class="rail-card-head"><h3>By type</h3>
        <button class="rail-link">View all</button></div>
      ${byType || "<p class='muted'>No categories available.</p>"}
    </section>
    <section class="rail-card">
      <h3>Largest files in view</h3>
      ${lgRows || "<p class='muted'>No file rows.</p>"}
    </section>
    <section class="rail-card">
      <h3>Audience simulator</h3>
      <div class="rail-aud-main"><b>${esc(aud.name)}</b><span>${
        Number(aud.score || 0)}%</span></div>
      <p class="muted">${esc(aud.summary ||
        "Run simulation for audience-specific guidance.")}</p>
      <button class="rail-cta" type="button" data-mode-jump="simulations">
        ${mode === "timeline" ? "Inspect selected range" : "Open simulation"}
      </button>
    </section>`;
  const jump = el.inspector.querySelector("[data-mode-jump]");
  if (jump) {
    jump.addEventListener("click", () => {
      state.manager.switch(jump.dataset.modeJump);
    });
  }
}

function renderUniverseRail() {
  const hero = !!state.manager?.mode?.fallback2d;
  const total = hero ? Math.max(1200, state.nodes.length * 28) :
    visibleNodes().length;
  const clusters = hero ? 8 : uniqueClusters();
  const today = hero ? 156 : modifiedToday();
  const scaled = hero ? {
    Documents: Math.round(total * 0.68),
    Images: Math.max(13, Math.round(total * 0.03)),
    Other: Math.max(8, Math.round(total * 0.02)),
    Video: Math.max(2, Math.round(total * 0.01)),
    System: Math.max(1, Math.round(total * 0.005)),
  } : null;
  const byType = (scaled ? Object.entries(scaled) : Object.keys(palette).map(
    cat => [cat, countCat(cat)])).map(([cat, val]) => `<div class="rail-type-row">
    <span>${esc(cat)}</span><b>${Number(val).toLocaleString()}</b></div>`).join("");
  const rows = state.audiences.length ? state.audiences : defaultAudiences();
  const top = rows[0] || defaultAudiences()[0];
  el.inspector.innerHTML = `
    <section class="rail-card">
      <h2 class="rail-head">Universe overview</h2>
      <div class="rail-metric-grid">
        <div class="rail-metric"><span>Files shown</span><b>${
          total.toLocaleString()}</b></div>
        <div class="rail-metric"><span>Clusters</span><b>${clusters}</b></div>
        <div class="rail-metric"><span>Modified today</span><b>${
          today.toLocaleString()}</b></div>
      </div>
    </section>
    <section class="rail-card">
      <div class="rail-card-head"><h3>By type</h3>
        <button class="rail-link">View all</button></div>
      ${byType}
    </section>
    <section class="rail-card">
      <div class="rail-card-head"><h3>Audience Simulator</h3>
        <button class="rail-link">View all</button></div>
      <div class="rail-aud-main"><b>${esc(top.name || "Recruiter")}</b><span>${
        Number(top.score || 0)}%</span></div>
      <p class="muted">${esc(top.summary || "")}</p>
      <div class="rail-type-row"><span>Estimated reach</span><b>68%</b></div>
      <div class="rail-type-row"><span>Top strength</span><b>Technical depth</b></div>
      <div class="rail-type-row"><span>Watchouts</span><b>Low bias</b></div>
    </section>
    <section class="rail-card">
      <h3>Iris insights</h3>
      <div class="rail-file-row"><span>Breadth of interests</span><b>87 · High</b></div>
      <div class="rail-file-row"><span>Network influence</span><b>74 · Moderate</b></div>
      <div class="rail-file-row"><span>Privacy posture</span><b>68 · Moderate</b></div>
      <button class="rail-cta" type="button" data-mode-jump="iris">
        View full analysis
      </button>
    </section>`;
  el.inspector.querySelector("[data-mode-jump]")?.addEventListener("click", () =>
    state.manager.switch("iris"));
}

async function renderTopologySummary() {
  const hero = !!state.manager?.mode?.hero;
  const total = hero ? Math.max(1200, state.nodes.length * 28) :
    visibleNodes().length;
  const clusters = hero ? 12 : uniqueClusters();
  const today = hero ? 156 : modifiedToday();
  const scaled = hero ? {
    Documents: Math.round(total * 0.98),
    Images: Math.max(13, Math.round(total * 0.01)),
    Other: Math.max(8, Math.round(total * 0.008)),
    Video: Math.max(2, Math.round(total * 0.004)),
    System: Math.max(1, Math.round(total * 0.002)),
  } : null;
  el.inspector.innerHTML = `
    <section class="rail-card">
      <h2 class="rail-head">Map overview</h2>
      <div class="rail-metric-grid">
        <div class="rail-metric"><span>Signals shown</span><b>${
          total.toLocaleString()}</b></div>
        <div class="rail-metric"><span>Clusters</span><b>${clusters}</b></div>
        <div class="rail-metric"><span>Modified today</span><b>${
          today.toLocaleString()}</b></div>
      </div>
    </section>
    <section class="rail-card">
      <div class="rail-card-head"><h3>By type</h3>
        <button class="rail-link">View all</button></div>
      ${(scaled ? Object.entries(scaled) : Object.keys(palette).map(cat =>
        [cat, countCat(cat)])).map(([cat, val]) => `<div class="rail-type-row">
        <span>${esc(cat)}</span><b>${
          Number(val).toLocaleString()}</b></div>`).join("")}
    </section>
    <section class="rail-card">
      <div class="rail-card-head"><h3>Audience views</h3>
        <button class="rail-link">Manage</button></div>
      <div id="mapAudienceRows">
        <div class="cards-loading"><span class="pulse-dot"></span>
          <span>Loading audiences…</span></div>
      </div>
    </section>
    <section class="rail-card">
      <div class="rail-card-head"><h3>Iris summary</h3>
        <span class="muted">Updated ${
          esc(state.homeData?.last_analyzed_ago || "recently")}</span></div>
      <div id="mapIrisSummary" class="muted">Loading…</div>
      <button class="rail-cta" type="button" data-mode-jump="universe">
        Open in Universe
      </button>
    </section>`;
  el.inspector.querySelector("[data-mode-jump]")?.addEventListener("click", () =>
    state.manager.switch("universe"));
  await Promise.all([refreshAudiences(), refreshHomeData()]);
  if (state.manager?.name !== "topology" || state.selected) return;
  const rows = state.audiences.length ? state.audiences : defaultAudiences();
  const wrap = el.inspector.querySelector("#mapAudienceRows");
  if (wrap) {
    wrap.innerHTML = rows.map(row => {
      const score = Number(row.score || 0);
      const barW = Math.max(8, Math.min(100, score));
      const barColor = score >= 70 ? "#22c55e" : score >= 50 ? "#f59e0b" : "#ef4444";
      const label = (row.name || row.id || "").replace(/\s+read$/i, "").trim();
      return `<button class="map-aud-row" data-aud="${esc(row.id)}">
        <div class="map-aud-top">
          <span class="map-aud-icon">${esc(row.icon || "👤")}</span>
          <span class="map-aud-label">${esc(label)}</span>
          <span class="map-aud-pct">${score}%</span>
        </div>
        <div class="map-aud-bar-track">
          <div class="map-aud-bar" style="width:${barW}%;background:${barColor}"></div>
        </div>
        <p class="map-aud-desc">${esc(row.summary || "")}</p>
      </button>`;
    }).join("");
    wrap.querySelectorAll(".map-aud-row[data-aud]").forEach(btn => {
      btn.addEventListener("click", () => openAudienceModal(btn.dataset.aud));
    });
  }
  const summary = state.homeSummary || state.homeData?.iris_summary || null;
  const sm = el.inspector.querySelector("#mapIrisSummary");
  if (sm) {
    if (summary) {
      sm.innerHTML = window.marked
        ? mdHtml(summary)
        : esc(summary).replace(/\n/g, "<br>");
      sm.classList.add("iris-content");
    } else {
      sm.innerHTML = `<span class="pulse-dot"></span> Summary generating…`;
    }
  }
}

function renderVaultRail() {
  const hd = state.homeData || {};
  const used = Number(hd.total_size || 0);
  const cap = Math.max(used * 1.35, 500 * 1024 * 1024 * 1024);
  const pct = Math.round((used / cap) * 100);
  el.inspector.innerHTML = `
    <section class="rail-card">
      <h2 class="rail-head">Storage health</h2>
      <div class="rail-ring">${pct}% used</div>
      <div class="rail-type-row"><span>Used</span><b>${humanSize(used)}</b></div>
      <div class="rail-type-row"><span>Free</span><b>${humanSize(cap - used)}</b></div>
    </section>
    <section class="rail-card">
      <div class="rail-card-head"><h3>Index coverage</h3><span class="rail-chip">
        Up to date</span></div>
      <div class="rail-progress"><span style="width:${pct}%"></span></div>
      <p class="muted">${state.nodes.length.toLocaleString()} files indexed</p>
    </section>
    <section class="rail-card">
      <h3>Sync status</h3>
      <div class="rail-type-row"><span>iCloud Drive</span><b>Up to date</b></div>
      <div class="rail-type-row"><span>Google Drive</span><b>Up to date</b></div>
      <div class="rail-type-row"><span>Local folders</span><b>Up to date</b></div>
    </section>
    <section class="rail-card">
      <h3>Privacy guardrails</h3>
      <div class="rail-type-row"><span>No network uploads</span><b>Always</b></div>
      <div class="rail-type-row"><span>PII redaction</span><b>On</b></div>
      <div class="rail-type-row"><span>Entry point</span>
        <b>Left rail Settings</b></div>
    </section>`;
}

function renderAudienceRail() {
  const rows = state.audiences.length ? state.audiences : defaultAudiences();
  const top = rows[0] || { name: "Recruiter", score: 79, summary: "" };
  el.inspector.innerHTML = `
    <section class="rail-card">
      <div class="rail-card-head"><h2 class="rail-head">${esc(top.name)}</h2>
        <span class="rail-chip">${Number(top.score || 0) >= 75 ? "High" : "Moderate"} confidence</span></div>
      <div class="rail-aud-main"><b>${Number(top.score || 0)}%</b><span>Overall impression</span></div>
      <p class="muted">${esc(top.summary || "")}</p>
    </section>
    <section class="rail-card">
      <h3>Top evidence driving score</h3>
      ${[...state.nodes].slice(0, 5).map(n => `<div class="rail-file-row">
        <span>${esc(base(n.path))}</span><b>${esc(n.category)}</b></div>`).join("")}
    </section>
    <section class="rail-card">
      <h3>What to improve next</h3>
      <div class="rail-file-row"><span>Add recent metrics</span><b>Learn</b></div>
      <div class="rail-file-row"><span>Increase leadership visibility</span><b>Learn</b></div>
      <div class="rail-file-row"><span>Share public content</span><b>Learn</b></div>
      <button class="rail-cta" type="button" data-mode-jump="simulations">Run simulation</button>
    </section>`;
  el.inspector.querySelector("[data-mode-jump]")?.addEventListener("click", () =>
    state.manager.switch("simulations"));
}

function renderSimulationRail() {
  const rows = state.audiences.length ? state.audiences : defaultAudiences();
  const out = rows.slice(0, 4).map(r => {
    const now = Number(r.score || 0);
    const aft = Math.min(99, now + 6 + (r.id === "recruiter" ? 4 : 0));
    return `<div class="rail-sim-row"><span>${esc(r.name || r.id)}</span>
      <b>${now}%</b><b>${aft}%</b><b class="good">+${aft - now}%</b></div>`;
  }).join("");
  el.inspector.innerHTML = `
    <section class="rail-card">
      <h2 class="rail-head">Projected outcomes</h2>
      <p class="muted">How this scenario may shift audience perception.</p>
      <div class="rail-sim-head"><span>Audience</span><span>Current</span>
        <span>After</span><span>Delta</span></div>
      ${out}
    </section>
    <section class="rail-card">
      <h3>Recommended next actions</h3>
      <div class="rail-file-row"><span>Publish case study</span><b>↗</b></div>
      <div class="rail-file-row"><span>Add endorsements</span><b>↗</b></div>
      <div class="rail-file-row"><span>Remove noisy files</span><b>↗</b></div>
      <button class="rail-cta">View all suggestions</button>
    </section>`;
}

function renderExportRail() {
  const mode = state.manager?.modes?.exports;
  const hist = mode?.history || [];
  el.inspector.innerHTML = `
    <section class="rail-card">
      <h2 class="rail-head">Destination</h2>
      <div class="rail-file-row"><span>Local vault (this device)</span><b>Recommended</b></div>
      <div class="rail-file-row"><span>Secure link</span><b>Encrypted</b></div>
      <div class="rail-file-row"><span>Email delivery</span><b>Optional</b></div>
    </section>
    <section class="rail-card">
      <h3>Privacy & compliance</h3>
      <div class="rail-type-row"><span>No data leaves your device</span><b>Always</b></div>
      <div class="rail-type-row"><span>PII removed</span><b>Applied</b></div>
      <div class="rail-type-row"><span>Anonymization</span><b>Applied</b></div>
      <div class="rail-type-row"><span>Content safe for sharing</span><b>Passed</b></div>
    </section>
    <section class="rail-card">
      <h3>Recent exports</h3>
      ${(hist.slice(0, 4).map(h => `<div class="rail-file-row"><span>${
        esc(h.kind)}</span><b>${humanSize(Number(h.bytes || 0))}</b></div>`).join(""))
      || "<p class='muted'>No exports yet.</p>"}
    </section>`;
}

function renderSettingsRail() {
  const ops = state.manager?.modes?.settings?.ops || {};
  const runs = Number(ops?.index?.runs_total || 0);
  const latest = ops?.index?.latest_run || "none";
  const free = humanSize(Number(ops?.storage?.free_bytes || 0));
  el.inspector.innerHTML = `
    <section class="rail-card">
      <div class="rail-card-head"><h2 class="rail-head">System health</h2>
        <button class="rail-link">View details</button></div>
      <div class="rail-type-row"><span>Index service</span><b>Running</b></div>
      <div class="rail-type-row"><span>Analysis engine</span><b>Running</b></div>
      <div class="rail-type-row"><span>Model status</span><b>Up to date</b></div>
      <div class="rail-type-row"><span>Runs</span><b>${runs}</b></div>
      <div class="rail-type-row"><span>Latest</span><b>${esc(latest)}</b></div>
      <div class="rail-type-row"><span>Storage free</span><b>${free}</b></div>
    </section>
    <section class="rail-card">
      <h3>Backup & restore</h3>
      <div class="rail-file-row"><span>Last backup</span><b>Today</b></div>
      <div class="rail-file-row"><span>Auto-backup</span><b>Daily</b></div>
      <div class="rail-file-row"><span>Restore from backup</span><b>Ready</b></div>
    </section>
    <section class="rail-card rail-danger">
      <h3>Danger zone</h3>
      <div class="rail-file-row"><span>Rebuild index</span><b>Rebuild</b></div>
      <div class="rail-file-row"><span>Clear cache</span><b>Clear</b></div>
      <div class="rail-file-row"><span>Forget this device</span><b>Forget</b></div>
    </section>`;
}

function renderIrisRail() {
  const rows = state.audiences.length ? state.audiences : defaultAudiences();
  const selected = rows.slice(0, 4).map(r => `<div class="rail-type-row">
    <span>${esc(r.name || r.id)}</span><b>${Number(r.score || 0)}%</b></div>`)
    .join("");
  el.inspector.innerHTML = `
    <section class="rail-card">
      <div class="rail-card-head"><h2 class="rail-head">Active context</h2>
        <button class="rail-link">Edit</button></div>
      <div class="rail-type-row"><span>Local vault</span><b>${state.nodes.length.toLocaleString()} files</b></div>
      <div class="rail-type-row"><span>Clusters selected</span><b>${uniqueClusters()}</b></div>
      <div class="rail-type-row"><span>Time range</span><b>Last 90 days</b></div>
    </section>
    <section class="rail-card">
      <h3>Audience views</h3>
      ${selected}
    </section>
    <section class="rail-card">
      <h3>Quick tools</h3>
      <div class="rail-file-row"><span>Summarize this context</span><b>↗</b></div>
      <div class="rail-file-row"><span>Risk check</span><b>↗</b></div>
      <div class="rail-file-row"><span>Cleanup suggestions</span><b>↗</b></div>
      <button class="rail-cta" type="button" data-mode-jump="simulations">
        Apply recommendation
      </button>
    </section>`;
  el.inspector.querySelector("[data-mode-jump]")?.addEventListener("click", () =>
    state.manager.switch("simulations"));
}

function defaultAudiences() {
  return [
    {
      id: "recruiter",
      name: "Recruiter read",
      icon: "👤",
      score: 80,
      summary: "Most likely a strong fit for technical leadership roles.",
    },
    {
      id: "investor",
      name: "Investor read",
      icon: "💰",
      score: 76,
      summary: "High builder signal with owner mindset.",
    },
    {
      id: "lender",
      name: "Lender read",
      icon: "🏛",
      score: 72,
      summary: "Low risk with stable financial behavior.",
    },
    {
      id: "stranger",
      name: "Stranger read",
      icon: "👁",
      score: 68,
      summary: "Creative and thoughtful with broad interests.",
    },
  ];
}

function ensureClusterLabelLayer() {
  if (ui.labels?.isConnected) return ui.labels;
  let layer = document.querySelector("#cluster-labels");
  if (!layer) {
    layer = document.createElement("div");
    layer.id = "cluster-labels";
    layer.className = "cluster-labels-layer";
    layer.style.pointerEvents = "none";
    layer.hidden = true;
    el.viewport.appendChild(layer);
  }
  ui.labels = layer;
  return layer;
}

function ensureMapToolbar() {
  if (ui.map?.root?.isConnected) return ui.map;
  let root = document.querySelector("#mapToolbar");
  if (!root) {
    root = document.createElement("div");
    root.id = "mapToolbar";
    root.className = "map-toolbar";
    root.hidden = true;
    root.setAttribute("role", "toolbar");
    root.setAttribute("aria-label", "Map tools");
    root.innerHTML = `
      <button type="button" class="map-tool active" data-tool="pan"
        title="Pan" aria-pressed="true">✥</button>
      <button type="button" class="map-tool" data-tool="focus"
        title="Focus selection" aria-pressed="false">◎</button>
      <button type="button" class="map-reset"
        title="Reset focus and fit view">↺</button>
      <div class="map-toolbar-sep"></div>
      <button type="button" class="map-zoom-out" title="Zoom out">−</button>
      <span class="map-zoom-val">100%</span>
      <button type="button" class="map-zoom-in" title="Zoom in">+</button>`;
    el.viewport.appendChild(root);
  }
  root.style.pointerEvents = "auto";
  ui.map = {
    root,
    zoom: root.querySelector(".map-zoom-val"),
  };
  return ui.map;
}

function ensureMapHint() {
  if (ui.hint?.isConnected) return ui.hint;
  let hint = document.querySelector("#mapHint");
  if (!hint) {
    hint = document.createElement("div");
    hint.id = "mapHint";
    hint.className = "canvas-hint";
    hint.textContent = "Drag to pan · Scroll to zoom · Click to select";
    hint.hidden = true;
    el.viewport.appendChild(hint);
  }
  hint.style.pointerEvents = "none";
  ui.hint = hint;
  return hint;
}

function ensureAudienceModal() {
  if (ui.modal?.isConnected) return ui.modal;
  let modal = document.querySelector("#audienceModal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "audienceModal";
    modal.className = "audience-modal-overlay";
    modal.hidden = true;
    modal.innerHTML = `
      <div class="audience-modal glass">
        <div class="audience-modal-head">
          <div class="audience-modal-who">
            <span class="audience-modal-icon">👤</span>
            <div>
              <div class="audience-modal-name">Audience</div>
              <div class="audience-modal-sub">How they read your footprint</div>
            </div>
          </div>
          <div class="audience-modal-score">
            <span class="audience-score-num">--%</span>
            <span class="audience-score-lbl">match</span>
          </div>
          <button class="audience-modal-close" type="button">✕</button>
        </div>
        <div class="audience-modal-body"></div>
      </div>`;
    document.body.appendChild(modal);
  }
  if (!modal.dataset.bound) {
    modal.dataset.bound = "1";
    modal.addEventListener("click", ev => {
      if (ev.target === modal || ev.target.closest(".audience-modal-close")) {
        closeAudienceModal();
      }
    });
    document.addEventListener("keydown", ev => {
      if (ev.key === "Escape") closeAudienceModal();
    });
  }
  ui.modal = modal;
  return modal;
}

function closeAudienceModal() {
  const modal = ensureAudienceModal();
  if (modal.hidden) return false;
  modal.hidden = true;
  return true;
}

async function openAudienceModal(audId = "recruiter") {
  const modal = ensureAudienceModal();
  modal.hidden = false;
  const body = modal.querySelector(".audience-modal-body");
  const icon = modal.querySelector(".audience-modal-icon");
  const name = modal.querySelector(".audience-modal-name");
  const score = modal.querySelector(".audience-score-num");
  const prof = state.audiences.find(a => a.id === audId) ||
    defaultAudiences().find(a => a.id === audId) || defaultAudiences()[0];
  icon.textContent = prof.icon || "👤";
  name.textContent = prof.name || "Audience read";
  score.textContent = "--%";
  body.innerHTML = `<div class="cards-loading"><span class="pulse-dot"></span>
    <span>Simulating audience view…</span></div>`;
  try {
    const data = await getJson(`/api/simulate/${encodeURIComponent(audId)}`);
    state.audienceCache.set(audId, data);
    const highs = (data.highlights || []).map(v =>
      `<span class="ws-topic">${esc(v)}</span>`).join("");
    const risks = (data.risks || []).map(v =>
      `<span class="ws-topic">${esc(v)}</span>`).join("");
    score.textContent = `${Number(data.score || 0)}%`;
    body.innerHTML = `
      <div class="audience-section">
        <div class="audience-section-title">What they see</div>
        <div class="audience-narrative">${esc(data.narrative || "")}</div>
      </div>
      <div class="audience-section">
        <div class="audience-section-title">Your strongest signals</div>
        <div class="audience-highlights">${highs || "<span class=\"muted\">None</span>"}</div>
      </div>
      <div class="audience-section">
        <div class="audience-section-title">Gaps and risks</div>
        <div class="audience-risks">${risks || "<span class=\"muted\">None</span>"}</div>
      </div>`;
  } catch (err) {
    body.innerHTML = `<p class="muted">Could not simulate audience:
      ${esc(apiMsg(err))}</p>`;
  }
}

function fileRow(n) {
  return `<div class="stat-row ana-row" data-nid="${esc(n.id)}" style="cursor:pointer">
    <span title="${esc(n.path)}">${esc(n.label.slice(0,26))}</span>
    <b>${humanSize(n.size)}</b></div>`;
}

function catRow([cat, val]) {
  return `<div class="stat-row"><span style="color:${palette[cat]}">${cat}</span><b>${val.toLocaleString()}</b></div>`;
}

function renderFile(n) {
  const wsMode = state.manager?.modes?.workstreams;
  const ws = wsMode?.workstreams?.find(w => w.id === n.cluster);
  const colorMap = { blue:"#5b9cf6", teal:"#2dd4bf", amber:"#fbbf24",
                     coral:"#f87171", purple:"#a78bfa", gray:"#6b7280" };
  const wsRow = ws
    ? `<div class="stat-row"><span>Workstream</span>
         <b style="color:${colorMap[ws.color]||colorMap.blue};font-size:11px;max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(ws.name)}</b></div>`
    : "";
  const tagsHtml = (n.tags||[]).length
    ? `<div style="margin:8px 0;display:flex;flex-wrap:wrap;gap:4px">${n.tags.map(t=>`<span class="ws-topic">${esc(t)}</span>`).join("")}</div>`
    : "";

  el.inspector.innerHTML = `
    <h2 class="panel-title" style="line-height:1.3">${esc(n.label)}</h2>
    <p class="path" style="margin-bottom:8px;word-break:break-all">${esc(n.path)}</p>
    <span class="badge" style="color:${palette[n.category]}">${n.category}</span>
    ${tagsHtml}
    <div class="stat-grid">
      <div class="stat-row"><span>Size</span><b>${humanSize(n.size)}</b></div>
      <div class="stat-row"><span>Modified</span><b>${relTime(n.mtime)}</b></div>
      <div class="stat-row"><span>Connections</span><b>${n.degree}</b></div>
      ${wsRow}
    </div>
    <div id="renameCard"></div>
    <div id="filePreview"></div>
    <div id="inferPanel"></div>
    <div class="actions">
      <button data-act="entity">Identity</button>
      <button data-act="infer">Iris inference</button>
      <button data-act="rename">Rename with AI</button>
      <button data-act="similar">Find Similar</button>
      <button data-act="open">Open in Finder</button>
    </div>`;
  el.inspector.querySelector(".actions").addEventListener("click", action);
  // Load text preview async if available in graph node
  if (n.text) {
    const snippet = String(n.text).trim().slice(0, 220);
    if (snippet.length > 30) {
      el.inspector.querySelector("#filePreview").innerHTML =
        `<div class="file-preview">${esc(snippet)}${snippet.length === 220 ? "…" : ""}</div>`;
    }
  }
  // renderInference() removed — use "Iris inference" button which calls irisInferFile()
}

function action(ev) {
  const act = ev.target.dataset.act;
  if (act === "open") return openFinder(state.selected);
  if (act === "infer") return irisInferFile(state.selected);
  if (act === "entity") return irisEntityFile(state.selected);
  if (act === "similar") return showSimilar();
  if (act === "rename") return renameWithAI();
}

function irisInferFile(n) {
  if (!n) return;
  const q = `Analyze this file: "${n.label}" (${humanSize(n.size)}, ${relTime(n.mtime)}). Path: ${n.path}. Tell me what it is, what workstream it belongs to, and what I should do with it.`;
  streamIris(q);
}

function irisEntityFile(n) {
  if (!n) return;
  state.irisEntityIds = [n.id];
  if (!IDENTITY_MODES.has(state.irisMode)) {
    state.irisMode = "entity";
    el.irisModebar?.querySelectorAll("button[data-imode]").forEach(b => {
      b.classList.toggle("active", b.dataset.imode === "entity");
    });
    el.draft.placeholder = "Ask about this file: what does it reveal?";
    updateIrisChips("entity");
  }
  updateEntityBar(state.irisMode);
  streamIris(`What does this file reveal about me? Analyze "${n.label}" as an identity evidence entity.`);
}

function inferFromCluster(clusterId) {
  const nodes = state.nodes.filter(n => n.cluster === clusterId);
  if (!nodes.length) return;
  nodes.sort((a, b) => b.degree - a.degree);
  state.selected = nodes[0];
  if (state.manager?.name !== "topology") state.manager.switch("topology");
  renderPanel();
  state.manager?.mode?.draw?.();
}

async function renderInference(force = false) {
  const sel = syncSelected();
  const panel = el.inspector.querySelector("#inferPanel");
  if (!sel || !panel) return;
  panel.innerHTML = `<p class="muted">Iris inference loading…</p>`;
  const run = encodeURIComponent(state.run || "");
  const cluster = encodeURIComponent(sel.cluster || "");
  const q = force ? "&refresh=1" : "";
  try {
    const data = await getJson(`/api/infer?run=${run}&cluster=${cluster}${q}`);
    drawInference(panel, data);
  } catch (err) {
    panel.innerHTML = `<p class="muted">Iris inference failed: ${esc(apiMsg(err))}</p>`;
  }
}

function drawInference(panel, data) {
  const claims = data.claims || [];
  const by = {
    behavior: claims.filter(c => c.family === "behavior"),
    projects: claims.filter(c => c.family === "projects"),
    risk: claims.filter(c => c.family === "risk"),
  };
  panel.innerHTML = `
    <h3 class="panel-title" style="margin-top:12px">Iris inference</h3>
    <div class="stat-grid">
      <div class="stat-row"><span>Source</span><b>${esc(data.source || "n/a")}</b></div>
      <div class="stat-row"><span>Claims</span><b>${claims.length}</b></div>
      <div class="stat-row"><span>Model</span><b>${esc(data.model || "n/a")}</b></div>
    </div>
    <div class="chips" id="inferFilt" style="margin:8px 0 10px">
      <button data-f=\"all\">All</button>
      <button data-f=\"behavior\">Behavior</button>
      <button data-f=\"projects\">Projects</button>
      <button data-f=\"risk\">Risk</button>
    </div>
    <div id="inferClaims">${renderClaims(claims)}</div>`;
  const filt = panel.querySelector("#inferFilt");
  filt.addEventListener("click", ev => {
    const btn = ev.target.closest("button[data-f]");
    if (!btn) return;
    const key = btn.dataset.f;
    const vals = key === "all" ? claims : by[key] || [];
    panel.querySelector("#inferClaims").innerHTML = renderClaims(vals);
    bindInferEvidence(panel);
  });
  bindInferEvidence(panel);
}

function renderClaims(claims) {
  if (!claims.length) return `<p class="muted">No inference claims for this cluster.</p>`;
  return claims.map(cl => {
    const conf = Math.round((cl.confidence || 0) * 100);
    const sev = cl.severity ? ` · ${cl.severity}` : "";
    const tent = cl.tentative ? " (tentative)" : "";
    const ev = (cl.evidence || []).slice(0, 3).map(e =>
      `<span class=\"msg-related-item\" data-id=\"${esc(e.id || "")}\" title=\"${esc(e.path || "")}\">${esc(base(e.path || "").slice(0, 24) || "evidence")} · ${Math.round((e.score || 0) * 100)}%</span>`
    ).join("");
    return `<div class="rename-card" style="margin-bottom:8px">
      <p><b>${esc(cl.title || cl.category || "claim")}</b> · ${conf}%${sev}${tent}</p>
      <p class="muted">${esc(cl.summary || "")}</p>
      <div class="msg-related">${ev}</div>
    </div>`;
  }).join("");
}

function bindInferEvidence(panel) {
  panel.querySelectorAll(".msg-related-item[data-id]").forEach(it => {
    it.addEventListener("click", () => {
      const nid = it.dataset.id;
      const n = state.nodeById.get(nid);
      if (!n) return;
      state.selected = n;
      renderPanel();
      state.manager?.mode?.draw?.();
    });
  });
}

function showSimilar() {
  const n = state.selected;
  if (!n) return;
  // Collect connected nodes sorted by link score
  const scored = [];
  state.links.forEach(l => {
    if (l.a === n.id) scored.push({ id: l.b, score: l.score });
    if (l.b === n.id) scored.push({ id: l.a, score: l.score });
  });
  scored.sort((a, b) => b.score - a.score);
  const connected = scored
    .map(s => ({ node: state.nodeById.get(s.id), score: s.score }))
    .filter(s => s.node);

  if (!connected.length) {
    addMsg(`No similar files found for "${n.label}" — it may be isolated in this graph.`, "assistant");
    return;
  }

  const rows = connected.slice(0, 12).map(({ node: cn, score }) => {
    const pct = Math.round(score * 100);
    const barColor = pct >= 72 ? "var(--green)" : pct >= 50 ? "var(--amber)" : "var(--blue)";
    return `<div class="stat-row ana-row" data-nid="${esc(cn.id)}" style="cursor:pointer">
      <span title="${esc(cn.path)}">${esc(cn.label.slice(0, 30))}</span>
      <b style="color:${barColor}">${pct}%</b></div>`;
  }).join("");

  el.inspector.innerHTML = `
    <h2 class="panel-title">Similar to <span style="color:var(--blue)">${esc(n.label.slice(0,22))}</span></h2>
    <p class="muted" style="margin-bottom:8px">${connected.length} related files · by semantic link score</p>
    <div class="stat-grid">${rows}</div>
    <div class="actions" style="margin-top:10px">
      <button id="backToFile">← Back</button>
      <button id="switchToMap">View in Map</button>
      <button id="askIrisSimilar">Ask Iris</button>
    </div>`;
  el.inspector.querySelector("#backToFile").onclick = () => renderPanel();
  el.inspector.querySelector("#switchToMap").onclick = () => {
    if (state.manager.name !== "topology") state.manager.switch("topology");
    else state.manager.mode.draw();
  };
  el.inspector.querySelector("#askIrisSimilar")?.addEventListener("click", () => {
    const names = connected.slice(0, 6).map(c => c.node.label).join(", ");
    streamIris(`What do "${n.label}" and these similar files have in common: ${names}?`);
  });
  bindAnalyzeRows();

  // Glow connected nodes in graph
  const connectedIds = new Set(scored.map(s => s.id));
  state.nodes.forEach(cn => { cn.glow = connectedIds.has(cn.id) ? 20 : 0; });
  if (state.manager?.mode?.draw) state.manager.mode.draw();
}

async function renameWithAI() {
  const res = await ask("Suggest a safer filename", "rename");
  const name = res.rename_proposals?.[0]?.name || "";
  const why = res.rename_proposals?.[0]?.why || res.answer;
  renameCard(name, why);
}

function renameCard(name, why) {
  const card = el.inspector.querySelector("#renameCard");
  card.innerHTML = `<div class="rename-card"><p class="muted">${esc(why)}</p>
    <input value="${esc(name)}">
    <button data-apply="1">Apply</button>
    <button data-skip="1">Skip</button></div>`;
  card.querySelector("[data-apply]").onclick = () => applyRename(card);
  card.querySelector("[data-skip]").onclick = () => card.innerHTML = "";
}

async function applyRename(card) {
  const sel = syncSelected();
  if (!sel) {
    card.querySelector("p").textContent = "Selection no longer exists.";
    card.querySelector("p").style.color = "var(--coral)";
    return;
  }
  const name = card.querySelector("input").value.trim();
  try {
    const res = await postJson("/api/rename", { path: sel.path, name });
    // Update the node in-memory so the graph and inspector reflects rename.
    if (sel) {
      sel.path = res.path;
      sel.label = displayName(name, res.path);
      if (state.manager?.mode?.draw) state.manager.mode.draw();
    }
    card.querySelector("p").textContent = `Renamed to ${name}`;
    renderFile(sel); // refresh inspector with new name
  } catch (err) {
    card.querySelector("p").textContent = `Rename failed: ${apiMsg(err)}`;
    card.querySelector("p").style.color = "var(--coral)";
  }
}

function openFinder(n) {
  if (!n) return;
  getJson(`/api/open?mode=reveal&path=${encodeURIComponent(n.path)}`);
}

async function sendDraft(ev) {
  ev.preventDefault();
  const q = el.draft.value.trim();
  if (!q) return;
  if (state.irisStreaming) abortActiveIris();
  el.draft.value = "";
  syncChatSend();
  await streamIris(q);
  syncChatSend();
}

function syncChatSend() {
  const btn = el.chatForm?.querySelector(".chatbox-send");
  if (!btn) return;
  const hasText = el.draft?.value.trim().length > 0;
  btn.disabled = !hasText || state.irisStreaming;
}

async function chip(ev) {
  const btn = ev.target.closest("button[data-q]");
  if (!btn) return;
  if (state.irisStreaming) abortActiveIris();
  const q = btn.dataset.q;
  // Instant DB-powered analysis for specific questions (no LLM wait)
  if (q === "What's using the most space?") {
    analyzeLocal("largest");
    return;
  }
  if (q === "What should I delete?") {
    analyzeLocal("old_downloads");
    return;
  }
  if (q === "Find duplicate files" || q === "Find stale downloads") {
    analyzeLocal(q === "Find stale downloads" ? "old_downloads" : "duplicates");
    return;
  }
  await streamIris(q);
}

// ─── Iris streaming engine ────────────────────────────────────────────────────

function activeIrisFeed() {
  const inline = document.querySelector("#irisDialogScroll");
  if (state.manager?.name === "iris" && inline) return inline;
  return el.messages;
}

function irisTimeoutMs() {
  const raw = Number(state.settings?.scan_rules?.timeout_s || 0);
  const sec = Number.isFinite(raw) && raw > 0 ? raw : 120;
  return Math.max(12000, Math.min(240000, sec * 1000));
}

function abortActiveIris() {
  const ctrl = state.irisAbort;
  if (!ctrl) return;
  state.irisAbort = null;
  try {
    ctrl.abort();
  } catch (_) {}
}

async function streamIris(q) {
  if (state.irisStreaming) abortActiveIris();
  const reqSeq = state.irisReqSeq + 1;
  state.irisReqSeq = reqSeq;
  const ctrl = new AbortController();
  state.irisAbort = ctrl;
  state.irisStreaming = true;
  syncChatSend();
  const feed = activeIrisFeed();
  const empty = feed.querySelector(".iris-inline-empty");
  if (empty) empty.remove();

  // User bubble
  const userDiv = document.createElement("div");
  userDiv.className = "msg user";
  userDiv.textContent = q;
  feed.appendChild(userDiv);
  feed.scrollTop = feed.scrollHeight;

  // Dismiss welcome message on first real interaction
  const welcome = feed.querySelector(".msg-welcome");
  if (welcome) welcome.remove();

  // Assistant streaming bubble
  const botDiv = document.createElement("div");
  botDiv.className = "msg assistant iris-streaming";
  const contentEl = document.createElement("div");
  contentEl.className = "iris-content";
  const cursor = document.createElement("span");
  cursor.className = "iris-cursor";
  botDiv.appendChild(contentEl);
  botDiv.appendChild(cursor);
  feed.appendChild(botDiv);
  feed.scrollTop = feed.scrollHeight;

  let fullText = "";
  const toolCards = new Map();
  const toolSeqByName = new Map();
  const hardTm = setTimeout(() => {
    try {
      ctrl.abort();
    } catch (_) {}
  }, irisTimeoutMs());

  try {
    const resp = await fetch("/api/iris", {
      method: "POST",
      headers: { "content-type": "application/json" },
      signal: ctrl.signal,
      body: JSON.stringify({
        q,
        run: activeRun(),
        mode: state.irisMode || "report",
        history: compactIrisHistory(state.irisHistory),
        selected_ids: state.irisEntityIds.slice(0, 6),
        audience: state.irisAudience || "recruiter",
      }),
    });

    if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop(); // keep incomplete last line
      for (const raw of lines) {
        const line = raw.trim();
        if (!line) continue;
        let chunk;
        try { chunk = JSON.parse(line); } catch (_) { continue; }

        if (chunk.type === "token") {
          fullText += chunk.content;
          contentEl.textContent = fullText; // plain text while streaming
          feed.scrollTop = feed.scrollHeight;

        } else if (chunk.type === "tool_start") {
          const nm = String(chunk.name || "tool");
          const idx = Number(toolSeqByName.get(nm) || 0) + 1;
          toolSeqByName.set(nm, idx);
          const tid = String(chunk.id || `${nm}:${idx}`);
          const card = makeToolCard(chunk.name, chunk.preview || "");
          botDiv.insertBefore(card, cursor);
          toolCards.set(tid, card);
          feed.scrollTop = feed.scrollHeight;

        } else if (chunk.type === "tool_end") {
          const nm = String(chunk.name || "tool");
          const idx = Number(toolSeqByName.get(nm) || 1);
          const tid = String(chunk.id || `${nm}:${idx}`);
          const card = toolCards.get(tid);
          if (card) finishToolCard(card, chunk.ms != null ? `${chunk.ms}ms` : "done", 0);

        } else if (chunk.type === "done") {
          // Collapse all finished tool cards to a single subtle line
          toolCards.forEach(card => { card.hidden = true; });

        } else if (chunk.type === "error") {
          if (!fullText.trim()) {
            fullText = `Iris error: ${chunk.message}`;
          }
        }
      }
    }
  } catch (err) {
    const msg = apiMsg(err);
    const stop = String(err?.name || "") === "AbortError";
    if (stop && reqSeq !== state.irisReqSeq) {
      fullText = "Interrupted.";
    } else if (stop) {
      fullText = "Iris request timed out. Try a shorter question.";
    } else {
      fullText = `Iris is unavailable: ${msg}. Make sure Ollama is running.`;
    }
  }
  clearTimeout(hardTm);

  // Remove cursor + render markdown
  cursor.remove();
  botDiv.classList.remove("iris-streaming");
  if (fullText) {
    state.irisErrStreak = 0;
    if (window.marked) {
      contentEl.innerHTML = mdHtml(fullText);
    } else {
      contentEl.textContent = fullText;
    }
  } else {
    state.irisErrStreak += 1;
    contentEl.textContent = "(no response)";
  }

  // Push to multi-turn history
  state.irisHistory.push({ role: "user", content: q.slice(0, 1800) });
  state.irisHistory.push({
    role: "assistant",
    content: String(fullText || "").slice(0, 2400),
  });
  // Keep history bounded (last 20 turns)
  if (state.irisHistory.length > 24) state.irisHistory.splice(0, 4);

  if (reqSeq === state.irisReqSeq) {
    state.irisAbort = null;
    state.irisStreaming = false;
    syncChatSend();
  }
  feed.scrollTop = feed.scrollHeight;
}

function makeToolCard(name, preview) {
  const div = document.createElement("div");
  div.className = "tool-card";
  div.innerHTML = `<div class="tool-card-head">
    <span class="tool-card-icon">⟳</span>
    <span class="tool-card-name">${esc(name.replace(/_/g, " "))}</span>
    ${preview ? `<span class="tool-card-args">${esc(preview)}</span>` : ""}
    <span class="tool-card-status">running…</span>
  </div>`;
  return div;
}

function finishToolCard(card, preview, resultLen) {
  card.classList.add("done");
  const icon = card.querySelector(".tool-card-icon");
  const status = card.querySelector(".tool-card-status");
  if (icon) icon.textContent = "✓";
  if (status) {
    status.textContent = preview || `${resultLen} bytes`;
    status.classList.add("done");
  }
}

// ─── Legacy ask() for rename + old APIs ──────────────────────────────────────
async function sendPrompt(q) {
  // Legacy: plain text, no streaming. Used internally.
  addMsg(q, "user");
  try {
    const res = await ask(q, kindFrom(q));
    const answer = res.answer || "No answer returned.";
    addMsg(answer, "assistant", res.related || []);
  } catch (err) {
    addMsg(assistantErr(err), "assistant");
  }
}

async function ask(q, kind = "question") {
  const node = syncSelected() || state.nodes[0];
  let enrichedQ = q;
  if (!state.selected && state.manager?.name === "workstreams") {
    const wsList = state.manager.modes?.workstreams?.workstreams || [];
    if (wsList.length) {
      const wsCtx = wsList.slice(0, 10)
        .map(w => `• ${w.name} (${w.file_count} files): ${w.summary}`)
        .join("\n");
      enrichedQ = `My file collection:\n${wsCtx}\n\nQuestion: ${q}`;
    }
  }
  return postJson("/api/chat", { run: state.run, id: node?.id,
    path: node?.path, q: enrichedQ, kind,
    history: compactIrisHistory(state.irisHistory),
    tool_mode: kind === "tasks" || kind === "rename" });
}

function addMsg(txt, who, related = []) {
  const div = document.createElement("div");
  div.className = `msg ${who}`;
  if (who === "assistant" && window.marked && txt.length > 2) {
    const contentEl = document.createElement("div");
    contentEl.className = "iris-content";
    contentEl.innerHTML = mdHtml(txt);
    div.appendChild(contentEl);
  } else {
    div.textContent = txt;
  }
  if (related.length) {
    const chips = document.createElement("div");
    chips.className = "msg-related";
    chips.innerHTML = related.slice(0, 4).map(r =>
      `<span class="msg-related-item" title="${esc(r.path)}" data-id="${esc(r.id)}">${esc(base(r.path).slice(0, 26))}</span>`
    ).join("");
    chips.addEventListener("click", ev => {
      const item = ev.target.closest("[data-id]");
      if (!item) return;
      const n = state.nodeById.get(item.dataset.id);
      if (!n) return;
      state.selected = n;
      if (state.manager?.name !== "workstreams" && state.manager?.mode?.draw) {
        state.manager.mode.draw();
      }
      renderPanel();
    });
    div.appendChild(chips);
  }
  el.messages.appendChild(div);
  el.messages.scrollTop = el.messages.scrollHeight;
  return div;
}

function kindFrom(q) {
  if (/rename|name/i.test(q)) return "rename";
  if (/similar|near/i.test(q)) return "similar";
  return "question";
}

function tooltip(ev, n) {
  if (!n) return hideTip();
  el.tip.hidden = false;
  // Keep tooltip inside viewport
  const tx = Math.min(ev.clientX + 14, window.innerWidth - 280);
  const ty = Math.min(ev.clientY + 14, window.innerHeight - 80);
  el.tip.style.left = `${tx}px`;
  el.tip.style.top = `${ty}px`;
  // Find workstream this node belongs to
  const ws = state.manager?.modes?.workstreams?.workstreams?.find(w => w.id === n.cluster);
  const wsLine = ws ? `<span style="color:var(--muted)">${esc(ws.name)}</span><br>` : "";
  el.tip.innerHTML = `<b>${esc(n.label)}</b><br>${wsLine}${humanSize(n.size)} · ${esc(relTime(n.mtime))}`;
}

function hideTip() {
  el.tip.hidden = true;
}

function countCat(cat) {
  return state.nodes.filter(n => n.category === cat).length;
}

function modifiedToday() {
  const day = 86400;
  const now = Date.now() / 1000;
  return state.nodes.filter(n => now - n.mtime < day).length;
}

function uniqueClusters() {
  return new Set(state.nodes.map(n => n.cluster)).size;
}

function largestByMonth(nodes = state.nodes) {
  const seen = new Map();
  for (const n of nodes) {
    const k = monthKey(n.mtime);
    if (!seen.has(k) || seen.get(k).size < n.size) seen.set(k, n);
  }
  return [...seen.values()].sort((a, b) => b.size - a.size);
}

function monthBins() {
  return monthBinsFor(state.nodes);
}

function monthBinsFor(nodes, minT = null, maxT = null) {
  if (!nodes?.length) return [];
  const lo = Number.isFinite(minT) ? minT : Math.min(...nodes.map(n => n.mtime || 0));
  const hi = Number.isFinite(maxT) ? maxT : Math.max(...nodes.map(n => n.mtime || 0));
  const by = new Map();
  for (const n of nodes) by.set(monthKey(n.mtime), (by.get(monthKey(n.mtime)) || 0) + 1);
  const out = [];
  const dt = new Date(lo * 1000);
  const end = new Date(hi * 1000);
  dt.setDate(1); dt.setHours(0, 0, 0, 0);
  end.setDate(1); end.setHours(0, 0, 0, 0);
  while (dt <= end) {
    const k = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}`;
    out.push({ month: k, count: by.get(k) || 0 });
    dt.setMonth(dt.getMonth() + 1);
  }
  return out;
}

function monthKey(ts) {
  const d = new Date((ts || 0) * 1000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function universePoint(n) {
  // Use actual PCA3D coordinates - these are semantically meaningful
  return { x: n.pcaX * 1.8, y: n.pcaY * 1.8, z: n.pcaZ * 1.8 };
}

function bright(n) {
  const col = new THREE.Color(palette[n.category]);
  const age = Date.now() / 1000 - n.mtime;
  return age < 604800 ? col.multiplyScalar(1.6) : col;
}

function labelSprite(txt, pos) {
  const cnv = document.createElement("canvas");
  cnv.width = 256;
  cnv.height = 64;
  const ctx = cnv.getContext("2d");
  ctx.fillStyle = "rgba(255,255,255,0.6)";
  ctx.font = "bold 24px system-ui";
  ctx.fillText(txt, 8, 40);
  const tex = new THREE.CanvasTexture(cnv);
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true });
  const sp = new THREE.Sprite(mat);
  const p = pos || center(txt); // use computed centroid if provided
  sp.position.set(p.x, p.y, p.z || 0);
  sp.scale.set(110, 28, 1);
  return sp;
}

function line(ctx, ax, ay, bx, by) {
  ctx.beginPath();
  ctx.moveTo(ax, ay);
  ctx.lineTo(bx, by);
  ctx.stroke();
}

function glow(ctx, p, n) {
  ctx.shadowColor = palette[n.category];
  ctx.shadowBlur = clamp(n.glow || 0, 0, 16);
  n.glow *= 0.74;
}

function hitBox(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h &&
    a.y + a.h > b.y;
}

function hitBoxPad(a, b, pad = 0) {
  return a.x - pad < b.x + b.w + pad && a.x + a.w + pad > b.x - pad &&
    a.y - pad < b.y + b.h + pad && a.y + a.h + pad > b.y - pad;
}

// ─── Local analytics (instant, DB-powered, no LLM) ───────────────────────────

async function analyzeLocal(kind) {
  try {
    const data = await getJson(`/api/analyze?kind=${kind}`);
    if (kind === "largest")      renderLargest(data);
    if (kind === "old_downloads") renderOldDownloads(data);
    if (kind === "duplicates")   renderDuplicates(data);
  } catch (err) {
    el.inspector.innerHTML = `<p class="muted">
      Analysis failed: ${esc(apiMsg(err))}
    </p>`;
  }
}

function renderLargest(data) {
  const items = data.items || [];
  const total = items.reduce((s, r) => s + (r.size || 0), 0);
  const rows = items.map(r => {
    const name = base(r.path);
    const nid = state.nodeById.has(r.id) ? r.id : null;
    const clickable = nid ? `data-nid="${esc(nid)}" style="cursor:pointer"` : "";
    const hint = nid ? "" : ` style="color:var(--subtle)"`;
    return `<div class="stat-row ana-row" ${clickable}>
      <span${hint} title="${esc(r.path)}">${esc(name.slice(0, 32))}</span>
      <b>${humanSize(r.size)}</b></div>`;
  }).join("");
  el.inspector.innerHTML = `
    <h2 class="panel-title">Largest files</h2>
    <p class="muted" style="margin-bottom:10px">
      Top ${items.length} of ${(data.items||[]).length} · ${humanSize(total)} total
    </p>
    <div class="stat-grid">${rows}</div>
    <p class="muted" style="margin-top:8px">Click a row to select it in the map.</p>`;
  bindAnalyzeRows();
}

function renderOldDownloads(data) {
  const items = data.items || [];
  if (!items.length) {
    el.inspector.innerHTML = `<h2 class="panel-title">Nothing stale</h2>
      <p class="muted">No large files older than 30 days in Downloads. 🎉</p>`;
    return;
  }
  const total = items.reduce((s, r) => s + (r.size || 0), 0);
  const rows = items.map(r => {
    const name = base(r.path);
    const age = Math.round((Date.now()/1000 - r.mtime) / 86400);
    const nid = state.nodeById.has(r.id) ? r.id : null;
    const clickable = nid ? `data-nid="${esc(nid)}" style="cursor:pointer"` : "";
    return `<div class="stat-row ana-row" ${clickable}>
      <span title="${esc(r.path)}">${esc(name.slice(0,28))}</span>
      <b style="color:var(--muted);font-size:11px">${age}d · ${humanSize(r.size)}</b></div>`;
  }).join("");
  el.inspector.innerHTML = `
    <h2 class="panel-title">Stale downloads</h2>
    <p class="muted" style="margin-bottom:10px">
      ${items.length} files · ${humanSize(total)} · older than 30 days
    </p>
    <div class="stat-grid">${rows}</div>
    <p class="muted" style="margin-top:8px">Double-click a node in Map to open in Finder.</p>`;
  bindAnalyzeRows();
}

function renderDuplicates(data) {
  const groups = data.groups || [];
  if (!groups.length) {
    el.inspector.innerHTML = `<h2 class="panel-title">No duplicates</h2>
      <p class="muted">No files with identical names found. ✓</p>`;
    return;
  }
  const totalWaste = groups.reduce((s, g) => s + (g.total_size||0) - Math.min(...(g.items||[]).map(i=>i.size||0)), 0);
  const rows = groups.slice(0, 14).map(g => {
    const nid = (g.items||[]).map(i=>i.id).find(id => state.nodeById.has(id));
    const clickable = nid ? `data-nid="${esc(nid)}" style="cursor:pointer"` : "";
    return `<div class="stat-row ana-row" ${clickable}>
      <span title="${g.items.map(i=>i.path).join('\n')}">${esc(g.name.slice(0,28))}</span>
      <b>${g.count}× · ${humanSize(g.total_size)}</b></div>`;
  }).join("");
  el.inspector.innerHTML = `
    <h2 class="panel-title">Duplicate filenames</h2>
    <p class="muted" style="margin-bottom:10px">
      ${groups.length} filename groups · ~${humanSize(totalWaste)} potentially reclaimable
    </p>
    <div class="stat-grid">${rows}</div>`;
  bindAnalyzeRows();
}

function bindAnalyzeRows() {
  el.inspector.querySelectorAll(".ana-row[data-nid]").forEach(row => {
    row.addEventListener("click", () => {
      const n = state.nodeById.get(row.dataset.nid);
      if (!n) return;
      state.selected = n;
      state.highlightCluster = null;
      // From Home view, jump to Map and center on the file
      if (state.manager?.name === "workstreams" || state.manager?.name === "onboard") {
        state.manager.switch("topology");
        const mode = state.manager.mode;
        if (mode?.cam) {
          const x = Number.isFinite(n.x) ? n.x : (n.pcaX || 0);
          const y = Number.isFinite(n.y) ? n.y : (n.pcaY || 0);
          mode.cam.x = -x;
          mode.cam.y = -y;
          mode.cam.k = clamp(2.5, 0.12, 8);
          mode.draw?.();
        }
      } else {
        state.manager?.mode?.draw?.();
      }
      renderPanel();
    });
  });
}

function drawCounts(n, e) {
  if (!el.counts) return;
  let clusterNote = "";
  if (state.highlightCluster) {
    const cid = String(state.highlightCluster || "");
    const clusterN = state.nodes.filter(nd => String(nd.cluster || "") === cid)
      .length;
    clusterNote = ` · ${clusterN} in cluster`;
  }
  el.counts.textContent = e > 0
    ? `${n.toLocaleString()} files · ${e} edges${clusterNote}`
    : `${n.toLocaleString()} files${clusterNote}`;
}

function humanSize(v) {
  if (!v) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let n = v;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) [n, i] = [n / 1024, i + 1];
  return `${n.toFixed(n >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

function hexToRgba(hex, alpha = 1) {
  const h = String(hex || "").replace("#", "");
  if (h.length !== 6) return `rgba(0,0,0,${alpha})`;
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

function relTime(ts) {
  if (!ts) return "unknown";
  const s = Date.now() / 1000 - ts;
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} hours ago`;
  if (s < 2592000) return `${Math.round(s / 86400)} days ago`;
  return new Date(ts * 1000).toLocaleDateString();
}

function map(v, a, b, x, y) {
  return x + (y - x) * ((v - a) / Math.max(1e-9, b - a));
}

function toggleTimelineHud(show) {
  const hud = ensureTimelineHud();
  hud.hidden = !show;
  if (show) updateTimelineHud();
}

function ensureTimelineHud() {
  if (ui.tl) return ui.tl;
  const hud = document.createElement("section");
  hud.className = "timeline-hud";
  hud.hidden = true;
  hud.innerHTML = `
    <div class="timeline-hud-row">
      <span id="tlRange" class="timeline-hud-val">Range: all time</span>
      <span id="tlShown" class="timeline-hud-meta">0 / 0 files</span>
    </div>
    <div class="timeline-hud-row timeline-hud-act">
      <button data-range="90d">90d</button>
      <button data-range="1y">1y</button>
      <button data-range="all" class="active">All</button>
    </div>`;
  hud.addEventListener("click", ev => {
    const btn = ev.target.closest("button[data-range]");
    if (!btn) return;
    state.manager?.mode?.setRangePreset?.(btn.dataset.range);
  });
  el.viewport.appendChild(hud);
  ui.tl = hud;
  return hud;
}

function updateTimelineHud(meta = {}) {
  const hud = ensureTimelineHud();
  const range = hud.querySelector("#tlRange");
  const shown = hud.querySelector("#tlShown");
  const minT = meta.minT || 0;
  const maxT = meta.maxT || 0;
  const flt = meta.tFilter;
  const a = flt ? flt[0] : minT;
  const b = flt ? flt[1] : maxT;
  range.textContent = (a && b) ? `Range: ${fmtDate(a)} → ${fmtDate(b)}` :
    "Range: all time";
  shown.textContent = `${(meta.shown || 0).toLocaleString()} / ${
    (meta.total || 0).toLocaleString()} files`;
  hud.querySelectorAll("button[data-range]").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.range === meta.preset);
  });
}

function fmtDate(ts) {
  return new Date(ts * 1000).toLocaleDateString(undefined, {
    month: "short", day: "numeric", year: "numeric",
  });
}

function clamp(v, a, b) {
  return Math.max(a, Math.min(b, v));
}

function hash(id) {
  let h = 2166136261;
  for (const ch of String(id)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return (h >>> 0) / 4294967295 * Math.PI * 2;
}

function num(v) {
  return Number.isFinite(Number(v)) ? Number(v) : 0;
}

function compactIrisHistory(rows, maxMsgs = 12, maxChars = 12000) {
  if (!Array.isArray(rows)) return [];
  const out = [];
  let used = 0;
  for (let i = rows.length - 1; i >= 0; i -= 1) {
    const row = rows[i];
    if (!row || typeof row !== "object") continue;
    const role = String(row.role || "").toLowerCase();
    if (role !== "user" && role !== "assistant") continue;
    const content = String(row.content || "").trim().slice(0, 1800);
    if (!content) continue;
    if (used + content.length > maxChars) continue;
    out.push({ role, content });
    used += content.length;
    if (out.length >= maxMsgs) break;
  }
  out.reverse();
  return out;
}

function mdHtml(txt) {
  if (!window.marked) return esc(txt);
  return sanitizeHtml(window.marked.parse(String(txt || "")));
}

function sanitizeHtml(raw) {
  const tpl = document.createElement("template");
  tpl.innerHTML = String(raw || "");
  const bad = "script,style,iframe,object,embed,link,meta,base";
  tpl.content.querySelectorAll(bad).forEach(el => el.remove());
  tpl.content.querySelectorAll("*").forEach(el => {
    for (const attr of [...el.attributes]) {
      const key = attr.name.toLowerCase();
      const val = String(attr.value || "").trim().toLowerCase();
      if (key.startsWith("on")) el.removeAttribute(attr.name);
      if ((key === "href" || key === "src") && val.startsWith("javascript:")) {
        el.removeAttribute(attr.name);
      }
    }
  });
  return tpl.innerHTML;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function apiCode(err) {
  if (!err || typeof err !== "object") return "";
  return String(err.apiCode || "");
}

function apiMsg(err) {
  if (!err) return "unknown error";
  if (typeof err === "string") return err;
  return String(err.apiMsg || err.message || "unknown error");
}

function assistantErr(err) {
  const code = apiCode(err);
  if (code === "unknown_node") {
    return "I lost file context. Select a file in the map and ask again.";
  }
  if (code === "scan_already_running") {
    return "A scan is already running. I can keep helping while it runs.";
  }
  return `Iris request failed: ${apiMsg(err)}`;
}

function mkApiErr(msg, code = "", status = 0) {
  const err = new Error(msg);
  err.apiMsg = msg;
  err.apiCode = code;
  err.status = status;
  return err;
}

function isApiFail(body) {
  return !!(body && typeof body === "object" && body.ok === false);
}

async function readJson(res) {
  const txt = await res.text();
  if (!txt) return {};
  try {
    return JSON.parse(txt);
  } catch (_) {
    return { err: txt };
  }
}

function failText(url, status, body) {
  const code = body?.err || body?.error || "";
  const msg = body?.message || code || `status ${status}`;
  return mkApiErr(`${url}: ${msg}`, code, status);
}

function failApi(body) {
  const code = String(body?.err || "request_failed");
  const msg = body?.message || body?.detail || code.replace(/_/g, " ");
  return mkApiErr(msg, code);
}

async function getJson(url) {
  const res = await fetch(url);
  const body = await readJson(res);
  if (!res.ok) throw failText(url, res.status, body);
  if (isApiFail(body)) throw failApi(body);
  return body;
}

async function postJson(url, data) {
  const res = await fetch(url, { method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(data) });
  const body = await readJson(res);
  if (!res.ok) throw failText(url, res.status, body);
  if (isApiFail(body)) throw failApi(body);
  return body;
}

/* ─── Settings panel ─────────────────────────────────────────────────────── */
(function initSettings() {
  const overlay = document.querySelector("#settingsOverlay");
  const closeBtn = document.querySelector("#settingsClose");
  const signBtn = document.querySelector("#settingsSignBtn");
  const providers = document.querySelector("#settingsProviders");
  const fileCount = document.querySelector("#settingsFileCount");
  const totalSize = document.querySelector("#settingsTotalSize");
  const form = document.querySelector("#providerForm");
  const formTitle = document.querySelector("#providerTitle");
  const formName = document.querySelector("#providerName");
  const formEmail = document.querySelector("#providerEmailInput");
  const formSubmit = document.querySelector("#providerSubmit");
  const formErr = document.querySelector("#providerErr");
  const exportKind = document.querySelector("#settingsExportKind");
  const exportBtn = document.querySelector("#settingsExportBtn");
  const exportMsg = document.querySelector("#settingsExportMsg");
  const digestEnabled = document.querySelector("#settingsDigestEnabled");
  const digestCron = document.querySelector("#settingsDigestCron");
  const digestTz = document.querySelector("#settingsDigestTz");
  const digestSaveBtn = document.querySelector("#settingsDigestSave");
  const digestQueueBtn = document.querySelector("#settingsDigestQueueNow");
  const digestStatus = document.querySelector("#settingsDigestStatus");
  const digestMsg = document.querySelector("#settingsDigestMsg");
  const llmProviderMode = document.querySelector("#settingsLlmProviderMode");
  const llmChatModel = document.querySelector("#settingsChatModel");
  const llmInferModel = document.querySelector("#settingsInferModel");
  const llmIrisModel = document.querySelector("#settingsIrisModel");
  const llmHomeModel = document.querySelector("#settingsHomeModel");
  const llmWsModel = document.querySelector("#settingsWorkstreamsModel");
  const llmSaveBtn = document.querySelector("#settingsLlmSave");
  const llmMsg = document.querySelector("#settingsLlmMsg");
  const channelRows = document.querySelector("#settingsChannelRows");
  const catalogMsg = document.querySelector("#settingsCatalogMsg");
  const modelValue = document.querySelector("#settingsModelValue");
  const topAvatar = el.topbarAvatarBtn;
  const panelAvatar = document.querySelector("#settingsAvatar");
  const panelName = document.querySelector("#settingsName");
  const panelEmail = document.querySelector("#settingsEmail");
  const panelSvg = `<svg viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="1.5" width="22" height="22">
    <circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
    </svg>`;
  let expanded = false;
  let activeProvider = "email";
  let busy = false;
  let exporting = false;

  window.__opticSyncAccount = syncAccount;
  window.__opticOpenSettings = openSettings;
  void syncAccount();

  function openSettings() {
    overlay.hidden = false;
    populateVaultStats();
    void syncAccount();
    void syncRuntimeModel();
    void syncAutomation();
    void syncLlmRuntime();
    void syncCatalog();
  }

  function closeSettings() {
    overlay.hidden = true;
    collapseProviders();
  }

  topAvatar?.addEventListener("click", openSettings);
  closeBtn?.addEventListener("click", closeSettings);
  overlay?.addEventListener("click", ev => {
    if (ev.target === overlay) closeSettings();
  });
  document.addEventListener("keydown", ev => {
    if (ev.key === "Escape" && !overlay.hidden) closeSettings();
  });

  signBtn?.addEventListener("click", () => {
    if (busy) return;
    if (state.account?.signed_in) {
      void signOut();
      return;
    }
    if (expanded) {
      collapseProviders();
      return;
    }
    expandProviders("email");
  });

  document.querySelector("#providerGoogle")?.addEventListener("click", () => {
    expandProviders("google");
  });
  document.querySelector("#providerApple")?.addEventListener("click", () => {
    expandProviders("apple");
  });
  document.querySelector("#providerEmail")?.addEventListener("click", () => {
    expandProviders("email");
  });
  form?.addEventListener("submit", ev => {
    ev.preventDefault();
    void submitSignup();
  });
  exportBtn?.addEventListener("click", () => {
    void runExport();
  });
  digestSaveBtn?.addEventListener("click", () => {
    void saveDigestAutomation();
  });
  digestQueueBtn?.addEventListener("click", () => {
    void queueDigestNow();
  });
  llmSaveBtn?.addEventListener("click", () => {
    void saveLlmRuntime();
  });

  async function syncAccount() {
    try {
      const data = await getJson("/api/account");
      applyAccount(data);
    } catch (_) {
      applyAccount({ signed_in: false, account: null });
    }
  }

  function applyAccount(data) {
    const obj = data && typeof data === "object" ? data : {};
    state.account = {
      signed_in: !!obj.signed_in,
      account: obj.account && typeof obj.account === "object" ?
        obj.account : null,
    };
    const acc = state.account.account;
    if (!state.account.signed_in || !acc) {
      setText(panelName, "Not signed in");
      setText(panelEmail, "Sync your vault across devices");
      setAvatar(panelAvatar, panelSvg, "");
      setTopAvatar("A", "Open account settings");
      signBtn.textContent = expanded ? "Cancel" : "Sign in";
      signBtn.classList.remove("signed-in");
      syncTopbarPresence();
      return;
    }
    const name = String(acc.name || "Local User");
    const email = String(acc.email || "");
    const initials = String(acc.initials || mkInitials(name, email));
    setText(panelName, name);
    setText(panelEmail, email || "Local account");
    setAvatar(panelAvatar, "", initials);
    setTopAvatar(initials, `Open account settings for ${name}`);
    signBtn.textContent = "Sign out";
    signBtn.classList.add("signed-in");
    collapseProviders();
    syncTopbarPresence();
  }

  function setText(node, txt) {
    if (node) node.textContent = txt;
  }

  function setAvatar(node, icon, txt) {
    if (!node) return;
    if (!txt) {
      node.classList.remove("signed-in");
      node.innerHTML = icon;
      return;
    }
    node.classList.add("signed-in");
    node.textContent = txt.slice(0, 2).toUpperCase();
  }

  function setTopAvatar(txt, label) {
    if (!topAvatar) return;
    const val = String(txt || "A").slice(0, 2).toUpperCase();
    const span = topAvatar.querySelector(".topbar-avatar-initial");
    if (span) span.textContent = val;
    else topAvatar.textContent = val;
    if (!label) return;
    topAvatar.title = label;
    topAvatar.setAttribute("aria-label", label);
  }

  function mkInitials(name, email) {
    const raw = String(name || email || "U");
    const parts = raw.split(/[^A-Za-z0-9]+/).filter(Boolean);
    if (!parts.length) return "U";
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  function expandProviders(provider) {
    if (state.account?.signed_in) return;
    expanded = true;
    activeProvider = provider;
    providers.hidden = false;
    form.hidden = false;
    formTitle.textContent = providerTitle(provider);
    formSubmit.textContent = "Create local account";
    signBtn.textContent = "Cancel";
    signBtn.classList.remove("signed-in");
    hideErr();
    if (!formName.value.trim()) formName.focus();
  }

  function providerTitle(provider) {
    if (provider === "google") return "Google sign-in";
    if (provider === "apple") return "Apple sign-in";
    return "Email sign-in";
  }

  function collapseProviders() {
    expanded = false;
    providers.hidden = true;
    form.hidden = true;
    hideErr();
    if (!state.account?.signed_in) {
      signBtn.textContent = "Sign in";
      signBtn.classList.remove("signed-in");
    }
  }

  async function submitSignup() {
    if (busy) return;
    const email = String(formEmail.value || "").trim();
    const name = String(formName.value || "").trim();
    if (!email) {
      return showErr("Email is required.");
    }
    busy = true;
    formSubmit.disabled = true;
    hideErr();
    try {
      const out = await postJson("/api/signup", {
        name,
        email,
        provider: activeProvider,
      });
      applyAccount(out);
    } catch (err) {
      showErr(apiMsg(err));
    } finally {
      busy = false;
      formSubmit.disabled = false;
    }
  }

  async function signOut() {
    busy = true;
    try {
      const out = await postJson("/api/signout", {});
      formName.value = "";
      formEmail.value = "";
      applyAccount(out);
    } catch (err) {
      showErr(apiMsg(err));
    } finally {
      busy = false;
    }
  }

  function showErr(msg) {
    if (!formErr) return;
    formErr.hidden = false;
    formErr.textContent = String(msg || "Unknown error");
  }

  function hideErr() {
    if (!formErr) return;
    formErr.hidden = true;
    formErr.textContent = "";
  }

  function populateVaultStats() {
    const count = state.nodes?.length ?? 0;
    if (fileCount) {
      fileCount.textContent = count ? `${count.toLocaleString()} files` : "—";
    }
    const totalBytes = state.nodes?.reduce((s, n) => s + (n.size || 0), 0) ?? 0;
    if (totalSize) {
      totalSize.textContent = totalBytes ? humanSize(totalBytes) : "—";
    }
  }

  function modelFromSettings() {
    const ints = state.settings?.integrations || {};
    const model = String(ints.chat_model || ints.infer_model || "").trim();
    const mode = String(ints.provider_mode || "ollama").trim();
    if (!model) return "Runtime model · local";
    return `${model} · ${mode}`;
  }

  async function syncRuntimeModel() {
    if (modelValue) modelValue.textContent = modelFromSettings();
    try {
      const data = await getJson("/api/health");
      const model = String(data?.model || "").trim();
      if (!model) return;
      const ints = state.settings?.integrations || {};
      const mode = String(ints.provider_mode || "ollama").trim();
      if (modelValue) modelValue.textContent = `${model} · ${mode}`;
    } catch (_) {
      return;
    }
  }

  async function syncAutomation() {
    try {
      const cur = await getJson("/api/integrations/state");
      const ints = cur?.integrations || {};
      const dig = ints?.automation?.digest || {};
      if (digestEnabled) digestEnabled.checked = !!dig.enabled;
      if (digestCron) digestCron.value = String(dig.cron || "0 9 * * *");
      if (digestTz) digestTz.value = String(dig.timezone || "UTC");
      const jobs = await getJson("/api/integrations/jobs");
      paintDigestStatus(jobs?.scheduler || null);
      setDigestMsg("Ready.", false);
    } catch (err) {
      setDigestMsg(`Automation unavailable: ${apiMsg(err)}`, true);
    }
  }

  async function syncCatalog() {
    if (!channelRows) return;
    try {
      const data = await getJson("/api/integrations/catalog");
      paintCatalog(data);
      setCatalogMsg("Live config + queue readiness loaded.", false);
    } catch (err) {
      channelRows.innerHTML = "<div class=\"settings-channel-sub\">" +
        "Catalog unavailable.</div>";
      setCatalogMsg(`Catalog unavailable: ${apiMsg(err)}`, true);
    }
  }

  function paintCatalog(data) {
    if (!channelRows) return;
    const channels = data?.channels || {};
    const email = catalogRow("Email", channels.email || {});
    const social = catalogRow("Social", channels.social || {});
    const hooks = catalogRow("Webhooks", channels.webhooks || {});
    const cal = catalogRow("Calendar", channels.calendar || {});
    const crm = catalogRow("CRM", channels.crm || {});
    const store = catalogRow("Storage", channels.storage || {});
    const ops = catalogRow("ChatOps", channels.chatops || {});
    channelRows.innerHTML = [email, social, hooks, cal, crm, store, ops].join("");
  }

  function catalogRow(name, row) {
    const enabled = !!row.enabled;
    const ready = !!row.ready;
    const badgeCls = ready ? "on" : "off";
    const badgeTxt = ready ? "Ready" : (enabled ? "Needs setup" : "Disabled");
    const sub = catalogSub(name, row);
    return `<div class="settings-channel-row">
      <div>
        <div class="settings-channel-name">${esc(name)}</div>
        <div class="settings-channel-sub">${esc(sub)}</div>
      </div>
      <span class="settings-channel-badge ${badgeCls}">${esc(badgeTxt)}</span>
    </div>`;
  }

  function catalogSub(name, row) {
    if (name === "Email") {
      const provider = String(row.provider || "smtp").toUpperCase();
      const cap = Number(row.daily_cap || 0);
      return `Provider: ${provider} · Daily cap: ${cap || "—"}`;
    }
    if (name === "Social") {
      const ready = (row.ready_providers || []).map(x => String(x).toUpperCase());
      return ready.length ? `Ready: ${ready.join(", ")}` :
        "No provider token ready";
    }
    if (name === "Calendar" || name === "CRM" || name === "Storage" ||
      name === "ChatOps") {
      const prv = String(row.provider || "").toUpperCase() || "—";
      return `Provider: ${prv} · Token: ${row.token_present ? "present" : "missing"}`;
    }
    const cnt = Number(row.target_count || 0);
    return `${cnt} target${cnt === 1 ? "" : "s"}`;
  }

  function setCatalogMsg(msg, err) {
    if (!catalogMsg) return;
    catalogMsg.textContent = String(msg || "");
    catalogMsg.classList.toggle("err", !!err);
  }

  function paintDigestStatus(row) {
    if (!digestStatus) return;
    if (!row || typeof row !== "object") {
      digestStatus.textContent = "Scheduler: unknown";
      return;
    }
    const next = Number(row.next_run || 0);
    const last = Number(row.last_enqueue || 0);
    const nextTxt = next ? new Date(next * 1000).toLocaleString() : "disabled";
    const lastTxt = last ? new Date(last * 1000).toLocaleString() : "never";
    const err = String(row.last_error || "");
    digestStatus.textContent = err
      ? `Next: ${nextTxt} · Last enqueue: ${lastTxt} · ${err}`
      : `Next: ${nextTxt} · Last enqueue: ${lastTxt}`;
  }

  function setDigestMsg(msg, err) {
    if (!digestMsg) return;
    digestMsg.textContent = String(msg || "");
    digestMsg.classList.toggle("err", !!err);
  }

  async function saveDigestAutomation() {
    const enabled = !!digestEnabled?.checked;
    const cron = String(digestCron?.value || "0 9 * * *").trim() || "0 9 * * *";
    const timezone = String(digestTz?.value || "UTC").trim() || "UTC";
    try {
      await postJson("/api/integrations/state", {
        integrations: {
          automation: {
            digest: { enabled, cron, timezone },
          },
        },
      });
      await refreshSettings(true);
      await syncAutomation();
      setDigestMsg("Automation saved.", false);
    } catch (err) {
      setDigestMsg(`Save failed: ${apiMsg(err)}`, true);
    }
  }

  async function queueDigestNow() {
    try {
      await postJson("/api/integrations/jobs", {
        kind: "email",
        payload: {
          to: state.account?.account?.email || "team@local",
          subject: "Optic digest · manual run",
          body: "Manual digest run queued from settings.",
          meta: { source: "settings_manual_digest" },
        },
      });
      await syncAutomation();
      setDigestMsg("Digest job queued.", false);
    } catch (err) {
      setDigestMsg(`Queue failed: ${apiMsg(err)}`, true);
    }
  }

  function setLlmMsg(msg, err) {
    if (!llmMsg) return;
    llmMsg.textContent = String(msg || "");
    llmMsg.classList.toggle("err", !!err);
  }

  async function syncLlmRuntime() {
    try {
      const cur = await getJson("/api/integrations/state");
      const ints = cur?.integrations || {};
      if (llmProviderMode) {
        llmProviderMode.value = String(ints.provider_mode || "ollama");
      }
      if (llmChatModel) llmChatModel.value = String(ints.chat_model || "");
      if (llmInferModel) llmInferModel.value = String(ints.infer_model || "");
      if (llmIrisModel) llmIrisModel.value = String(ints.iris_model || "");
      if (llmHomeModel) llmHomeModel.value = String(ints.home_model || "");
      if (llmWsModel) {
        llmWsModel.value = String(ints.workstreams_model || "");
      }
      setLlmMsg("Ready.", false);
    } catch (err) {
      setLlmMsg(`Runtime unavailable: ${apiMsg(err)}`, true);
    }
  }

  async function saveLlmRuntime() {
    const provider_mode = String(llmProviderMode?.value || "ollama");
    const chat_model = String(llmChatModel?.value || "").trim();
    const infer_model = String(llmInferModel?.value || "").trim();
    const iris_model = String(llmIrisModel?.value || "").trim();
    const home_model = String(llmHomeModel?.value || "").trim();
    const workstreams_model = String(llmWsModel?.value || "").trim();
    try {
      await postJson("/api/integrations/state", {
        integrations: {
          provider_mode,
          chat_model,
          infer_model,
          iris_model,
          home_model,
          workstreams_model,
        },
      });
      await refreshSettings(true);
      await syncRuntimeModel();
      await syncLlmRuntime();
      setLlmMsg("Runtime saved.", false);
    } catch (err) {
      setLlmMsg(`Save failed: ${apiMsg(err)}`, true);
    }
  }

  async function runExport() {
    if (exporting || !exportBtn) return;
    const run = String(state.run || el.run?.value || "").trim();
    if (!run) return setExportMsg("No run selected.", true);
    exporting = true;
    exportBtn.disabled = true;
    setExportMsg("Preparing export…", false);
    try {
      const kind = String(exportKind?.value || "report");
      const data = await exportData(kind, run);
      dlJson(`optic-${kind}-${run}.json`, data);
      setExportMsg(`Exported optic-${kind}-${run}.json`, false);
    } catch (err) {
      setExportMsg(`Export failed: ${apiMsg(err)}`, true);
    } finally {
      exporting = false;
      exportBtn.disabled = false;
    }
  }

  async function exportData(kind, run) {
    if (kind === "graph") return getJson(`/api/graph?run=${enc(run)}`);
    if (kind === "workstreams") return getJson(`/api/workstreams?run=${enc(run)}`);
    if (kind === "bundle") {
      const [report, workstreams, graph] = await Promise.all([
        getJson(`/api/report?run=${enc(run)}`),
        getJson(`/api/workstreams?run=${enc(run)}`),
        getJson(`/api/graph?run=${enc(run)}`),
      ]);
      return { run, report, workstreams, graph };
    }
    return getJson(`/api/report?run=${enc(run)}`);
  }

  function setExportMsg(msg, err) {
    if (!exportMsg) return;
    exportMsg.textContent = String(msg || "");
    exportMsg.classList.toggle("err", !!err);
  }

  function dlJson(name, data) {
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 300);
  }

  function enc(txt) {
    return encodeURIComponent(String(txt || ""));
  }
})();
