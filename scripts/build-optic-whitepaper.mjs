import { copyFile, cp, mkdir, writeFile } from "node:fs/promises";
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
await mkdir(new URL("../public/assets/optic/", import.meta.url), {
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
  const jobs = copyRows().map(([src, dst]) => copyFile(url(src), url(dst)));
  await Promise.all(jobs);
  await cp(url("../assets/optic/"), url("../public/assets/optic/"), {
    recursive: true,
  });
}

function copyRows() {
  return [
    ["../optic.html", "../public/optic.html"],
    ["../optic-investors.html", "../public/optic-investors.html"],
    ["../src/optic_app.js", "../public/src/optic_app.js"],
    ["../src/optic_content.js", "../public/src/optic_content.js"],
    ["../src/optic_investor_app.js", "../public/src/optic_investor_app.js"],
    ["../styles/optic.css", "../public/styles/optic.css"],
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
