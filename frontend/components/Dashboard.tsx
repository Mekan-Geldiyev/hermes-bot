'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell,
} from 'recharts';
import { PriceSimulator } from '@/lib/simulator';
import { computeMarkov } from '@/lib/markov';
import { runMonteCarlo } from '@/lib/monteCarlo';
import { computeSMC } from '@/lib/smc';
import type { MarkovResult, MCResult, SMCResult, ClaudeDecision } from '@/lib/types';

// ─── types ────────────────────────────────────────────────────────────────────

interface LogLine {
  text: string;
  tag: 'error' | 'success' | 'warn' | 'highlight' | 'signal' | 'info';
}

interface SkipEntry {
  id: string;
  timestamp: string;
  market: string;
  ticker: string;
  direction: 'BULL' | 'BEAR';
  entry_btc: number;
  yes_price: number;
  no_price: number;
  confidence: number;
  reasoning: string;
  would_have_won: boolean | null;
  exit_btc: number | null;
}

interface BotTrade {
  id: string;
  timestamp: string;
  market: string;
  direction: 'BULL' | 'BEAR';
  entry_btc: number;
  yes_price: number;
  no_price: number;
  confidence: number;
  reasoning: string;
  size_usdc: number;
  result: 'WIN' | 'LOSS' | null;
  exit_btc: number | null;
  pnl: number | null;
}

interface Ledger {
  initial: number;
  balance: number;
  trades: BotTrade[];
}

// ─── helpers ──────────────────────────────────────────────────────────────────

const fmt  = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 0 });
const pct  = (n: number) => (n * 100).toFixed(1) + '%';
const now  = () => new Date().toLocaleTimeString('en-US', { hour12: false });

function sigColor(s: string | null) {
  if (s === 'BULL') return 'text-bull';
  if (s === 'BEAR') return 'text-bear';
  return 'text-gray-500';
}
function sigBg(s: string | null) {
  if (s === 'BULL') return 'bg-bull/10 border-bull/40 text-bull';
  if (s === 'BEAR') return 'bg-bear/10 border-bear/40 text-bear';
  return 'bg-white/5 border-white/10 text-gray-500';
}

// ─── sub-components ───────────────────────────────────────────────────────────

function Badge({ sig }: { sig: string | null }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[11px] font-mono font-bold tracking-wider ${sigBg(sig)}`}>
      {sig === 'BULL' ? '▲' : sig === 'BEAR' ? '▼' : '–'} {sig ?? 'NONE'}
    </span>
  );
}

function Card({ title, children, glow, right }: {
  title: React.ReactNode;
  children: React.ReactNode;
  glow?: 'bull' | 'bear' | null;
  right?: React.ReactNode;
}) {
  const border = glow === 'bull' ? 'border-bull/30 shadow-[0_0_18px_rgba(0,217,135,0.08)]'
               : glow === 'bear' ? 'border-bear/30 shadow-[0_0_18px_rgba(255,60,90,0.08)]'
               : 'border-white/[0.06]';
  return (
    <div className={`rounded-xl border bg-[#0d0d11] p-4 ${border} transition-all duration-500`}>
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] uppercase tracking-[0.2em] text-gray-600 font-mono">{title}</p>
        {right && <div>{right}</div>}
      </div>
      {children}
    </div>
  );
}

// ─── Paper Trades Panel ───────────────────────────────────────────────────────

