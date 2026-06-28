import type { Bar, SMCResult } from './types';

function detectBOS(bars: Bar[], lookback = 14): 'BULL' | 'BEAR' | null {
  if (bars.length < lookback + 1) return null;
  const window = bars.slice(-(lookback + 1), -1);
  const cur = bars[bars.length - 1];
  const swingHigh = Math.max(...window.map(b => b.high));
  const swingLow  = Math.min(...window.map(b => b.low));
  if (cur.high > swingHigh) return 'BULL';
  if (cur.low  < swingLow)  return 'BEAR';
  return null;
}

function detectLiquiditySweep(bars: Bar[], lookback = 8): 'BULL' | 'BEAR' | null {
  if (bars.length < lookback + 1) return null;
  const window = bars.slice(-(lookback + 1), -1);
  const cur = bars[bars.length - 1];
  const recentLow  = Math.min(...window.map(b => b.low));
  const recentHigh = Math.max(...window.map(b => b.high));
  if (cur.low  < recentLow  && cur.close > recentLow)  return 'BULL';
  if (cur.high > recentHigh && cur.close < recentHigh) return 'BEAR';
  return null;
}

function detectFVG(bars: Bar[]): 'BULL' | 'BEAR' | null {
  if (bars.length < 3) return null;
  const [c1, , c3] = bars.slice(-3);
  if (c1.high < c3.low)  return 'BULL';
  if (c1.low  > c3.high) return 'BEAR';
  return null;
}

function majority(sigs: ('BULL' | 'BEAR' | null)[]): 'BULL' | 'BEAR' | null {
  const found = sigs.filter(Boolean) as ('BULL' | 'BEAR')[];
  if (!found.length) return null;
  const b = found.filter(s => s === 'BULL').length;
  const r = found.filter(s => s === 'BEAR').length;
  return b > r ? 'BULL' : r > b ? 'BEAR' : null;
}

export function computeSMC(bars: Bar[]): SMCResult {
  const bos            = detectBOS(bars);
  const liquiditySweep = detectLiquiditySweep(bars);
  const fvg            = detectFVG(bars);
  return {
    bos, liquiditySweep, fvg,
    signal: majority([bos, liquiditySweep, fvg]),
    patternsFound: [bos, liquiditySweep, fvg].filter(Boolean).length,
  };
}
