const exact = {
  "/": "optic.html",
  "/apple-touch-icon.png": "apple-touch-icon.png",
  "/favicon.svg": "favicon.svg",
  "/favicon-32.png": "favicon-32.png",
  "/investors": "optic-investors.html",
  "/app-privacy": "legal-app-privacy.html",
  "/cookies": "legal-cookies.html",
  "/legal": "legal.html",
  "/legal/": "legal.html",
  "/notice-at-collection": "legal-notice.html",
  "/optic-interactive.html": "optic-interactive.html",
  "/optic-investors.html": "optic-investors.html",
  "/optic.html": "optic.html",
  "/privacy": "legal-privacy.html",
  "/robots.txt": "robots.txt",
  "/site.webmanifest": "site.webmanifest",
  "/sitemap.xml": "sitemap.xml",
  "/terms": "legal-terms.html",
};

const dirs = ["assets/optic/", "assets/vendor/", "docs/", "src/", "styles/"];

export function pickFile(path) {
  const clean = cleanPath(path);
  if (exact[clean] !== undefined) return exact[clean];
  const file = clean.replace(/^\/+/, "");
  if (bad(file)) return "";
  return dirs.some((dir) => file.startsWith(dir)) ? file : "";
}

function cleanPath(path) {
  try {
    return decodeURIComponent(path || "/");
  } catch {
    return "/";
  }
}

function bad(file) {
  return file.includes("..") || file.startsWith(".") || file.includes("/.");
}
