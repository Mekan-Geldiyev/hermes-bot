import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Hermes · BTC Prediction Engine',
  description: 'Markov + Monte Carlo + SMC + Claude — Polymarket BTC Up/Down simulation',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
