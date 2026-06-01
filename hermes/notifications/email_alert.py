"""
Email alerts via Gmail SMTP.

Required .env vars:
  EMAIL_FROM         your Gmail address  (e.g. you@gmail.com)
  EMAIL_APP_PASSWORD 16-char app password from Google Account → Security → App passwords
  EMAIL_TO           recipient (e.g. nightgtwolf@gmail.com)
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from hermes.config import EMAIL_FROM, EMAIL_APP_PASSWORD, EMAIL_TO


def _send(subject: str, body: str) -> None:
    if not EMAIL_FROM or not EMAIL_APP_PASSWORD or not EMAIL_TO:
        print("[Email] Skipped — EMAIL_FROM / EMAIL_APP_PASSWORD / EMAIL_TO not set")
        return
    try:
        msg = MIMEMultipart()
        msg["From"]    = EMAIL_FROM
        msg["To"]      = EMAIL_TO
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(EMAIL_FROM, EMAIL_APP_PASSWORD)
            server.send_message(msg)
        print(f"[Email] Sent '{subject}' → {EMAIL_TO}")
    except Exception as e:
        print(f"[Email] Failed: {e}")


def send_trade_alert(
    direction: str,
    market: str,
    size_usdc: float,
    price: float,
    confidence: float,
    reasoning: str,
    balance: float,
) -> None:
    arrow  = "▲" if direction == "BULL" else "▼"
    shares = size_usdc / price if price > 0 else 0
    win_payout = shares - size_usdc

    subject = f"🔥 Hermes Paper Trade: {arrow} {direction} BTC"
    body = f"""Hermes just logged a paper trade.

Direction  : {direction} {arrow}
Market     : {market}
Odds       : {price:.3f}  ({price*100:.1f}¢ per share)
Size       : ${size_usdc:.2f} USDC
Confidence : {confidence:.0%}
Balance    : ${balance:.2f}

Claude's reasoning:
  {reasoning}

─────────────────────────────────
If this were a real trade:
  Shares bought : {shares:.1f} shares at {price:.3f}
  WIN payout    : ${shares:.2f}  (profit +${win_payout:.2f})
  LOSS cost     : -${size_usdc:.2f}
─────────────────────────────────
"""
    _send(subject, body)


def send_resolve_alert(
    direction: str,
    result: str,
    entry_btc: float,
    exit_btc: float,
    pnl: float,
    balance: float,
    market: str,
) -> None:
    icon = "✅" if result == "WIN" else "❌"
    pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"

    subject = f"{icon} Hermes Trade Resolved: {result}"
    body = f"""A paper trade just resolved.

Result     : {result} {icon}
Direction  : {direction}
Market     : {market}
Entry BTC  : ${entry_btc:,.0f}
Exit BTC   : ${exit_btc:,.0f}
P&L        : {pnl_str}
New balance: ${balance:.2f}
"""
    _send(subject, body)
