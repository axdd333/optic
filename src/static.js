import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";

import { send, staticHead, text } from "./http.js";

export async function sendFile(ctx, res, file) {
  const safe = safeFile(file);
  if (!safe) return text(res, 404, "not found");
  try {
    const buf = await readFile(join(ctx.cfg.root, safe));
    return send(res, 200, staticHead(extname(safe), cache(safe)), buf);
  } catch {
    return text(res, 404, "not found");
  }
}

function safeFile(file) {
  const clean = normalize(file).replace(/^(\.\.[/\\])+/, "");
  if (clean.startsWith("/") || clean.startsWith(".")) return "";
  return clean;
}

function cache(file) {
  if (file.endsWith(".html")) return "no-store";
  if (file.endsWith(".md")) return "no-store";
  return "public, max-age=604800";
}
