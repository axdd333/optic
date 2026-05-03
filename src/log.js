const rank = {
  debug: 10,
  error: 40,
  info: 20,
  silent: 99,
  warn: 30,
};

export function logger(cfg, sink = console) {
  return {
    error: (msg, ctx = {}) => emit(cfg, sink, "error", msg, ctx),
    info: (msg, ctx = {}) => emit(cfg, sink, "info", msg, ctx),
    warn: (msg, ctx = {}) => emit(cfg, sink, "warn", msg, ctx),
  };
}

function emit(cfg, sink, level, msg, ctx) {
  if (!enabled(cfg.logLevel, level)) return;
  const row = { ...ctx, level, msg, ts: new Date().toISOString() };
  const fn = level === "error" ? sink.error : sink.log;
  fn.call(sink, JSON.stringify(row));
}

function enabled(min, level) {
  return rank[level] >= (rank[min] ?? rank.info);
}
