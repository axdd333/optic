import { NextRequest, NextResponse } from 'next/server';

const BACKEND = process.env.OPTIC_BACKEND_URL ?? 'http://127.0.0.1:3003';

// ── Internal proxy token — shared secret between Next.js proxy and ctxorg backend ──
// The backend skips CSRF when this header is present with the correct value.
const INTERNAL_PROXY_TOKEN = process.env.OPTIC_INTERNAL_PROXY_TOKEN ?? 'optic-proxy-v1';

// ── Route allowlist — only these path prefixes may be proxied (Finding 2) ──
const ALLOWED_PREFIXES: string[] = [
  '/api/runs', '/api/graph', '/api/reveal', '/api/open', '/api/delta',
  '/api/workstreams', '/api/report', '/api/status', '/api/embeddings/status',
  '/api/home', '/api/account', '/api/workspace', '/api/api-keys',
  '/api/billing', '/api/settings', '/api/integrations',
  '/api/audiences', '/api/simulations', '/api/simulate/',
  '/api/exports', '/api/infer', '/api/analyze', '/api/entity/profile',
  '/api/audience', '/api/audit', '/api/chat', '/api/iris',
  '/api/rename', '/api/signup', '/api/signin', '/api/signout',
  '/api/scan', '/api/embed/run',
  '/api/vana/',
  '/api/v1/',
  '/healthz', '/readyz', '/api/health', '/api/ready',
  '/static/',
];

function isAllowed(backendPath: string): boolean {
  for (const prefix of ALLOWED_PREFIXES) {
    if (backendPath === prefix || backendPath.startsWith(prefix)) return true;
  }
  // Sub-paths under allowed prefixes are also permitted
  return false;
}

async function proxy(req: NextRequest): Promise<NextResponse> {
  const url = new URL(req.url);
  const backendPath = url.pathname.replace(/^\/api\/backend/, '');

  // ── Route allowlist check (Finding 2) ──
  if (!isAllowed(backendPath)) {
    return NextResponse.json({ ok: false, err: 'route_not_allowed' }, { status: 404 });
  }

  const target = `${BACKEND}${backendPath}${url.search}`;

  const headers = new Headers();
  // Forward content-type and auth headers only
  const forward = ['content-type', 'authorization', 'cookie'];
  for (const h of forward) {
    const v = req.headers.get(h);
    if (v) headers.set(h, v);
  }
  // Set internal proxy token so backend can skip CSRF for trusted proxy requests (Finding 1)
  headers.set('host', new URL(BACKEND).host);
  headers.set('x-internal-proxy', INTERNAL_PROXY_TOKEN);

  const hasBody = req.method !== 'GET' && req.method !== 'HEAD';
  let bodyContent: string | undefined;
  if (hasBody) {
    bodyContent = await req.text();
  }
  const init: RequestInit = {
    method: req.method,
    headers,
    ...(hasBody && bodyContent ? { body: bodyContent } : {}),
  };

  try {
    const upstream = await fetch(target, init);
    const buf = await upstream.arrayBuffer();
    const resHeaders = new Headers();
    const skip = new Set(['transfer-encoding', 'connection', 'keep-alive']);
    upstream.headers.forEach((val, key) => {
      if (!skip.has(key.toLowerCase())) resHeaders.set(key, val);
    });
    return new NextResponse(buf, { status: upstream.status, headers: resHeaders });
  } catch (err) {
    console.error('[backend proxy] unreachable:', err);
    return NextResponse.json({ error: 'backend_unavailable' }, { status: 502 });
  }
}

export const dynamic = 'force-dynamic';
export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
