"""
Monte Carlo path simulation over the Markov transition matrix.
Fires 500 paths N steps forward and returns directional probabilities.
"""
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class MCResult:
    bull_prob: float
    bear_prob: float
    signal: Optional[str]    # "BULL" | "BEAR" | None
    n_paths: int
    n_steps: int


def run_monte_carlo(
    transition_matrix: np.ndarray,
    current_state: int,
    n_paths: int = 500,
    n_steps: int = 10,
    edge_threshold: float = 0.52,
) -> MCResult:
    """
    Simulate n_paths Markov chains of n_steps from current_state.
    Returns fraction of paths ending in each state.
    """
    rng = np.random.default_rng()

    # Vectorised: shape (n_paths,) state array
    states = np.full(n_paths, current_state, dtype=np.int32)
    T = transition_matrix

    for _ in range(n_steps):
        # For each path, draw next state from T[current_state]
        rand = rng.random(n_paths)
        # BULL transition probability for each path's current state
        bull_prob_vec = T[states, 1]  # T[state][BULL]
        states = np.where(rand < bull_prob_vec, 1, 0)

    bull_prob = float(np.mean(states == 1))
    bear_prob = 1.0 - bull_prob

    signal = None
    if bull_prob >= edge_threshold:
        signal = "BULL"
    elif bear_prob >= edge_threshold:
        signal = "BEAR"

    return MCResult(
        bull_prob=bull_prob,
        bear_prob=bear_prob,
        signal=signal,
        n_paths=n_paths,
        n_steps=n_steps,
    )
