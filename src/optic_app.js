import { publicSections } from "./optic_content.js";

export const initState = Object.freeze({
  motion: "normal",
  route: "home",
  view: "public",
});

const reducers = {
  motion: reduceMotion,
  route: reduceRoute,
  view: reduceView,
};

let state = initState;
let scene;
let sceneMod;

export function opticReducer(st = initState, act = {}) {
  const fn = reducers[act.type];
  return fn ? fn(st, act) : st;
}

function reduceMotion(st, act) {
  const motion = act.motion === "reduced" ? "reduced" : "normal";
  return { ...st, motion };
}

function reduceRoute(st, act) {
  return { ...st, route: routeOf(act.route) };
}

function reduceView(st, act) {
  const view = act.view === "brief" ? "brief" : "public";
  return { ...st, view };
}

function init() {
  bind();
  initMotion();
  initScene();
  watchPanels();
  setRouteFromHash();
}

function initScene() {
  const root = document.querySelector(".optic-scene");
  import("./optic_scene.js")
    .then((mod) => startScene(mod, root))
    .catch(() => {});
}

function startScene(mod, root) {
  sceneMod = mod;
  scene = mod.createScene(root, { count: 1400 });
  scene.setMotion(state.motion);
}

function bind() {
  document.addEventListener("click", onClick);
  window.addEventListener("hashchange", setRouteFromHash);
}

function initMotion() {
  const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
  commit({ motion: mq.matches ? "reduced" : "normal", type: "motion" });
  mq.addEventListener?.("change", onMotion);
  stageMotion();
}

function onMotion(evt) {
  commit({ motion: evt.matches ? "reduced" : "normal", type: "motion" });
}

function stageMotion() {
  if (state.motion === "reduced") return settleMotion();
  if (!("IntersectionObserver" in window)) return settleMotion();
  const obs = new IntersectionObserver(onStage, { threshold: 0.16 });
  $$("[data-motion-stage]").forEach((node) => obs.observe(node));
}

function onStage(entries) {
  entries.forEach((entry) => {
    entry.target.classList.toggle("is-settled", entry.isIntersecting);
  });
}

function settleMotion() {
  $$("[data-motion-stage]").forEach((node) => {
    node.classList.add("is-settled");
  });
}

function watchPanels() {
  if (!("IntersectionObserver" in window)) return;
  const obs = new IntersectionObserver(onPanel, panelOpts());
  $$("[data-panel]").forEach((node) => obs.observe(node));
}

function panelOpts() {
  return { rootMargin: "-42% 0px -48% 0px", threshold: 0 };
}

function onPanel(entries) {
  const hit = entries.find((entry) => entry.isIntersecting);
  if (!hit?.target.id) return;
  sceneMod?.setScene(sceneName(hit.target));
  setState(hit.target.id);
}

function onClick(evt) {
  const node = evt.target.closest("[data-track], a[href]");
  if (!node) return;
  if (node.dataset.track) track(node.dataset.track);
  if (node.hash) return scrollToRoute(evt, node.hash.slice(1));
}

function scrollToRoute(evt, id) {
  const node = document.getElementById(id);
  if (!node) return;
  evt.preventDefault();
  setState(id);
  node.scrollIntoView({ behavior: motionScroll(), block: "start" });
  history.replaceState(null, "", `#${id}`);
}

function motionScroll() {
  return state.motion === "reduced" ? "auto" : "smooth";
}

function setRouteFromHash() {
  const id = location.hash.replace(/^#/, "") || "home";
  setRoute(id);
}

function setRoute(id) {
  setState(id);
  const node = document.getElementById(domRoute(id));
  if (node) sceneMod?.setScene(sceneName(node));
  node?.scrollIntoView({ block: "start" });
}

function setState(id) {
  const route = routeOf(id);
  const view = route === "brief" ? "brief" : "public";
  commit({ route, type: "route" });
  commit({ type: "view", view });
}

function commit(act) {
  state = opticReducer(state, act);
  sync();
}

function sync() {
  document.body.dataset.motion = state.motion;
  document.body.dataset.route = state.route;
  document.body.dataset.view = state.view;
  document.documentElement.classList.toggle("motion-reduced", isReduced());
  sceneMod?.setMotion(state.motion);
  updateActiveLinks();
}

function sceneName(node) {
  return node?.dataset.scene || "hero";
}

function updateActiveLinks() {
  $$("a[href^='#']").forEach(updateLink);
}

function updateLink(link) {
  const id = link.hash.slice(1);
  const on = routeOf(id) === state.route || topMatch(id);
  link.setAttribute("aria-current", on ? "page" : "false");
}

function topMatch(id) {
  return id === "top" && state.route === "home";
}

function track(name) {
  const body = JSON.stringify({ name, path: location.pathname });
  fetch("/api/event", { body, headers: jsonHead(), method: "POST" })
    .catch(() => {});
}

function jsonHead() {
  return { "content-type": "application/json" };
}

function routeOf(id) {
  const route = id === "top" ? "home" : String(id || "home");
  return validRoute(route) ? route : "home";
}

function domRoute(id) {
  const route = routeOf(id);
  return route === "home" ? "top" : route;
}

function validRoute(id) {
  const dyn = publicSections.map((item) => item.id);
  return ["home", "how", "audit", "uses", "privacy", "brief", ...dyn]
    .includes(id);
}

function isReduced() {
  return state.motion === "reduced";
}

function $$(sel, root = document) {
  return [...root.querySelectorAll(sel)];
}

if (typeof document !== "undefined") init();
