import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

import {
  appendices,
  auditSteps,
  audiences,
  bodySections,
  claims,
  hero,
  opticCfg,
  principles,
  profileParts,
  publicSections,
  sampleReport,
  sourceGaps,
  sources,
  validationAgenda,
  zinePlates,
} from "../src/optic_content.js";
import { initState, opticReducer } from "../src/optic_app.js";
import {
  clipText,
  genRead,
  initInv,
  reduceInv,
  scrambleText,
} from "../src/optic_investor_app.js";

const banned = [
  "credit score for identity",
  "definitive score",
  "master claim ledger",
  "moral compass",
  "source ledger",
];

test("optic content is the investor-readable feedback layer", () => {
  assert.equal(opticCfg.version, "v1.0");
  assert.match(opticCfg.title, /Private perception intelligence/);
  assert.match(hero.lede, /Private perception intelligence/);
  assert.match(opticCfg.description, /high-stakes professional contexts/);
  assert.equal(publicSections.length, 6);
});

test("optic public model keeps only the new content surface", () => {
  assert.equal(appendices.length, 0);
  assert.equal(claims.length, 0);
  assert.equal(sources.length, 0);
  assert.equal(zinePlates.length, 0);
  assert.equal(sampleReport.findings.length, 0);
  assert.equal(validationAgenda, sourceGaps);
});

test("optic narrative has full product coverage", () => {
  assert.equal(bodySections.length, 8);
  assert.equal(auditSteps.length, 6);
  assert.equal(audiences.length, 4);
  assert.equal(principles.length, 4);
  assert.equal(profileParts.length, 4);
  assert.deepEqual(publicSections.map((row) => row.id), expectedNav());
});

test("optic reducer keeps page and motion state bounded", () => {
  const product = opticReducer(initState, route("product"));
  assert.notEqual(product, initState);
  assert.equal(product.route, "product");
  assert.equal(opticReducer(product, route("missing")).route, "home");
  assert.equal(opticReducer(product, motion()).motion, "reduced");
});

test("optic content avoids old artifact language", async () => {
  const corpus = [
    JSON.stringify({ auditSteps, bodySections, hero, opticCfg }),
    await readFile(file("../docs/optic-whitepaper.md"), "utf8"),
  ].join("\n");
  for (const phrase of banned) assertNoPhrase(corpus, phrase);
});

test("generated optic public bundle is publishable", async () => {
  for (const path of publicPaths()) await access(file(path));
});

test("optic motion hooks and reduced motion ship publicly", async () => {
  const html = await readFile(file("../public/optic.html"), "utf8");
  const js = await readFile(file("../public/src/optic_app.js"), "utf8");
  const scene = await readFile(file("../public/src/optic_scene.js"), "utf8");
  const css = await readFile(file("../public/styles/optic.css"), "utf8");
  const cinema = await readFile(file("../public/styles/optic-cinematic.css"),
    "utf8");
  assert.match(html, /data-motion/);
  assert.match(html, /class="optic-scene"/);
  assert.match(html, /data-scene="hero"/);
  assert.match(html, /optic-cinematic\.css/);
  assert.match(js, /prefers-reduced-motion/);
  assert.match(scene, /createScene/);
  assert.match(scene, /setMotion/);
  assert.match(css, /motion-reduced/);
  assert.match(cinema, /73svh/);
  assert.match(cinema, /hero-system/);
  assert.match(cinema, /38\.2%/);
});

test("investor field guide generation is deterministic and bounded", () => {
  const red = reduceInv(initInv, { motion: "reduced", type: "motion" });
  assert.equal(red.motion, "reduced");
  assert.match(genRead("network"), /calibration/);
  assert.equal(genRead("missing"), genRead("thesis"));
  assert.equal(scrambleText("ABC", 2), scrambleText("ABC", 2));
  assert.equal(clipText("a ".repeat(90)).length <= 132, true);
});

function publicPaths() {
  return [
    "../public/index.html",
    "../public/optic.html",
    "../public/optic-investors.html",
    "../public/legal.html",
    "../public/legal-terms.html",
    "../public/legal-privacy.html",
    "../public/legal-cookies.html",
    "../public/legal-app-privacy.html",
    "../public/legal-notice.html",
    "../public/src/optic_app.js",
    "../public/src/optic_content.js",
    "../public/src/optic_investor_app.js",
    "../public/src/optic_scene.js",
    "../public/styles/optic.css",
    "../public/styles/optic-cinematic.css",
    "../public/assets/vendor/three.module.js",
    "../public/docs/optic-whitepaper.md",
    "../public/docs/legal/README.md",
    "../public/docs/legal/terms.md",
    "../public/docs/legal/privacy.md",
  ];
}

function expectedNav() {
  return ["why", "product", "wedge", "calibration", "trust", "brief"];
}

function assertNoPhrase(corpus, phrase) {
  const rx = new RegExp(`\\b${escapeRx(phrase)}\\b`, "i");
  assert.equal(rx.test(corpus), false, phrase);
}

function escapeRx(val) {
  return val.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function route(id) {
  return { route: id, type: "route" };
}

function motion() {
  return { motion: "reduced", type: "motion" };
}

function file(path) {
  return new URL(path, import.meta.url);
}
