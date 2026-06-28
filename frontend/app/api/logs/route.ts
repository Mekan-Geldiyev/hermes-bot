import { NextRequest, NextResponse } from 'next/server';

const BOT_URL = process.env.HERMES_BOT_URL?.replace(/\/$/, '');

export async function GET(req: NextRequest) {
  const n = req.nextUrl.searchParams.get('n') ?? '150';

  if (BOT_URL) {
    try {
      const res = await fetch(`${BOT_URL}/logs?n=${n}`, {
        cache: 'no-store',
        signal: AbortSignal.timeout(3000),
      });
      return NextResponse.json(await res.json());
    } catch { /* fall through */ }
  }

  try {
    const res = await fetch(`http://localhost:8080/logs?n=${n}`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(3000),
    });
    return NextResponse.json(await res.json());
  } catch { /* fall through */ }

  return NextResponse.json({ lines: [] });
}
