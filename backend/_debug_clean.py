"""Debug the noise word filtering."""
noise = {
    "https", "http", "www", "com", "org", "net", "html",
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
        meaningful = [w for w in words if len(w) > 1]
    if not meaningful:
        meaningful = words[:1]
    cleaned = []
    for w in meaningful:
        if w.upper() in ("AI", "API", "SSL", "DNS", "PDF", "CSS", "JS", "ML"):
            cleaned.append(w.upper())
        elif len(w) <= 2:
            cleaned.append(w.upper())
        else:
            cleaned.append(w[0].upper() + w[1:].lower() if len(w) > 1 else w.upper())
    name = " ".join(cleaned)
    return name.strip() or "Other"

# Test
raw = "HTTPS ABX XTCFTW Com"
words = raw.split()
print(f"Words: {words}")
print(f"Lowered: {[w.lower() for w in words]}")
print(f"In noise? https:{'https' in noise}, abx:{'abx' in noise}, xtcftw:{'xtcftw' in noise}, com:{'com' in noise}")
meaningful = [w for w in words if w.lower() not in noise]
print(f"Meaningful: {meaningful}")
print(f"Result: {clean(raw)!r}")
