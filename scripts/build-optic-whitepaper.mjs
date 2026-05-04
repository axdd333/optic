import { copyFile, mkdir, readdir, writeFile } from "node:fs/promises";
import {
  audiences,
  auditSteps,
  bodySections,
  hero,
  opticCfg,
  principles,
  profileParts,
  signals,
} from "../src/optic_content.js";

const docOut = new URL("../docs/optic-whitepaper.md", import.meta.url);
const pubDoc = new URL("../public/docs/optic-whitepaper.md", import.meta.url);

await mkdir(new URL("../docs/", import.meta.url), { recursive: true });
await mkdir(new URL("../public/docs/", import.meta.url), { recursive: true });
await mkdir(new URL("../public/docs/legal/", import.meta.url), {
  recursive: true,
});
await mkdir(new URL("../public/assets/optic/", import.meta.url), {
  recursive: true,
});
await mkdir(new URL("../assets/vendor/", import.meta.url), { recursive: true });
await mkdir(new URL("../public/assets/vendor/", import.meta.url), {
  recursive: true,
});
await mkdir(new URL("../public/src/", import.meta.url), { recursive: true });
await mkdir(new URL("../public/styles/", import.meta.url), { recursive: true });
await mkdir(new URL("../public/crawl/", import.meta.url), { recursive: true });

const body = doc();
await writeFile(docOut, body, "utf8");
await writeFile(pubDoc, body, "utf8");
await syncStatic();

function doc() {
  return [
    title(),
    heroText(),
    list("Signals", signals),
    table("Principles", principles),
    table("First audit", auditSteps),
    table("Profile output", profileParts),
    table("Starting wedge", audiences),
    ...bodySections.map(section),
  ].join("\n\n");
}

async function syncStatic() {
  await syncVendor();
  const jobs = copyRows().map(([src, dst]) => copyFile(url(src), url(dst)));
  await Promise.all(jobs);
  await syncDir("../assets/optic/", "../public/assets/optic/");
  await syncDir("../docs/legal/", "../public/docs/legal/");
}

async function syncVendor() {
  const src = "../node_modules/three/build/three.module.js";
  await copyFile(url(src), url("../assets/vendor/three.module.js"));
  await copyFile(url(src), url("../public/assets/vendor/three.module.js"));
}

function copyRows() {
  return [
    ["../optic.html", "../public/index.html"],
    ["../optic.html", "../public/optic.html"],
    ["../optic-investors.html", "../public/investors.html"],
    ["../optic-investors.html", "../public/optic-investors.html"],
    ["../legal.html", "../public/legal.html"],
    ["../legal-terms.html", "../public/terms.html"],
    ["../legal-terms.html", "../public/legal-terms.html"],
    ["../legal-privacy.html", "../public/privacy.html"],
    ["../legal-privacy.html", "../public/legal-privacy.html"],
    ["../legal-cookies.html", "../public/cookies.html"],
    ["../legal-cookies.html", "../public/legal-cookies.html"],
    ["../legal-app-privacy.html", "../public/app-privacy.html"],
    ["../legal-app-privacy.html", "../public/legal-app-privacy.html"],
    ["../legal-notice.html", "../public/notice-at-collection.html"],
    ["../legal-notice.html", "../public/legal-notice.html"],
    ["../src/optic_app.js", "../public/src/optic_app.js"],
    ["../src/optic_content.js", "../public/src/optic_content.js"],
    ["../src/optic_investor_app.js", "../public/src/optic_investor_app.js"],
    ["../src/optic_scene.js", "../public/src/optic_scene.js"],
    ["../styles/legal.css", "../public/styles/legal.css"],
    ["../styles/optic.css", "../public/styles/optic.css"],
    ["../styles/optic-cinematic.css", "../public/styles/optic-cinematic.css"],
    ["../favicon.svg", "../public/favicon.svg"],
    ["../favicon-32.png", "../public/favicon-32.png"],
    ["../apple-touch-icon.png", "../public/apple-touch-icon.png"],
    ["../site.webmanifest", "../public/site.webmanifest"],
    ["../robots.txt", "../public/robots.txt"],
    ["../sitemap.xml", "../public/sitemap.xml"],
    ["../crawl/optic-robots.txt", "../public/crawl/optic-robots.txt"],
    ["../crawl/optic-sitemap.xml", "../public/crawl/optic-sitemap.xml"],
  ];
}

function title() {
  return `# Optic: Private Identity Feedback\n\nVersion: ${opticCfg.version}`;
}

function heroText() {
  return `## Positioning\n\n${hero.lede}\n\n${hero.body}`;
}

function section(sec, idx) {
  return `## ${idx + 1}. ${sec.title}\n\n${sec.essay.map(clean).join("\n\n")}`;
}

function list(name, rows) {
  return `## ${name}\n\n${rows.map((row) => `- ${clean(row)}`).join("\n")}`;
}

function table(name, rows) {
  return [`## ${name}`, ...rows.map(rowText)].join("\n\n");
}

function rowText(row) {
  return `### ${clean(row.title)}\n\n${clean(row.body)}`;
}

function url(path) {
  return new URL(path, import.meta.url);
}

function clean(val) {
  return String(val).replace(/\s+/g, " ").trim();
}

async function syncDir(src, dst) {
  await mkdir(url(dst), { recursive: true });
  const rows = await readdir(url(src), { withFileTypes: true });
  await Promise.all(rows.map((row) => syncEntry(src, dst, row)));
}

async function syncEntry(src, dst, row) {
  const from = `${src}${row.name}`;
  const to = `${dst}${row.name}`;
  if (row.isDirectory()) return syncDir(`${from}/`, `${to}/`);
  if (row.isFile()) return copyFile(url(from), url(to));
}