function PaperTradesPanel({ ledger, connected, lastFetched }: {
  ledger: Ledger;
  connected: boolean;
  lastFetched: Date | null;
}) {
  const resolved = ledger.trades.filter(t => t.result !== null);
  const pending  = ledger.trades.filter(t => t.result === null);
  const wins     = resolved.filter(t => t.result === 'WIN');
  const roi      = ledger.initial > 0 ? ((ledger.balance - ledger.initial) / ledger.initial) * 100 : 0;
  const winRate  = resolved.length > 0 ? (wins.length / resolved.length) * 100 : 0;

  const statusDot = connected
    ? <span className="inline-flex items-center gap-1.5 text-[10px] text-bull"><span className="w-1.5 h-1.5 rounded-full bg-bull animate-pulse-fast inline-block" />LIVE</span>
    : <span className="inline-flex items-center gap-1.5 text-[10px] text-gray-600"><span className="w-1.5 h-1.5 rounded-full bg-gray-700 inline-block" />OFFLINE</span>;

  const titleNode = <span>PAPER TRADES · HERMES BOT</span>;
  const rightNode = (
    <div className="flex items-center gap-3">
      {lastFetched && (
        <span className="text-[10px] text-gray-700">
          {lastFetched.toLocaleTimeString('en-US', { hour12: false })}
        </span>
      )}
      {statusDot}
    </div>
  );

  return (
    <Card title={titleNode} right={rightNode} glow={connected && ledger.trades.length > 0 ? (roi >= 0 ? 'bull' : 'bear') : null}>

      {/* Summary row */}
      <div className="grid grid-cols-4 gap-2 mb-4">
        {[
          { label: 'Account', val: `$${ledger.initial.toFixed(2)}`, color: 'text-gray-400' },
          { label: 'Balance', val: `$${ledger.balance.toFixed(2)}`, color: roi >= 0 ? 'text-bull' : 'text-bear' },
          { label: 'Win Rate', val: resolved.length ? `${winRate.toFixed(0)}%` : '—', color: winRate >= 55 ? 'text-bull' : winRate > 0 ? 'text-warn' : 'text-gray-500' },
          { label: 'ROI', val: ledger.trades.length ? `${roi >= 0 ? '+' : ''}${roi.toFixed(1)}%` : '—', color: roi >= 0 ? 'text-bull' : 'text-bear' },
        ].map(s => (
          <div key={s.label} className="bg-white/[0.03] rounded-lg p-2 text-center">
            <div className="text-[9px] text-gray-600 uppercase tracking-wider mb-1">{s.label}</div>
            <div className={`text-[14px] font-bold font-mono ${s.color}`}>{s.val}</div>
          </div>
        ))}
      </div>

      {/* Balance bar */}
      {ledger.trades.length > 0 && (
        <div className="relative h-1.5 bg-white/5 rounded-full mb-4 overflow-hidden">
          <div
            className={`absolute left-0 top-0 h-full rounded-full transition-all duration-700 ${roi >= 0 ? 'bg-bull/60' : 'bg-bear/60'}`}
            style={{ width: `${Math.min(100, Math.max(0, (ledger.balance / (ledger.initial * 2)) * 100))}%` }}
          />
        </div>
      )}

      {/* Trade table */}
      {!connected && ledger.trades.length === 0 ? (
        <div className="py-6 text-center">
          <p className="text-[12px] text-gray-600 mb-1">Bot is offline</p>
          <p className="text-[10px] text-gray-700 font-mono">python -m hermes.main</p>
        </div>
      ) : ledger.trades.length === 0 ? (
        <p className="text-[12px] text-gray-600 text-center py-4">
          Bot connected — waiting for first trade signal
        </p>
      ) : (
        <div className="overflow-auto max-h-64">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-gray-600 border-b border-white/[0.05]">
                <th className="text-left pb-1.5 font-normal">Time</th>
                <th className="text-left pb-1.5 font-normal">Dir</th>
                <th className="text-right pb-1.5 font-normal">Entry</th>
                <th className="text-right pb-1.5 font-normal">Odds</th>
                <th className="text-right pb-1.5 font-normal">Size</th>
                <th className="text-right pb-1.5 font-normal">Result</th>
                <th className="text-right pb-1.5 font-normal">P&L</th>
              </tr>
            </thead>
            <tbody>
              {[...ledger.trades].reverse().map(t => {
                const price = t.direction === 'BULL' ? t.yes_price : t.no_price;
                return (
                  <React.Fragment key={t.id}>
                    <tr className="border-b border-white/[0.03] hover:bg-white/[0.02] group">
                      <td className="py-1.5 text-gray-500">
                        {new Date(t.timestamp).toLocaleTimeString('en-US', { hour12: false, month: 'short', day: 'numeric' }).slice(0, 12)}
                      </td>
                      <td className={`py-1.5 font-bold ${t.direction === 'BULL' ? 'text-bull' : 'text-bear'}`}>
                        {t.direction === 'BULL' ? '▲' : '▼'} {t.direction}
                      </td>
                      <td className="py-1.5 text-right text-gray-400 font-mono">${fmt(t.entry_btc)}</td>
                      <td className="py-1.5 text-right text-gray-500 font-mono">{price.toFixed(3)}</td>
                      <td className="py-1.5 text-right text-gray-400 font-mono">${t.size_usdc.toFixed(2)}</td>
                      <td className={`py-1.5 text-right font-bold ${
                        t.result === null  ? 'text-warn' :
                        t.result === 'WIN' ? 'text-bull' : 'text-bear'
                      }`}>
                        {t.result === null ? 'OPEN' : t.result === 'WIN' ? 'WIN ✓' : 'LOSS ✗'}
                      </td>
                      <td className={`py-1.5 text-right font-bold font-mono ${
                        t.pnl === null ? 'text-gray-600' :
                        t.pnl >= 0 ? 'text-bull' : 'text-bear'
                      }`}>
                        {t.pnl !== null ? `${t.pnl >= 0 ? '+' : ''}$${Math.abs(t.pnl).toFixed(2)}` : '—'}
                      </td>
                    </tr>
                    {/* Reasoning tooltip row */}
                    <tr className="border-b border-white/[0.03]">
                      <td colSpan={7} className="pb-1.5 text-[10px] text-gray-700 italic pl-1">
                        {t.reasoning}
                        {t.exit_btc && (
                          <span className="ml-2 not-italic text-gray-600">
                            exit ${fmt(t.exit_btc)}
                          </span>
                        )}
                      </td>
                    </tr>
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Stats footer */}
      {resolved.length > 0 && (
        <div className="mt-3 pt-3 border-t border-white/[0.05] flex justify-between text-[10px] text-gray-600">
          <span>{resolved.length} resolved · {pending.length} open</span>
          <span>
            Avg win ${(resolved.filter(t=>t.result==='WIN').reduce((s,t)=>s+(t.pnl??0),0)/(wins.length||1)).toFixed(2)} ·
            Avg loss ${ Math.abs(resolved.filter(t=>t.result==='LOSS').reduce((s,t)=>s+(t.pnl??0),0)/(Math.max(1,resolved.length-wins.length))).toFixed(2)}
          </span>
        </div>
      )}
    </Card>
  );
}

// ─── Log Panel ────────────────────────────────────────────────────────────────

const LOG_COLORS: Record<LogLine['tag'], string> = {
  error:     'text-bear',
  success:   'text-bull',
  warn:      'text-warn',
  highlight: 'text-blue-400',
  signal:    'text-purple-400',
  info:      'text-gray-500',
};

function LogPanel({ lines, connected }: { lines: LogLine[]; connected: boolean }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [lines]);

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          BOT LOGS · LIVE STREAM
          {connected
            ? <span className="w-1.5 h-1.5 rounded-full bg-bull animate-pulse-fast inline-block" />
            : <span className="w-1.5 h-1.5 rounded-full bg-gray-700 inline-block" />}
        </span>
      }
    >
      <div className="bg-black/40 rounded-lg p-3 h-56 overflow-y-auto font-mono text-[10px] leading-relaxed">
        {lines.length === 0 ? (
          <span className="text-gray-700">
            {connected ? 'No log output yet…' : 'Bot offline — no logs available'}
          </span>
        ) : (
          lines.map((l, i) => (
            <div key={i} className={`${LOG_COLORS[l.tag]} whitespace-pre-wrap break-all`}>
              {l.text}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
      <div className="mt-2 flex gap-3 text-[9px] text-gray-700 flex-wrap">
        {[
          { tag: 'error',     label: 'Error',   color: 'bg-bear' },
          { tag: 'success',   label: 'Success',  color: 'bg-bull' },
          { tag: 'warn',      label: 'No trade', color: 'bg-warn' },
          { tag: 'highlight', label: 'Fire/Market', color: 'bg-blue-400' },
          { tag: 'signal',    label: 'Signals',  color: 'bg-purple-400' },
        ].map(({ label, color }) => (
          <span key={label} className="flex items-center gap-1">
            <span className={`w-1.5 h-1.5 rounded-full ${color} inline-block`} />
            {label}
          </span>
        ))}
      </div>
    </Card>
  );
}

// ─── Skip Logs Panel ─────────────────────────────────────────────────────────

function SkipLogsPanel({ skips, highconf }: { skips: SkipEntry[]; highconf: SkipEntry[] }) {
  const [tab, setTab] = React.useState<'low' | 'high'>('low');
  const entries = tab === 'low' ? [...skips].reverse() : [...highconf].reverse();

  const resolved = entries.filter(e => e.would_have_won !== null);
  const wins     = resolved.filter(e => e.would_have_won === true);
  const winRate  = resolved.length ? (wins.length / resolved.length * 100) : null;
  const avgConf  = entries.length ? entries.reduce((s, e) => s + e.confidence, 0) / entries.length : null;

  return (
    <Card
      title={
        <span className="flex items-center gap-3">
          <span>SIGNAL SKIPS</span>
          <span className="flex gap-1">
            {(['low', 'high'] as const).map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-2 py-0.5 rounded text-[9px] uppercase tracking-wider border transition-colors ${
                  tab === t
                    ? 'border-blue-400/40 text-blue-400 bg-blue-400/10'
                    : 'border-white/10 text-gray-600 bg-transparent hover:border-white/20'
                }`}
              >
                {t === 'low' ? `Low Conf <0.63` : `High Conf (hist.)`}
              </button>
            ))}
          </span>
        </span>
      }
    >
      {/* Summary stats */}
      <div className="grid grid-cols-4 gap-2 mb-4">
        {[
          { label: 'Total',    val: entries.length.toString(),                                           color: 'text-gray-400' },
          { label: 'Resolved', val: resolved.length.toString(),                                          color: 'text-gray-400' },
          { label: 'Win Rate', val: winRate !== null ? `${winRate.toFixed(0)}%` : '—',                   color: winRate !== null && winRate >= 55 ? 'text-bull' : winRate !== null ? 'text-bear' : 'text-gray-600' },
          { label: 'Avg Conf', val: avgConf !== null ? `${(avgConf * 100).toFixed(1)}%` : '—',           color: 'text-gray-400' },
        ].map(s => (
          <div key={s.label} className="bg-white/[0.03] rounded-lg p-2 text-center">
            <div className="text-[9px] text-gray-600 uppercase tracking-wider mb-1">{s.label}</div>
            <div className={`text-[14px] font-bold font-mono ${s.color}`}>{s.val}</div>
          </div>
        ))}
      </div>

      {entries.length === 0 ? (
        <p className="text-[12px] text-gray-600 text-center py-4">No entries yet</p>
      ) : (
        <div className="overflow-auto max-h-72">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-gray-600 border-b border-white/[0.05]">
                <th className="text-left pb-1.5 font-normal">Time</th>
                <th className="text-left pb-1.5 font-normal">Dir</th>
                <th className="text-right pb-1.5 font-normal">Conf</th>
                <th className="text-right pb-1.5 font-normal">Entry</th>
                <th className="text-right pb-1.5 font-normal">Exit</th>
                <th className="text-right pb-1.5 font-normal">Would've Won</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(e => (
                <React.Fragment key={e.id}>
                  <tr className="border-b border-white/[0.03] hover:bg-white/[0.02]">
                    <td className="py-1.5 text-gray-500">
                      {new Date(e.timestamp).toLocaleString('en-US', {
                        month: 'numeric', day: 'numeric',
                        hour: '2-digit', minute: '2-digit', hour12: false,
                      })}
                    </td>
                    <td className={`py-1.5 font-bold ${e.direction === 'BULL' ? 'text-bull' : 'text-bear'}`}>
                      {e.direction === 'BULL' ? '▲' : '▼'} {e.direction}
                    </td>
                    <td className="py-1.5 text-right font-mono text-gray-400">
                      {(e.confidence * 100).toFixed(0)}%
                    </td>
                    <td className="py-1.5 text-right text-gray-500 font-mono">${fmt(e.entry_btc)}</td>
                    <td className="py-1.5 text-right text-gray-600 font-mono">
                      {e.exit_btc ? `$${fmt(e.exit_btc)}` : '—'}
                    </td>
                    <td className={`py-1.5 text-right font-bold ${
                      e.would_have_won === null  ? 'text-gray-600' :
                      e.would_have_won === true  ? 'text-bull' : 'text-bear'
                    }`}>
                      {e.would_have_won === null ? 'OPEN' : e.would_have_won ? 'YES ✓' : 'NO ✗'}
                    </td>
                  </tr>
                  <tr className="border-b border-white/[0.03]">
                    <td colSpan={6} className="pb-1.5 text-[10px] text-gray-700 italic pl-1">
                      {e.reasoning}
                    </td>
                  </tr>
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ─── main Dashboard ───────────────────────────────────────────────────────────

export default function Dashboard() {
  const simRef  = useRef<PriceSimulator | null>(null);
  const claudeThrottleRef = useRef(0);

  // Simulation state
  const [chartData, setChartData] = useState<{ t: string; p: number }[]>([]);
  const [price, setPrice]   = useState(0);
  const [delta, setDelta]   = useState(0);
  const [markov, setMarkov] = useState<MarkovResult | null>(null);
  const [mc, setMC]         = useState<MCResult | null>(null);
  const [smc, setSMC]       = useState<SMCResult | null>(null);
  const [claude, setClaude] = useState<ClaudeDecision>({
    direction: 'NO_TRADE', confidence: 0, reasoning: 'Waiting for signal convergence…', loading: false,
  });
  const [convergeFire, setConvergeFire] = useState(false);
  const [tick, setTick] = useState(0);

  // Live paper trades state
  const [ledger, setLedger]           = useState<Ledger>({ initial: 20, balance: 20, trades: [] });
  const [botConnected, setBotConnected] = useState(false);
  const [lastFetched, setLastFetched]   = useState<Date | null>(null);

  // Real BTC price from bot
  const [realPrice, setRealPrice] = useState<number | null>(null);

  // Live log state
  const [logLines, setLogLines] = useState<LogLine[]>([]);

  // Skip logs state
  const [skips, setSkips]       = useState<SkipEntry[]>([]);
  const [highconf, setHighconf]  = useState<SkipEntry[]>([]);

  useEffect(() => { simRef.current = new PriceSimulator(); }, []);

  // ── Live trades polling ──────────────────────────────────────────────────
  const fetchTrades = useCallback(async () => {
    try {
      const res = await fetch('/api/trades', { cache: 'no-store' });
      const data: Ledger = await res.json();
      setLedger(data);
      setBotConnected(true);
      setLastFetched(new Date());
    } catch {
      setBotConnected(false);
    }
  }, []);

  useEffect(() => {
    fetchTrades();
    const id = setInterval(fetchTrades, 30_000);
    return () => clearInterval(id);
  }, [fetchTrades]);

  // ── Real price polling every 5s ─────────────────────────────────────────
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch('/api/status', { cache: 'no-store' });
        const data = await res.json();
        if (data.last_price) setRealPrice(data.last_price);
      } catch { /* bot offline */ }
    };
    fetchStatus();
    const id = setInterval(fetchStatus, 5_000);
    return () => clearInterval(id);
  }, []);

  // ── Log polling every 5s ─────────────────────────────────────────────────
  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const res = await fetch('/api/logs?n=150', { cache: 'no-store' });
        const data = await res.json();
        if (data.lines?.length) setLogLines(data.lines);
      } catch { /* bot offline */ }
    };
    fetchLogs();
    const id = setInterval(fetchLogs, 5_000);
    return () => clearInterval(id);
  }, []);

  // ── Skip logs polling every 30s ──────────────────────────────────────────
  useEffect(() => {
    const fetchSkips = async () => {
      try {
        const [sr, hr] = await Promise.all([
          fetch('/api/skips',    { cache: 'no-store' }),
          fetch('/api/highconf', { cache: 'no-store' }),
        ]);
        setSkips(await sr.json());
        setHighconf(await hr.json());
      } catch { /* bot offline */ }
    };
    fetchSkips();
    const id = setInterval(fetchSkips, 30_000);
    return () => clearInterval(id);
  }, []);

  // ── Claude query ─────────────────────────────────────────────────────────
  const askClaude = useCallback(async (
    m: MarkovResult, mc_: MCResult, s: SMCResult, p: number
  ) => {
    if (Date.now() - claudeThrottleRef.current < 15_000) return;
    claudeThrottleRef.current = Date.now();
    setClaude(prev => ({ ...prev, loading: true }));
    try {
      const res = await fetch('/api/hermes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ markov: m, mc: mc_, smc: s, btcPrice: p, yesPrice: mc_.bullProb.toFixed(3) }),
      });
      const data = await res.json();
      setClaude({ direction: data.direction, confidence: data.confidence, reasoning: data.reasoning, loading: false });
      if (data.direction !== 'NO_TRADE' && data.confidence >= 0.65) {
        setConvergeFire(true);
        setTimeout(() => setConvergeFire(false), 2000);
      }
    } catch {
      setClaude(prev => ({ ...prev, loading: false }));
    }
  }, []);

  // ── Simulation tick ──────────────────────────────────────────────────────
  useEffect(() => {
    const id = setInterval(() => {
      const sim = simRef.current;
      if (!sim) return;
      sim.tick();
      const bars   = sim.getBars();
      const prices = sim.getPrices();
      const cur    = sim.getPrice();

      setChartData(bars.slice(-60).map((b, i) => ({
        t: i % 10 === 0 ? new Date(b.timestamp).toLocaleTimeString('en-US', { hour12: false }) : '',
        p: +b.close.toFixed(0),
      })));
      setPrice(cur);
      if (prices.length > 1) setDelta((cur - prices[0]) / prices[0] * 100);

      const m   = computeMarkov(prices);
      const mc_ = runMonteCarlo(m.matrix, m.currentState);
      const s   = computeSMC(bars);
      setMarkov(m); setMC(mc_); setSMC(s);
      setTick(t => t + 1);

      const sigs  = [m.signal, mc_.signal, s.signal];
      const bulls = sigs.filter(v => v === 'BULL').length;
      const bears = sigs.filter(v => v === 'BEAR').length;
      if (bulls >= 2 || bears >= 2) askClaude(m, mc_, s, cur);
    }, 2000);
    return () => clearInterval(id);
  }, [askClaude]);

  // ── derived ──────────────────────────────────────────────────────────────
  const allConverge = markov && mc && smc && claude.direction !== 'NO_TRADE' && claude.confidence >= 0.65;
  const priceUp     = delta >= 0;
  const chartColor  = priceUp ? '#00d987' : '#ff3c5a';

  const mcBars = mc ? [
    { name: 'BULL', value: +(mc.bullProb * 100).toFixed(1), fill: '#00d987' },
    { name: 'BEAR', value: +(mc.bearProb * 100).toFixed(1), fill: '#ff3c5a' },
  ] : [];

  const mCells = markov ? [
    { label: 'B→B', val: markov.matrix[0][0], dir: 'BEAR' },
    { label: 'B→U', val: markov.matrix[0][1], dir: 'BULL' },
    { label: 'U→B', val: markov.matrix[1][0], dir: 'BEAR' },
    { label: 'U→U', val: markov.matrix[1][1], dir: 'BULL' },
  ] : [];

  return (
    <div className="min-h-screen bg-[#060608] text-gray-200 font-mono p-4 flex flex-col gap-4">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between border-b border-white/[0.06] pb-3">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-bull animate-pulse-fast" />
          <span className="text-[11px] text-gray-500 tracking-widest uppercase">Hermes · BTC/USDT</span>
        </div>
        <div className="flex items-center gap-5">
          <span className="text-[11px] text-gray-500">{now()} UTC</span>
          {/* Bot connection badge */}
          <span className={`text-[11px] px-2 py-0.5 rounded border font-bold ${
            botConnected
              ? 'border-bull/30 text-bull bg-bull/5'
              : 'border-white/10 text-gray-600 bg-white/[0.02]'
          }`}>
            {botConnected ? '⬤ Bot live' : '◯ Bot offline'}
          </span>
          <span className={`text-[11px] font-bold ${ledger.balance >= ledger.initial ? 'text-bull' : 'text-bear'}`}>
            Paper: ${ledger.balance.toFixed(2)}
          </span>
        </div>
      </div>

      {/* ── Price ticker ───────────────────────────────────────────────────── */}
      <div className="flex items-end gap-4 flex-wrap">
        {/* Real price from Binance via bot */}
        {realPrice ? (
          <div className="flex items-end gap-3">
            <span className="text-4xl font-bold tracking-tight text-bull">
              ${fmt(realPrice)}
            </span>
            <span className="text-[11px] text-bull/60 mb-1.5 px-1.5 py-0.5 rounded border border-bull/20 bg-bull/5">
              LIVE · Binance
            </span>
          </div>
        ) : (
          <div className="flex items-end gap-3">
            <span className={`text-4xl font-bold tracking-tight ${priceUp ? 'text-bull' : 'text-bear'}`}>
              ${fmt(price)}
            </span>
            <span className={`text-lg mb-1 ${priceUp ? 'text-bull' : 'text-bear'}`}>
              {priceUp ? '▲' : '▼'} {Math.abs(delta).toFixed(3)}%
            </span>
            <span className="text-[10px] text-gray-600 mb-1.5 px-1.5 py-0.5 rounded border border-white/10">
              sim · tick #{tick}
            </span>
          </div>
        )}
      </div>

      {/* ── Main grid ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 flex-1">

        {/* ── Left column ────────────────────────────────────────────────── */}
        <div className="xl:col-span-2 flex flex-col gap-4">

          {/* Price chart */}
          <Card title="BTC/USDT · 2-second sim bars">
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={chartData} margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
                <defs>
                  <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor={chartColor} stopOpacity={0.18} />
                    <stop offset="95%" stopColor={chartColor} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="t" tick={{ fill: '#555', fontSize: 10 }} tickLine={false} axisLine={false} />
                <YAxis domain={['auto','auto']} tick={{ fill: '#555', fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={v=>`$${(v/1000).toFixed(1)}k`} width={52} />
                <Tooltip contentStyle={{ background: '#111', border: '1px solid #222', borderRadius: 8, fontSize: 12 }} labelStyle={{ color: '#888' }} formatter={(v: number) => [`$${fmt(v)}`, 'BTC']} />
                <Area type="monotone" dataKey="p" stroke={chartColor} strokeWidth={1.5} fill="url(#priceGrad)" dot={false} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </Card>

          {/* Monte Carlo */}
          <Card title={`Monte Carlo · 500 paths × 10 steps`} glow={mc?.signal as 'bull'|'bear'|null}>
            <div className="flex items-center gap-4 mb-3">
              <Badge sig={mc?.signal ?? null} />
              {mc && (
                <span className="text-[12px] text-gray-500">
                  Bull: <span className="text-bull">{pct(mc.bullProb)}</span>
                  {'  '}Bear: <span className="text-bear">{pct(mc.bearProb)}</span>
                </span>
              )}
            </div>
            {mc && (
              <div className="relative h-4 rounded-full overflow-hidden bg-white/5 mb-4">
                <div className="absolute left-0 top-0 h-full bg-bull/70 transition-all duration-500" style={{ width: pct(mc.bullProb) }} />
                <div className="absolute right-0 top-0 h-full bg-bear/70 transition-all duration-500" style={{ width: pct(mc.bearProb) }} />
              </div>
            )}
            <ResponsiveContainer width="100%" height={100}>
              <BarChart data={mcBars} barCategoryGap="30%">
                <XAxis dataKey="name" tick={{ fill: '#555', fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis domain={[0,100]} tick={{ fill: '#555', fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={v=>`${v}%`} width={34} />
                <Tooltip contentStyle={{ background: '#111', border: '1px solid #222', borderRadius: 8, fontSize: 12 }} formatter={(v: number) => [`${v}%`]} />
                <Bar dataKey="value" radius={[4,4,0,0]} isAnimationActive={false}>
                  {mcBars.map((entry, i) => <Cell key={i} fill={entry.fill} fillOpacity={0.8} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>

          {/* ── REAL paper trades from Python bot ── */}
          <PaperTradesPanel
            ledger={ledger}
            connected={botConnected}
            lastFetched={lastFetched}
          />

          {/* ── Live log stream ── */}
          <LogPanel lines={logLines} connected={botConnected} />

          {/* ── Signal skip logs ── */}
          <SkipLogsPanel skips={skips} highconf={highconf} />

        </div>

        {/* ── Right column: signals ──────────────────────────────────────── */}
        <div className="flex flex-col gap-4">

          {/* Markov */}
          <Card title={`Markov chain · ${markov?.nSamples ?? 0} samples`} glow={markov?.signal as 'bull'|'bear'|null}>
            <div className="flex items-center justify-between mb-3">
              <Badge sig={markov?.signal ?? null} />
              <span className="text-[11px] text-gray-600">
                State: <span className={markov?.currentState === 1 ? 'text-bull' : 'text-bear'}>
                  {markov?.currentState === 1 ? 'BULL' : 'BEAR'}
                </span>
              </span>
            </div>
            <div className="grid grid-cols-2 gap-1.5 mb-3">
              {mCells.map(cell => (
                <div key={cell.label} className={`rounded-lg p-2.5 text-center border ${cell.dir === 'BULL' ? 'border-bull/20' : 'border-bear/20'}`}
                  style={{ background: cell.dir === 'BULL' ? `rgba(0,217,135,${cell.val*0.18})` : `rgba(255,60,90,${cell.val*0.18})` }}>
                  <div className="text-[9px] text-gray-600 mb-0.5">{cell.label}</div>
                  <div className={`text-[15px] font-bold ${cell.dir === 'BULL' ? 'text-bull' : 'text-bear'}`}>{(cell.val*100).toFixed(0)}%</div>
                </div>
              ))}
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-gray-600">Bull persist.</span>
              <span className={markov && markov.bullPersistence >= 0.87 ? 'text-bull font-bold' : 'text-gray-400'}>
                {markov ? pct(markov.bullPersistence) : '—'}{markov && markov.bullPersistence >= 0.87 && ' ✓'}
              </span>
            </div>
            <div className="flex justify-between text-[11px] mt-1">
              <span className="text-gray-600">Bear persist.</span>
              <span className={markov && markov.bearPersistence >= 0.87 ? 'text-bear font-bold' : 'text-gray-400'}>
                {markov ? pct(markov.bearPersistence) : '—'}{markov && markov.bearPersistence >= 0.87 && ' ✓'}
              </span>
            </div>
          </Card>

          {/* SMC */}
          <Card title="Smart money concepts" glow={smc?.signal as 'bull'|'bear'|null}>
            <div className="flex items-center justify-between mb-3">
              <Badge sig={smc?.signal ?? null} />
              <span className="text-[11px] text-gray-600">{smc?.patternsFound ?? 0}/3 active</span>
            </div>
            <div className="space-y-2">
              {[
                { label: 'Break of Structure', val: smc?.bos },
                { label: 'Liquidity Sweep',    val: smc?.liquiditySweep },
                { label: 'Fair Value Gap',      val: smc?.fvg },
              ].map(row => (
                <div key={row.label} className="flex items-center justify-between">
                  <span className="text-[11px] text-gray-500">{row.label}</span>
                  <Badge sig={row.val ?? null} />
                </div>
              ))}
            </div>
          </Card>

          {/* Claude */}
          <Card title="Claude Opus · Brain" glow={claude.direction === 'BULL' ? 'bull' : claude.direction === 'BEAR' ? 'bear' : null}>
            <div className="flex items-center justify-between mb-3">
              {claude.loading
                ? <span className="text-[12px] text-warn animate-pulse">Thinking…</span>
                : <Badge sig={claude.direction === 'NO_TRADE' ? null : claude.direction} />
              }
              {!claude.loading && claude.direction !== 'NO_TRADE' && (
                <span className={`text-[13px] font-bold ${claude.confidence >= 0.72 ? 'text-bull' : 'text-warn'}`}>
                  {pct(claude.confidence)}
                </span>
              )}
            </div>
            {!claude.loading && claude.confidence > 0 && (
              <div className="h-1.5 bg-white/5 rounded-full mb-3 overflow-hidden">
                <div className={`h-full rounded-full transition-all duration-700 ${claude.direction === 'BULL' ? 'bg-bull' : 'bg-bear'}`}
                  style={{ width: pct(claude.confidence) }} />
              </div>
            )}
            <p className="text-[11px] text-gray-500 leading-relaxed">{claude.reasoning}</p>
          </Card>

          {/* Convergence gate */}
          <div className={`rounded-xl border p-4 transition-all duration-500 ${
            allConverge
              ? `border-warn/40 bg-warn/5 ${convergeFire ? 'animate-fire' : ''}`
              : 'border-white/[0.06] bg-[#0d0d11]'
          }`}>
            <p className="text-[10px] uppercase tracking-[0.2em] text-gray-600 mb-3 font-mono">Convergence gate</p>
            <div className="grid grid-cols-2 gap-2">
              {[
                { label: 'Markov', sig: markov?.signal },
                { label: 'MC',     sig: mc?.signal },
                { label: 'SMC',    sig: smc?.signal },
                { label: 'Claude', sig: claude.direction === 'NO_TRADE' ? null : claude.direction },
              ].map(row => (
                <div key={row.label} className="flex items-center justify-between bg-white/[0.03] rounded-lg px-2.5 py-2">
                  <span className="text-[10px] text-gray-600">{row.label}</span>
                  <span className={`text-[10px] font-bold ${sigColor(row.sig ?? null)}`}>{row.sig ?? '—'}</span>
                </div>
              ))}
            </div>
            <div className={`mt-3 text-center text-[12px] font-bold tracking-widest ${allConverge ? 'text-warn' : 'text-gray-700'}`}>
              {allConverge ? `🔥 FIRE — ${claude.direction}` : 'WAITING FOR CONVERGENCE'}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
