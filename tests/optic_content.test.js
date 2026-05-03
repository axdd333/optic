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
  const css = await readFile(file("../public/styles/optic.css"), "utf8");
  assert.match(html, /data-motion/);
  assert.match(js, /prefers-reduced-motion/);
  assert.match(css, /motion-reduced/);
});

function publicPaths() {
  return [
    "../public/optic.html",
    "../public/optic-investors.html",
    "../public/src/optic_app.js",
    "../public/src/optic_content.js",
    "../public/src/optic_investor_app.js",
    "../public/styles/optic.css",
    "../public/docs/optic-whitepaper.md",
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
