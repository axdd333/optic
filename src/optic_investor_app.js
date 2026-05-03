const notes = {
  boundary: "The moat is trust: subject-owned, local-first, and explicit.",
  network: "The expansion path is calibration with user-controlled data value.",
  product: "The first product is useful before the network exists.",
  thesis: "The company gives people a private way to inspect perception.",
  wedge: "Start where perception errors already cost money and opportunity.",
  why: "AI increases the value of interpreting identity fragments.",
};

function init() {
  window.addEventListener("hashchange", sync);
  document.addEventListener("click", trackClick);
  sync();
}

function sync() {
  const id = clean(location.hash) || "thesis";
  const active = document.getElementById(id) ? id : "thesis";
  document.body.dataset.section = active;
  show(active);
  note(active);
}

function show(id) {
  panels().forEach((node) => {
    node.classList.toggle("is-active", node.id === id);
  });
}

function note(id) {
  const node = document.querySelector("[data-note]");
  if (node) node.textContent = notes[id] || notes.thesis;
}

function trackClick(evt) {
  const node = evt.target.closest("[data-investor-link]");
  if (!node) return;
  track("optic_investor_nav");
}

function track(name) {
  const body = JSON.stringify({ name, path: location.pathname });
  fetch("/api/event", { body, headers: jsonHead(), method: "POST" })
    .catch(() => {});
}

function jsonHead() {
  return { "content-type": "application/json" };
}

function panels() {
  return [...document.querySelectorAll(".investor-panel")];
}

function clean(hash) {
  return hash.replace(/^#/, "");
}

init();
