import { NextRequest, NextResponse } from 'next/server';
import { createHash, randomBytes } from 'crypto';
import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { join } from 'path';

const DATA_DIR = join(process.cwd(), '.optic');
const USERS_FILE = join(DATA_DIR, 'users.json');

function hash(password: string, salt: string) {
  return createHash('sha256').update(password + salt).digest('hex');
}

function loadUsers(): Array<{ id: string; email: string; salt: string; hash: string; created_at: string }> {
  try {
    return JSON.parse(readFileSync(USERS_FILE, 'utf8'));
  } catch {
    return [];
  }
}

function saveUsers(users: ReturnType<typeof loadUsers>) {
  mkdirSync(DATA_DIR, { recursive: true });
  writeFileSync(USERS_FILE, JSON.stringify(users, null, 2));
}

export async function POST(req: NextRequest) {
  const { email, password } = await req.json();

  if (!email || !password) {
    return NextResponse.json({ error: 'Email and password are required.' }, { status: 400 });
  }
  if (password.length < 8) {
    return NextResponse.json({ error: 'Password must be at least 8 characters.' }, { status: 400 });
  }

  const users = loadUsers();
  if (users.find(u => u.email.toLowerCase() === email.toLowerCase())) {
    return NextResponse.json({ error: 'An account with that email already exists.' }, { status: 409 });
  }

  const salt = randomBytes(16).toString('hex');
  const newUser = {
    id: randomBytes(8).toString('hex'),
    email: email.toLowerCase().trim(),
    salt,
    hash: hash(password, salt),
    created_at: new Date().toISOString(),
  };

  users.push(newUser);
  saveUsers(users);

  const res = NextResponse.json({ ok: true });
  res.cookies.set('optic_session', newUser.id, {
    httpOnly: true,
    sameSite: 'lax',
    path: '/',
    maxAge: 60 * 60 * 24 * 30,
  });
  return res;
}
