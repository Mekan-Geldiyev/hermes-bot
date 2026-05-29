"""
2-state Markov chain over discretised BTC price returns.
States: BEAR=0, BULL=1
"""
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class MarkovResult:
    transition_matrix: np.ndarray   # shape (2,2)
    current_state: int               # 0=BEAR 1=BULL
    persistence: float               # T[current_state][current_state]
    bull_persistence: float          # T[1][1]
    bear_persistence: float          # T[0][0]
    signal: Optional[str]            # "BULL" | "BEAR" | None
    n_samples: int


def classify_returns(prices: list[float], threshold_pct: float = 0.0) -> list[int]:
    """Convert price series to binary state sequence (0=BEAR, 1=BULL)."""
    states = []
    for i in range(1, len(prices)):
        ret = (prices[i] - prices[i-1]) / prices[i-1]
        states.append(1 if ret > threshold_pct else 0)
    return states


def build_transition_matrix(states: list[int]) -> np.ndarray:
    T = np.zeros((2, 2), dtype=float)
    for i in range(len(states) - 1):
        T[states[i]][states[i+1]] += 1.0
    row_sums = T.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    return T / row_sums


def compute_markov(prices: list[float], persistence_threshold: float = 0.87) -> MarkovResult:
    if len(prices) < 10:
        T = np.full((2, 2), 0.5)
        return MarkovResult(T, 1, 0.5, 0.5, 0.5, None, len(prices))

    states = classify_returns(prices)
    T = build_transition_matrix(states)
    current_state = states[-1]
    persistence = T[current_state][current_state]

    signal = None
    if T[1][1] >= persistence_threshold:
        signal = "BULL"
    elif T[0][0] >= persistence_threshold:
        signal = "BEAR"

    return MarkovResult(
        transition_matrix=T,
        current_state=current_state,
        persistence=persistence,
        bull_persistence=float(T[1][1]),
        bear_persistence=float(T[0][0]),
        signal=signal,
        n_samples=len(states),
    )
