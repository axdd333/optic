export function loadCfg(env = process.env) {
  const cfg = {
    host: str(env.HOST, "0.0.0.0"),
    logLevel: str(env.LOG_LEVEL, "info"),
    port: int(env.PORT, 8080),
    root: str(env.OPTIC_ROOT, process.cwd()),
  };
  return Object.freeze(cfg);
}

function int(val, fallback) {
  const num = Number.parseInt(val || "", 10);
  return Number.isFinite(num) && num > 0 ? num : fallback;
}

function str(val, fallback) {
  return String(val || fallback);
}
