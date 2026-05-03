export const initSrv = Object.freeze({
  errors: 0,
  events: 0,
  reqs: 0,
});

export function reduceSrv(st = initSrv, act = {}) {
  if (act.type === "error") return inc(st, "errors");
  if (act.type === "event") return inc(st, "events");
  if (act.type === "req") return inc(st, "reqs");
  return st;
}

export function createState(seed = initSrv) {
  let st = seed;
  return {
    act: (act) => {
      st = reduceSrv(st, act);
    },
    snap: () => st,
  };
}

function inc(st, key) {
  return Object.freeze({ ...st, [key]: st[key] + 1 });
}
