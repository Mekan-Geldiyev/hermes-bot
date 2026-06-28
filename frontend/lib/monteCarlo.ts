import type { MCResult } from './types';

export function runMonteCarlo(
  matrix: number[][],
  currentState: number,
  nPaths = 500,
  nSteps = 10,
  threshold = 0.55,
): MCResult {
  let bullCount = 0;
  const samplePaths: number[][] = [];

  for (let p = 0; p < nPaths; p++) {
    let state = currentState;
    const path = [state];
    for (let s = 0; s < nSteps; s++) {
      state = Math.random() < matrix[state][1] ? 1 : 0;
      path.push(state);
    }
    if (state === 1) bullCount++;
    if (p < 8) samplePaths.push(path);
  }

  const bullProb = bullCount / nPaths;
  const bearProb = 1 - bullProb;

  let signal: 'BULL' | 'BEAR' | null = null;
  if (bullProb >= threshold) signal = 'BULL';
  else if (bearProb >= threshold) signal = 'BEAR';

  return { bullProb, bearProb, signal, samplePaths };
}
