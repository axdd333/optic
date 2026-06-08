"""Test the improved _clean_workstream_name function."""
_WS_NOISE_WORDS = {
    "https", "http", "www", "com", "org", "net", "html", "json", "xml",
    "css", "js", "php", "asp", "jsp", "htm", "xhtml",
    "image", "images", "file", "files", "copy", "backup", "final", "draft",
    "temp", "untitled", "screenshot", "screenshots", "screen",
    "photo", "photos", "picture", "pictures", "img", "pic",
    "version", "new", "old", "test", "sample", "example", "misc", "various",
    "inbox", "downloads", "desktop", "documents", "library", "folder",
    "users", "home", "root", "local", "mobile",
    "name", "path", "size", "type", "date", "true", "false", "null", "none",
    "default", "used", "found",
    "abx", "xtcftw", "rspace", "pyasn1",
    "data", "work", "beta", "tests", "examples", "docs", "generated",
    "live", "round", "very", "simple", "just", "only", "some",
}


def _clean_workstream_name(raw):
    if not raw:
        return "Other"
    name = raw.strip()
    for prefix in ["set-up-", "setup-", "config-"]:
        if name.lower().startswith(prefix):
            name = name[len(prefix):]
    name = name.replace("-", " ").replace("_", " ")
    words = name.split()
    meaningful = [w for w in words if w.lower() not in _WS_NOISE_WORDS]
    if not meaningful:
        meaningful = [w for w in words if len(w) > 1]
    if not meaningful:
        meaningful = words[:1]
    cleaned = []
    for w in meaningful:
        if w.upper() in ("AI", "API", "SSL", "DNS", "PDF", "CSS", "JS", "ML",
                         "UI", "UX", "NLP", "GPU", "CPU", "RAM", "SSD",
                         "VM", "CI", "CD", "AWS", "GCP", "SQL", "NoSQL", "DB"):
            cleaned.append(w.upper())
        elif len(w) <= 2:
            cleaned.append(w.upper())
        else:
            cleaned.append(w[0].upper() + w[1:].lower() if len(w) > 1 else w.upper())
    name = " ".join(cleaned)
    if len(name) < 2:
        name = raw[:30]
    return name.strip() or "Other"


ugly_names = [
    "HTTPS ABX XTCFTW Com",
    "Rspace XTCFTW Com Very Very Simple",
    "Live V49",
    "V1",
    "Pyasn1 Modules",
    "Round 1",
    "Beta",
    "Tests",
    "Examples",
    "Docs",
    "Trading",
    "Data",
    "Work",
    "Screenshots",
    "Downloads",
    "Generated",
    "set-up-my-project",
    "config_backend",
    "AI Research",
    "API Gateway Service",
    "PDF Reports",
    "DNS Config",
    "my-code-project",
    "Photos from trip",
    "desktop stuff",
]

print("BEFORE vs AFTER cleaning:\n")
for n in ugly_names:
    cleaned = _clean_workstream_name(n)
    print(f"  {n!r:42s} -> {cleaned!r}")
