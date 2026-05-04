import * as THREE from "/assets/vendor/three.module.js";

const scenes = Object.freeze({
  hero: { amp: 0.54, hue: 0.68, wave: 1.15 },
  privacy: { amp: 0.2, hue: 0.42, wave: 0.72 },
  process: { amp: 0.38, hue: 0.56, wave: 0.96 },
  report: { amp: 0.28, hue: 0.5, wave: 0.62 },
});

let active;

export function createScene(root, cfg = {}) {
  if (!root || !webglOk()) return noop();
  active = make(root, cfg);
  active.start();
  return active.api;
}

export function setScene(name) {
  active?.api.setScene(name);
}

export function setMotion(mode) {
  active?.api.setMotion(mode);
}

export function destroy() {
  active?.api.destroy();
  active = undefined;
}

function make(root, cfg) {
  const ctx = init(root, cfg);
  const api = makeApi(ctx);
  addField(ctx);
  addRing(ctx);
  bind(ctx);
  return { api, start: () => loop(ctx) };
}

function init(root, cfg) {
  const renderer = new THREE.WebGLRenderer({ alpha: true, canvas: root });
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  return { camera, cfg, mouse: new THREE.Vector2(), renderer, running: false,
    scene, state: "hero", stop: false, target: "hero", t: 0 };
}

function makeApi(ctx) {
  return {
    destroy: () => kill(ctx),
    setMotion: (mode) => motion(ctx, mode),
    setScene: (name) => sceneTo(ctx, name),
  };
}

function addField(ctx) {
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", posAttr(ctx.cfg.count || 1300));
  const mat = new THREE.PointsMaterial(opts(0.018, 0x9eb3a5, 0.72));
  ctx.field = new THREE.Points(geo, mat);
  ctx.scene.add(ctx.field);
}

function addRing(ctx) {
  const geo = new THREE.TorusGeometry(1.6, 0.002, 8, 180);
  const mat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true });
  mat.opacity = 0.18;
  ctx.ring = new THREE.Mesh(geo, mat);
  ctx.ring.position.z = -2;
  ctx.scene.add(ctx.ring);
}

function bind(ctx) {
  ctx.onResize = () => resize(ctx);
  ctx.onMove = (evt) => move(ctx, evt);
  ctx.onScroll = () => scroll(ctx);
  addEventListener("resize", ctx.onResize);
  addEventListener("pointermove", ctx.onMove);
  addEventListener("scroll", ctx.onScroll, { passive: true });
  resize(ctx);
}

function resize(ctx) {
  const w = innerWidth || 1;
  const h = innerHeight || 1;
  ctx.renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.75));
  ctx.renderer.setSize(w, h, false);
  ctx.camera.aspect = w / h;
  ctx.camera.position.z = 4;
  ctx.camera.updateProjectionMatrix();
}

function loop(ctx) {
  if (ctx.stop) {
    ctx.running = false;
    return;
  }
  ctx.running = true;
  requestAnimationFrame(() => loop(ctx));
  draw(ctx);
}

function draw(ctx) {
  const spec = scenes[ctx.state] || scenes.hero;
  ctx.t += 0.006;
  ctx.field.rotation.y = ctx.mouse.x * 0.09 + ctx.t * 0.04 * spec.wave;
  ctx.field.rotation.x = ctx.mouse.y * 0.06 + Math.sin(ctx.t) * 0.04;
  ctx.field.material.opacity = 0.38 + spec.amp * 0.3;
  ctx.ring.rotation.z += 0.0018 * spec.wave;
  ctx.ring.material.opacity = 0.08 + spec.amp * 0.14;
  ctx.renderer.render(ctx.scene, ctx.camera);
}

function sceneTo(ctx, name) {
  if (scenes[name]) ctx.state = name;
}

function motion(ctx, mode) {
  ctx.stop = mode === "reduced";
  if (ctx.stop) ctx.renderer.render(ctx.scene, ctx.camera);
  if (!ctx.stop && !ctx.running) loop(ctx);
}

function move(ctx, evt) {
  ctx.mouse.x = (evt.clientX / Math.max(innerWidth, 1) - 0.5) * 2;
  ctx.mouse.y = (evt.clientY / Math.max(innerHeight, 1) - 0.5) * -2;
}

function scroll(ctx) {
  const max = Math.max(document.body.scrollHeight - innerHeight, 1);
  ctx.scene.rotation.z = (scrollY / max - 0.5) * 0.16;
}

function kill(ctx) {
  ctx.stop = true;
  ctx.running = false;
  removeEventListener("resize", ctx.onResize);
  removeEventListener("pointermove", ctx.onMove);
  removeEventListener("scroll", ctx.onScroll);
  ctx.renderer.dispose();
}

function posAttr(count) {
  const arr = new Float32Array(count * 3);
  for (let i = 0; i < count; i += 1) fillPoint(arr, i);
  return new THREE.BufferAttribute(arr, 3);
}

function fillPoint(arr, idx) {
  const t = idx * 0.168;
  const r = 1.2 + (idx % 89) * 0.032;
  arr[idx * 3] = Math.cos(t) * r;
  arr[idx * 3 + 1] = Math.sin(t * 0.82) * r * 0.44;
  arr[idx * 3 + 2] = -1.8 - (idx % 47) * 0.026;
}

function opts(size, color, opacity) {
  return { blending: THREE.AdditiveBlending, color, depthWrite: false,
    opacity, size, transparent: true };
}

function webglOk() {
  return typeof WebGLRenderingContext !== "undefined";
}

function noop() {
  return { destroy() {}, setMotion() {}, setScene() {} };
}
