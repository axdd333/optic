import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { app } from "../server.mjs";

test("optic public and investor pages render without overflow", {
  timeout: 120000,
}, async (t) => {
  const server = app({ logLevel: "silent" }).listen(0);
  let browser;
  try {
    browser = await chromium.launch();
  } catch (err) {
    await close(server);
    t.skip(String(err));
    return;
  }
  try {
    await smoke(browser, server.address().port);
  } finally {
    await browser.close();
    await close(server);
  }
});

async function smoke(browser, port) {
  await publicSmoke(browser, port, { height: 940, width: 1440 });
  await publicSmoke(browser, port, { height: 844, width: 390 });
  await investorSmoke(browser, port);
}

async function publicSmoke(browser, port, viewport) {
  const ctx = await browser.newContext({ viewport });
  const page = await ctx.newPage();
  await failEvents(page);
  await page.goto(url(port, "/"), { waitUntil: "networkidle" });
  await waitText(page, "Know how the internet sees you.");
  await assertNoOverflow(page);
  await ctx.close();
}

async function investorSmoke(browser, port) {
  const ctx = await browser.newContext({
    viewport: { height: 940, width: 1440 },
  });
  const page = await ctx.newPage();
  await failEvents(page);
  await page.goto(url(port, "/investors"));
  await waitText(page, "Private feedback for how people are perceived.");
  await page.click('a[href="#network"]');
  await waitText(page, "Calibration can become a user-owned data economy.");
  await assertNoOverflow(page);
  await ctx.close();
}

async function failEvents(page) {
  await page.route("**/api/event", (route) => {
    route.fulfill({ body: "{}", status: 503 });
  });
}

async function waitText(page, val) {
  await page.waitForFunction((text) => {
    return document.body.textContent?.includes(text);
  }, val);
}

async function assertNoOverflow(page) {
  const ok = await page.evaluate(() => {
    const doc = document.documentElement;
    return doc.scrollWidth <= doc.clientWidth + 1;
  });
  assert.equal(ok, true);
}

function url(port, path) {
  return `http://127.0.0.1:${port}${path}`;
}

function close(server) {
  return new Promise((resolve) => server.close(resolve));
}
