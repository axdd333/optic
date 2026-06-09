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
        return raw.strip()[:30] or "Other"
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
    # Pure noise names
    ("HTTPS ABX XTCFTW Com", "raw only (all noise)"),
    ("Rspace XTCFTW Com Very Very Simple", "raw only (all noise)"),
    # Mixed noise+meaningful  
    ("HTTPS ABX XTCFTW Com Project Alpha", "noise + meaningful"),
    ("src optic backend server", "partially noise"),
    ("Downloads Research Papers", "one noise word"),
    ("data Trading Strat", "one noise word"),
    # Clean names
    ("AI Research", "clean"),
    ("API Gateway Service", "clean"),
    ("my-code-project", "hyphens"),
    ("config_backend", "underscores + noise prefix"),
    ("set-up-project-alpha", "set-up prefix"),
    # Edge cases  
    ("V1", "short"),
    ("src", "all-noise short"),
    ("Trading", "clean single"),
]

print("CLEANING RESULTS:\n")
for n, desc in test_names:
    print(f"  {n!r:50s} -> {clean(n)!r:30s}  ({desc})")
