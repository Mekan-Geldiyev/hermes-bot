/**
 * Proxy route: fetches live paper trade data from the Python bot.
 *
 * Strategy (in order):
 *  1. If HERMES_BOT_URL is set → forward to {HERMES_BOT_URL}/trades  (Amplify / remote)
 *  2. Try http://localhost:8080/trades                                (local dev)
 *  3. Fallback: return empty ledger
 */
import { NextResponse } from 'next/server';

const BOT_URL = process.env.HERMES_BOT_URL?.replace(/\/$/, '');

const EMPTY = { initial: 20, balance: 20, trades: [] };

async function fetchFrom(url: string) {
  const res = await fetch(url, {
    cache: 'no-store',
    signal: AbortSignal.timeout(3000),
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export async function GET() {
  // 1. Explicit bot URL (set on Amplify when bot runs on EC2/ngrok)
  if (BOT_URL) {
    try {
      return NextResponse.json(await fetchFrom(`${BOT_URL}/trades`));
    } catch { /* fall through */ }
  }

  // 2. Local dev — bot on same machine
  try {
    return NextResponse.json(await fetchFrom('http://localhost:8080/trades'));
  } catch { /* fall through */ }

  // 3. Nothing running
  return NextResponse.json(EMPTY);
}
