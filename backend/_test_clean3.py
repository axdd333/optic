"""Test the fixed _clean_workstream_name function."""
noise = {
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
    "screenshots", "downloads",
}


def clean(raw):
    if not raw: return "Other"
    name = raw.strip()
    for prefix in ["set-up-", "setup-", "config-"]:
        if name.lower().startswith(prefix):
            name = name[len(prefix):]
    name = name.replace("-", " ").replace("_", " ")
    words = name.split()
    meaningful = [w for w in words if w.lower() not in noise]
    if not meaningful:
        meaningful = [w for w in words if len(w) > 2 and not w.isdigit()]
    if not meaningful:
        return raw[:30] or "Other"
    cleaned = []
    for w in meaningful:
        if w.upper() in ("AI", "API", "SSL", "DNS", "PDF", "CSS", "JS", "ML"):
            cleaned.append(w.upper())
        elif len(w) <= 2:
            cleaned.append(w.upper())
        else:
            cleaned.append(w[0].upper() + w[1:].lower() if len(w) > 1 else w.upper())
    name = " ".join(cleaned)
    if len(name) < 2:
        name = raw[:30]
    return name.strip() or "Other"


test_names = [
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
    "src",
    "Src",
]

print("CLEANING RESULTS:\n")
for n in test_names:
    print(f"  {n!r:42s} -> {clean(n)!r}")
