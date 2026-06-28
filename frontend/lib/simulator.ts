import type { Bar } from './types';

const MAX_BARS = 120;

// Geometric Brownian Motion with Hurst-like momentum persistence
export class PriceSimulator {
  private price: number;
  private momentum: number;
  private trend: number;        // slow-moving regime bias
  private trendTimer: number;
  private bars: Bar[];

  constructor(initialPrice = 104_800) {
    this.price = initialPrice;
    this.momentum = 0;
    this.trend = 0.00005;
    this.trendTimer = 0;
    this.bars = [];
    // Pre-seed with history so Markov has data immediately
    for (let i = 0; i < 80; i++) this._tick();
  }

  private _randn(): number {
    // Box-Muller
    const u = 1 - Math.random();
    const v = Math.random();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }

  private _tick(): Bar {
    // Regime flip every 20–60 ticks
    this.trendTimer++;
    if (this.trendTimer > 20 + Math.random() * 40) {
      this.trend = (Math.random() - 0.48) * 0.0003;
      this.trendTimer = 0;
    }

    const sigma = 0.0008;
    const noise = this._randn() * sigma;
    // Momentum persistence (Hurst ~0.6 feel)
    const ret = this.trend + noise + this.momentum * 0.35;
    this.momentum = ret * 0.6;

    const open  = this.price;
    const close = open * (1 + ret);
    const wick  = Math.abs(noise) * 2;
    const high  = Math.max(open, close) * (1 + wick);
    const low   = Math.min(open, close) * (1 - wick);

    this.price = close;

    const bar: Bar = {
      timestamp: Date.now(),
      open, high, low, close,
      volume: 8 + Math.random() * 40,
    };

    this.bars.push(bar);
    if (this.bars.length > MAX_BARS) this.bars.shift();
    return bar;
  }

  tick(): Bar { return this._tick(); }

  getBars(): Bar[] { return [...this.bars]; }
  getPrices(): number[] { return this.bars.map(b => b.close); }
  getPrice(): number { return this.price; }
}
