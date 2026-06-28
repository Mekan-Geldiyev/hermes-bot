import { NextResponse } from 'next/server';

const BOT_URL = process.env.HERMES_BOT_URL?.replace(/\/$/, '');

export async function GET() {
  for (const base of [BOT_URL, 'http://localhost:8080'].filter(Boolean)) {
    try {
      const res = await fetch(`${base}/status`, {
        cache: 'no-store',
        signal: AbortSignal.timeout(2000),
      });
      return NextResponse.json(await res.json());
    } catch { /* try next */ }
  }
  return NextResponse.json({ running: false, last_price: null });
}
