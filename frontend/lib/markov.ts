import type { MarkovResult } from './types';

export function computeMarkov(prices: number[], threshold = 0.87): MarkovResult {
  if (prices.length < 10) {
    return {
      matrix: [[0.5, 0.5], [0.5, 0.5]],
      currentState: 1,
      bullPersistence: 0.5,
      bearPersistence: 0.5,
      signal: null,
      nSamples: prices.length,
    };
  }

  const states: number[] = [];
  for (let i = 1; i < prices.length; i++) {
    states.push(prices[i] > prices[i - 1] ? 1 : 0);
  }

  const counts = [[0, 0], [0, 0]];
  for (let i = 0; i < states.length - 1; i++) {
    counts[states[i]][states[i + 1]]++;
  }

  const matrix = counts.map(row => {
    const sum = row[0] + row[1];
    return sum === 0 ? [0.5, 0.5] : [row[0] / sum, row[1] / sum];
  });

  const currentState = states[states.length - 1];
  const bullPersistence = matrix[1][1];
  const bearPersistence = matrix[0][0];

  let signal: 'BULL' | 'BEAR' | null = null;
  if (bullPersistence >= threshold) signal = 'BULL';
  else if (bearPersistence >= threshold) signal = 'BEAR';

  return { matrix, currentState, bullPersistence, bearPersistence, signal, nSamples: states.length };
}
