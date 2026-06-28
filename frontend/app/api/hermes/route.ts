import { NextRequest, NextResponse } from 'next/server';

const MOCK_RESPONSES: Record<string, { reasoning: string }> = {
  BULL: {
    reasoning: 'Markov persistence and MC paths both confirm momentum continuation. SMC structure shows clean BOS with liquidity cleared below — smart money positioned long.',
  },
  BEAR: {
    reasoning: 'Bearish Markov persistence dominates. MC simulation shows >60% paths ending bearish. FVG overhead unmitigated — expect reversion sell-off.',
  },
  NO_TRADE: {
    reasoning: 'Signal divergence detected. Markov and MC disagree on direction. Insufficient structural conviction to enter. Waiting for cleaner setup.',
  },
};

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { markov, mc, smc, btcPrice, yesPrice } = body;

  const apiKey = process.env.ANTHROPIC_API_KEY;

  // ── Real Claude path ─────────────────────────────────────────────────────
  if (apiKey) {
    try {
      const Anthropic = (await import('@anthropic-ai/sdk')).default;
      const client = new Anthropic({ apiKey });

      const prompt = `Current BTC: $${Number(btcPrice).toLocaleString()}
Polymarket YES (Up) price: ${yesPrice}

MARKOV (${markov.nSamples} samples)
P(Bull→Bull): ${markov.bullPersistence.toFixed(3)}  P(Bear→Bear): ${markov.bearPersistence.toFixed(3)}
Current state: ${markov.currentState === 1 ? 'BULL' : 'BEAR'}  Signal: ${markov.signal ?? 'NONE'}

MONTE CARLO (500 paths × 10 steps)
P(end=BULL): ${mc.bullProb.toFixed(3)}  P(end=BEAR): ${mc.bearProb.toFixed(3)}  Signal: ${mc.signal ?? 'NONE'}

SMC PATTERNS
BOS: ${smc.bos ?? 'NONE'}  Sweep: ${smc.liquiditySweep ?? 'NONE'}  FVG: ${smc.fvg ?? 'NONE'}
Consensus: ${smc.signal ?? 'NONE'} (${smc.patternsFound}/3 patterns)

Output ONLY valid JSON — no markdown:
{"direction":"BULL"|"BEAR"|"NO_TRADE","confidence":0.00,"reasoning":"max 20 words"}`;

      const msg = await client.messages.create({
        model: 'claude-opus-4-8',
        max_tokens: 150,
        system: 'You are Hermes, a quant trading brain. Synthesise signals and output a single JSON trading decision. Be terse.',
        messages: [{ role: 'user', content: prompt }],
      });

      const raw = (msg.content[0] as { text: string }).text.trim();
      const parsed = JSON.parse(raw);
      return NextResponse.json({ ...parsed, source: 'claude' });
    } catch {
      // Fall through to mock
    }
  }

  // ── Simulated path (no API key needed) ──────────────────────────────────
  const votes = [markov.signal, mc.signal, smc.signal].filter(Boolean);
  const bulls = votes.filter((v: string) => v === 'BULL').length;
  const bears = votes.filter((v: string) => v === 'BEAR').length;

  let direction: string;
  let confidence: number;

  if (bulls === 3) {
    direction = 'BULL';
    confidence = 0.71 + markov.bullPersistence * 0.15;
  } else if (bears === 3) {
    direction = 'BEAR';
    confidence = 0.71 + markov.bearPersistence * 0.15;
  } else if (bulls >= 2) {
    direction = 'BULL';
    confidence = 0.58 + mc.bullProb * 0.1;
  } else if (bears >= 2) {
    direction = 'BEAR';
    confidence = 0.58 + mc.bearProb * 0.1;
  } else {
    direction = 'NO_TRADE';
    confidence = 0;
  }

  return NextResponse.json({
    direction,
    confidence: Math.min(0.96, confidence),
    reasoning: MOCK_RESPONSES[direction]?.reasoning ?? MOCK_RESPONSES.NO_TRADE.reasoning,
    source: 'simulated',
  });
}
