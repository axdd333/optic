import { createServer } from "node:http";
import { fileURLToPath } from "node:url";

import { loadCfg } from "./src/cfg.js";
import { json, text } from "./src/http.js";
import { logger } from "./src/log.js";
import { pickFile } from "./src/route.js";
import { createState } from "./src/state.js";
import { sendFile } from "./src/static.js";

const cfg = loadCfg();
const log = logger(cfg);

export function app(over = {}) {
  const ctx = makeCtx(over);
  return createServer((req, res) => serve(ctx, req, res));
}

async function serve(ctx, req, res) {
  try {
    ctx.state.act({ type: "req" });
    return await dispatch(ctx, req, res);
  } catch (err) {
    return fail(ctx, res, err);
  }
}

async function dispatch(ctx, req, res) {
  const url = reqUrl(req);
  if (req.method === "GET" && url.pathname === "/healthz") {
    return health(ctx, res);
  }
  if (url.pathname === "/api/event") return event(ctx, req, res);
  if (req.method !== "GET" && req.method !== "HEAD") {
    return json(res, 405, { ok: false, msg: "method" });
  }
  return staticReq(ctx, req, res, url);
}

async function event(ctx, req, res) {
  if (req.method !== "POST") return json(res, 405, { ok: false });
  await readBody(req);
  ctx.state.act({ type: "event" });
  return json(res, 202, { ok: true });
}

function staticReq(ctx, req, res, url) {
  const file = pickFile(url.pathname);
  if (!file) return text(res, 404, "not found");
  if (req.method === "HEAD") return text(res, 200, "");
  return sendFile(ctx, res, file);
}

function health(ctx, res) {
  return json(res, 200, { ok: true, state: ctx.state.snap() });
}

function fail(ctx, res, err) {
  ctx.state.act({ type: "error" });
  ctx.log.error("request_failed", { err: err.message });
  return json(res, 500, { ok: false, msg: "error" });
}

function makeCtx(over) {
  const { env, ...cfgOver } = over;
  const cfg = { ...loadCfg(env), ...cfgOver };
  return { cfg, log: logger(cfg), state: createState() };
}

function reqUrl(req) {
  const host = req.headers.host || "localhost";
  return new URL(req.url || "/", `http://${host}`);
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

if (isMain()) {
  app().listen(cfg.port, cfg.host, onListen);
}

function onListen() {
  log.info("listen", { host: cfg.host, port: cfg.port });
}

function isMain() {
  if (!process.argv[1]) return false;
  return fileURLToPath(import.meta.url) === process.argv[1];
}
