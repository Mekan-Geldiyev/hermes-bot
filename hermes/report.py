"""
Paper trading report.

Usage:
    python -m hermes.report
"""
import json
import os
import sys
from datetime import datetime, timezone

LEDGER_PATH = os.path.join(os.path.dirname(__file__), "paper_trades.json")

BULL = "\033[92m"   # green
BEAR = "\033[91m"   # red
WARN = "\033[93m"   # yellow
DIM  = "\033[90m"   # grey
BOLD = "\033[1m"
RST  = "\033[0m"


def _clr(text: str, color: str) -> str:
    return f"{color}{text}{RST}"


def main():
    if not os.path.exists(LEDGER_PATH):
        print("No paper trades found. Run:  python -m hermes.main")
        sys.exit(0)

    with open(LEDGER_PATH) as f:
        ledger = json.load(f)

    trades   = ledger.get("trades", [])
    initial  = ledger.get("initial", 20.0)
    balance  = ledger.get("balance", initial)

    resolved = [t for t in trades if t["result"] is not None]
    pending  = [t for t in trades if t["result"] is None]
    wins     = [t for t in resolved if t["result"] == "WIN"]
    losses   = [t for t in resolved if t["result"] == "LOSS"]

    total_pnl = sum(t["pnl"] for t in resolved)
    win_rate  = len(wins) / len(resolved) * 100 if resolved else 0.0
    roi       = (balance - initial) / initial * 100

    W = 68
    SEP  = "═" * W
    sep  = "─" * W

    print(f"\n{_clr(SEP, BOLD)}")
    print(f"  {_clr('HERMES PAPER TRADING REPORT', BOLD)}")
    print(f"{_clr(SEP, BOLD)}")
    print(f"  Initial account  :  ${initial:.2f}")

    bal_color = BULL if balance >= initial else BEAR
    roi_str   = f"{'+'if roi>=0 else ''}{roi:.1f}%"
    print(f"  Current balance  :  {_clr(f'${balance:.2f}', bal_color)}  {_clr(f'({roi_str})', bal_color)}")
    print()
    print(f"  Total trades     :  {len(trades)}  "
          f"({_clr(str(len(wins)) + 'W', BULL)} / {_clr(str(len(losses)) + 'L', BEAR)} / "
          f"{_clr(str(len(pending)) + ' open', WARN)})")

    if resolved:
        wr_color = BULL if win_rate >= 55 else (WARN if win_rate >= 45 else BEAR)
        print(f"  Win rate         :  {_clr(f'{win_rate:.0f}%', wr_color)}")
        pnl_color = BULL if total_pnl >= 0 else BEAR
        pnl_str   = f"{'+'if total_pnl>=0 else ''}${total_pnl:.2f}"
        print(f"  Net P&L          :  {_clr(pnl_str, pnl_color)}")

    if not trades:
        print(f"\n  {_clr('No trades logged yet.', DIM)}")
        print(f"{_clr(SEP, BOLD)}\n")
        return

    print(f"\n  {_clr('TRADE LOG', BOLD)}")
    print(f"  {sep}")

    # header
    print(
        f"  {'#':>2}  {'Time':17}  {'Dir':9}  "
        f"{'Entry BTC':>10}  {'Odds':5}  {'Size':6}  "
        f"{'Conf':5}  {'Result':7}  {'P&L':>8}"
    )
    print(f"  {sep}")

    for i, t in enumerate(trades, 1):
        try:
            ts = datetime.fromisoformat(t["timestamp"].replace("Z", "+00:00"))
            time_str = ts.strftime("%b %d %H:%M UTC")
        except Exception:
            time_str = t.get("timestamp", "")[:16]

        direction = t["direction"]
        price     = t["yes_price"] if direction == "BULL" else t["no_price"]
        dir_str   = (f"{_clr('▲ BULL', BULL)}" if direction == "BULL"
                     else f"{_clr('▼ BEAR', BEAR)}")

        result = t.get("result")
        if result == "WIN":
            result_str = _clr("WIN  ✓", BULL)
        elif result == "LOSS":
            result_str = _clr("LOSS ✗", BEAR)
        else:
            result_str = _clr("OPEN …", WARN)

        pnl = t.get("pnl")
        if pnl is not None:
            pnl_color = BULL if pnl >= 0 else BEAR
            pnl_str   = _clr(f"{'+'if pnl>=0 else ''}${pnl:.2f}", pnl_color)
        else:
            pnl_str = _clr("—", DIM)

        print(
            f"  {i:>2}  {time_str:17}  {dir_str:9}  "
            f"${t['entry_btc']:>10,.0f}  {price:.3f}  ${t['size_usdc']:.2f}  "
            f"{t['confidence']:.0%}   {result_str:7}  {pnl_str:>8}"
        )

        # indent reasoning
        reasoning = t.get("reasoning", "")
        if reasoning:
            print(f"        {_clr(reasoning[:72], DIM)}")

    print(f"  {sep}")

    # expected value summary
    if resolved:
        avg_win  = sum(t["pnl"] for t in wins)  / len(wins)  if wins   else 0
        avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
        ev = (win_rate/100) * avg_win + (1 - win_rate/100) * avg_loss
        ev_color = BULL if ev >= 0 else BEAR
        print(f"\n  Avg win:  ${avg_win:.2f}   Avg loss: ${avg_loss:.2f}   "
              f"EV per trade: {_clr(f'${ev:.2f}', ev_color)}")

    print(f"{_clr(SEP, BOLD)}\n")


if __name__ == "__main__":
    main()
