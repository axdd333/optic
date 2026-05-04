import assert from "node:assert/strict";
import test from "node:test";

import { app } from "../server.mjs";
import { pickFile } from "../src/route.js";
import { initSrv, reduceSrv } from "../src/state.js";

test("route decisions are allow-listed", () => {
  assert.equal(pickFile("/"), "optic.html");
  assert.equal(pickFile("/investors"), "optic-investors.html");
  assert.equal(pickFile("/legal"), "legal.html");
  assert.equal(pickFile("/terms"), "legal-terms.html");
  assert.equal(pickFile("/privacy"), "legal-privacy.html");
  assert.equal(pickFile("/cookies"), "legal-cookies.html");
  assert.equal(pickFile("/app-privacy"), "legal-app-privacy.html");
  assert.equal(pickFile("/notice-at-collection"), "legal-notice.html");
  assert.equal(pickFile("/docs/legal/terms.md"), "docs/legal/terms.md");
  assert.equal(pickFile("/styles/optic.css"), "styles/optic.css");
  assert.equal(
    pickFile("/assets/vendor/three.module.js"),
    "assets/vendor/three.module.js",
  );
  assert.equal(pickFile("/docs/legal/../privacy.md"), "");
  assert.equal(pickFile("/qa/var/optic-public.png"), "");
  assert.equal(pickFile("/../server.mjs"), "");
});

test("server state transitions are immutable", () => {
  const req = reduceSrv(initSrv, { type: "req" });
  const event = reduceSrv(req, { type: "event" });
  const err = reduceSrv(event, { type: "error" });
  assert.deepEqual(initSrv, { errors: 0, events: 0, reqs: 0 });
  assert.deepEqual(err, { errors: 1, events: 1, reqs: 1 });
});

test("server serves pages, health, events, and 404s", async () => {
  const server = app({ logLevel: "silent" }).listen(0);
  const port = server.address().port;
  try {
    await assertPage(port);
    await assertLegal(port);
    await assertEvent(port);
    await assertMissing(port);
  } finally {
    await close(server);
  }
});

async function assertPage(port) {
  const res = await hit(port, "/");
  assert.equal(res.status, 200);
  const body = await res.text();
  assert.match(body, /The internet/);
  assert.match(body, /Example inference/);
}

async function assertLegal(port) {
  const res = await hit(port, "/legal");
  assert.equal(res.status, 200);
  assert.match(await res.text(), /Legal for the Optic website and app/);
  const terms = await hit(port, "/terms");
  assert.match(await terms.text(), /hello@tryoptic.app/);
}

async function assertEvent(port) {
  const res = await hit(port, "/api/event", {
    body: JSON.stringify({ name: "test" }),
    headers: { "content-type": "application/json" },
    method: "POST",
  });
  assert.equal(res.status, 202);
  const health = await hit(port, "/healthz");
  assert.match(await health.text(), /"events":1/);
}

async function assertMissing(port) {
  const res = await hit(port, "/qa/var/optic-public.png");
  assert.equal(res.status, 404);
}

function hit(port, path, opts) {
  return fetch(`http://127.0.0.1:${port}${path}`, opts);
}

function close(server) {
  return new Promise((resolve) => server.close(resolve));
}
