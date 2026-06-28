export interface Bar {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface MarkovResult {
  matrix: number[][];       // 2×2: [BEAR→BEAR, BEAR→BULL] [BULL→BEAR, BULL→BULL]
  currentState: number;     // 0=BEAR 1=BULL
  bullPersistence: number;  // matrix[1][1]
  bearPersistence: number;  // matrix[0][0]
  signal: 'BULL' | 'BEAR' | null;
  nSamples: number;
}

export interface MCResult {
  bullProb: number;
  bearProb: number;
  signal: 'BULL' | 'BEAR' | null;
  samplePaths: number[][];  // first 8 paths for sparklines
}

export interface SMCResult {
  bos: 'BULL' | 'BEAR' | null;
  liquiditySweep: 'BULL' | 'BEAR' | null;
  fvg: 'BULL' | 'BEAR' | null;
  signal: 'BULL' | 'BEAR' | null;
  patternsFound: number;
}

export interface ClaudeDecision {
  direction: 'BULL' | 'BEAR' | 'NO_TRADE';
  confidence: number;
  reasoning: string;
  loading: boolean;
}

export interface Trade {
  id: string;
  timestamp: number;
  direction: 'BULL' | 'BEAR';
  entryPrice: number;
  confidence: number;
  exitPrice?: number;
  pnl?: number;
  status: 'OPEN' | 'WIN' | 'LOSS';
}
