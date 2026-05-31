import { NextRequest, NextResponse } from 'next/server';
import { createHash } from 'crypto';
import { readFileSync } from 'fs';
import { join } from 'path';

const USERS_FILE = join(process.cwd(), '.optic', 'users.json');

function hash(password: string, salt: string) {
  return createHash('sha256').update(password + salt).digest('hex');
}

function loadUsers(): Array<{ id: string; email: string; salt: string; hash: string }> {
  try {
    return JSON.parse(readFileSync(USERS_FILE, 'utf8'));
  } catch {
    return [];
  }
}

export async function POST(req: NextRequest) {
  const { email, password } = await req.json();

  if (!email || !password) {
    return NextResponse.json({ error: 'Email and password are required.' }, { status: 400 });
  }

  const users = loadUsers();
  const user = users.find(u => u.email === email.toLowerCase().trim());

  if (!user || hash(password, user.salt) !== user.hash) {
    return NextResponse.json({ error: 'Invalid email or password.' }, { status: 401 });
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set('optic_session', user.id, {
    httpOnly: true,
    sameSite: 'lax',
    path: '/',
    maxAge: 60 * 60 * 24 * 30,
  });
  return res;
}
