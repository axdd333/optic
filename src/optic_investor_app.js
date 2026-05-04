export const initInv = Object.freeze({
  motion: "normal",
  route: "thesis",
  status: "idle",
});

const reads = {
  boundary: ["trust moat", "subject-owned", "no buyer dossier"],
  network: ["calibration", "voluntary input", "user-owned value"],
  product: ["local audit", "private processing", "repair path"],
  thesis: ["feedback layer", "evidence trail", "mirror with receipts"],
  wedge: ["high-stakes moments", "urgent buyer", "assisted audit"],
  why: ["second self", "AI interpretation", "fragment overload"],
};

const glyphs = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/->";
const steps = ["source", "signal", "inference", "confidence", "repair"];
let state = initInv;

export function reduceInv(st = initInv, act = {}) {
  if (act.type === "motion") return motion(st, act);
  if (act.type === "route") return route(st, act);
  if (act.type === "status") return status(st, act);
  return st;
}

export function genRead(id) {
  const row = reads[id] || reads.thesis;
  return `Investor lens: ${row.join(", ")}.`;
}

export function scrambleText(text, tick) {
  return [...text].map((char, idx) => glyph(char, idx, tick)).join("");
}

export function clipText(text, sz = 132) {
  const val = String(text).replace(/\s+/g, " ").trim();
  return val.length > sz ? `${val.slice(0, sz - 1)}.` : val;
}

function init() {
  bind();
  initMotion();
  observe();
  syncRoute();
}

function bind() {
  document.addEventListener("click", onClick);
  window.addEventListener("hashchange", syncRoute);
}

function initMotion() {
  const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
  commit({ motion: mq.matches ? "reduced" : "normal", type: "motion" });
  mq.addEventListener?.("change", onMotion);
}

function observe() {
  if (isReduced() || !("IntersectionObserver" in window)) return settleAll();
  const obs = new IntersectionObserver(onReveal, { threshold: 0.24 });
  $$("[data-reveal], [data-panel]").forEach((node) => obs.observe(node));
}

function onMotion(evt) {
  commit({ motion: evt.matches ? "reduced" : "normal", type: "motion" });
  if (evt.matches) settleAll();
}

function onReveal(entries) {
  entries.filter((entry) => entry.isIntersecting).forEach(reveal);
}

function reveal(entry) {
  const node = entry.target;
  node.classList.add("is-visible");
  if (node.id && node.id !== "top") commit({ route: node.id, type: "route" });
  runEffects(node);
}

function runEffects(node) {
  typeAll(node);
  scrambleAll(node);
  cycleAll(node);
}

function typeAll(root) {
  $$("[data-type]", root).forEach(typeNode);
}

function scrambleAll(root) {
  $$("[data-scramble]", root).forEach(scrambleNode);
}

function cycleAll(root) {
  $$("[data-cycle]", root).forEach(cycleNode);
}

function typeNode(node) {
  if (node.dataset.done) return;
  const text = node.dataset.text || node.textContent;
  node.dataset.done = "true";
  if (isReduced()) return setText(node, text);
  typeWrite(node, text);
}

function typeWrite(node, text, idx = 0) {
  setText(node, text.slice(0, idx));
  if (idx >= text.length) return;
  setTimeout(() => typeWrite(node, text, idx + 1), 18);
}

function scrambleNode(node) {
  if (node.dataset.done) return;
  const text = clipText(node.textContent);
  node.dataset.done = "true";
  if (isReduced()) return setText(node, text);
  scrambleLoop(node, text, 0);
}

function scrambleLoop(node, text, tick) {
  setText(node, tick > 12 ? text : scrambleText(text, tick));
  if (tick > 12) return;
  setTimeout(() => scrambleLoop(node, text, tick + 1), 42);
}

function cycleNode(node) {
  if (node.dataset.running) return;
  node.dataset.running = "true";
  paintCycle(node, 0);
}

function paintCycle(node, idx) {
  [...node.children].forEach((child, pos) => {
    child.classList.toggle("is-hot", pos === idx % steps.length);
  });
  setTimeout(() => paintCycle(node, idx + 1), isReduced() ? 5000 : 900);
}

function onClick(evt) {
  const node = evt.target.closest("[data-investor-link]");
  if (!node) return;
  track("optic_investor_nav");
}

function syncRoute() {
  const id = clean(location.hash) || "thesis";
  const route = document.getElementById(id) ? id : "thesis";
  commit({ route, type: "route" });
}

function sync() {
  document.body.dataset.effect = state.status;
  document.body.dataset.section = state.route;
  document.documentElement.classList.toggle("motion-reduced", isReduced());
  syncLinks();
  syncLive();
}

function syncLinks() {
  $$("[data-investor-link]").forEach((node) => {
    node.setAttribute("aria-current", linkOn(node) ? "page" : "false");
  });
}

function syncLive() {
  const node = document.querySelector("[data-live]");
  if (node) node.textContent = genRead(state.route);
}

function settleAll() {
  $$("[data-reveal], [data-panel]").forEach(settleNode);
}

function settleNode(node) {
  node.classList.add("is-visible");
  runEffects(node);
}

function commit(act) {
  state = reduceInv(state, act);
  sync();
}

function motion(st, act) {
  const val = act.motion === "reduced" ? "reduced" : "normal";
  return { ...st, motion: val, status: val === "reduced" ? "reduced" : "idle" };
}

function route(st, act) {
  const val = st.motion === "reduced" ? "reduced" : "revealing";
  return { ...st, route: clean(act.route) || "thesis", status: val };
}

function status(st, act) {
  const val = ["idle", "revealing", "settled", "reduced"].includes(act.status);
  return { ...st, status: val ? act.status : st.status };
}

function glyph(char, idx, tick) {
  if (char === " ") return " ";
  if (tick > idx % 9 + 3) return char;
  return glyphs[(idx * 7 + tick * 5) % glyphs.length];
}

function linkOn(node) {
  return clean(node.hash) === state.route;
}

function setText(node, text) {
  node.textContent = text;
}

function isReduced() {
  return state.motion === "reduced";
}

function clean(hash) {
  return String(hash || "").replace(/^#/, "");
}

function track(name) {
  const body = JSON.stringify({ name, path: location.pathname });
  fetch("/api/event", { body, headers: jsonHead(), method: "POST" })
    .catch(() => {});
}

function jsonHead() {
  return { "content-type": "application/json" };
}

function $$(sel, root = document) {
  return [...root.querySelectorAll(sel)];
}

if (typeof document !== "undefined") init();
