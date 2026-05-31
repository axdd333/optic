import { NextRequest, NextResponse } from 'next/server';

const BACKEND = process.env.OPTIC_BACKEND_URL ?? 'http://127.0.0.1:3003';

async function proxy(req: NextRequest): Promise<NextResponse> {
  const url = new URL(req.url);
  const backendPath = url.pathname.replace(/^\/api\/backend/, '');
  const target = `${BACKEND}${backendPath}${url.search}`;

  const headers = new Headers();
  // Forward content-type and auth headers only
  const forward = ['content-type', 'authorization', 'cookie'];
  for (const h of forward) {
    const v = req.headers.get(h);
    if (v) headers.set(h, v);
  }
  // Spoof origin so ctxorg's same-origin CSRF check passes
  headers.set('host', new URL(BACKEND).host);
  headers.set('origin', BACKEND);

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
