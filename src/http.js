const types = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".md": "text/markdown; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".txt": "text/plain; charset=utf-8",
  ".webmanifest": "application/manifest+json; charset=utf-8",
  ".xml": "application/xml; charset=utf-8",
};

export function json(res, status, body) {
  send(res, status, head(types[".json"], "no-store"), jsonBody(body));
}

export function text(res, status, body) {
  send(res, status, head(types[".txt"], "no-store"), body);
}

export function staticHead(ext, cache) {
  return head(types[ext] || types[".html"], cache);
}

export function send(res, status, headers, body) {
  res.writeHead(status, headers);
  res.end(body);
}

function jsonBody(body) {
  return JSON.stringify(body);
}

function head(type, cache) {
  return {
    "cache-control": cache,
    "content-type": type,
    "x-content-type-options": "nosniff",
  };
}
