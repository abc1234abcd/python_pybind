#cython: language_level=3
import numpy as np
cimport numpy as np
from libc.math cimport fabs

def calculate_rsi(np.float32_t[:] prices, int window):
    cdef:
        np.float32_t[:] deltas = np.zeros(len(prices)-1, dtype=np.float32)
        np.float32_t avg_gain = 0.0
        np.float32_t avg_loss = 1e-10  # Avoid division by zero
        int i, n = len(prices)
        np.float32_t current_delta
        np.float32_t rs, rsi
    # price deltas
    for i in range(1, n):
        deltas[i-1] = prices[i] - prices[i-1]
    # Initial average gain/loss (first 'window' periods)
    cdef:
        np.float32_t sum_gain = 0.0
        np.float32_t sum_loss = 0.0
        int count_gain = 0
        int count_loss = 0
    for i in range(window):
        current_delta = deltas[i]
        if current_delta > 0:
            sum_gain += current_delta
            count_gain += 1
        else:
            sum_loss += fabs(current_delta)
            count_loss += 1
    avg_gain = sum_gain / window if count_gain > 0 else 0.0
    avg_loss = sum_loss / window if count_loss > 0 else 1e-10
    # Exponential moving average updates
    for i in range(window, n-1):
        current_delta = deltas[i]
        
        if current_delta > 0:
            avg_gain = (avg_gain * (window - 1) + current_delta) / window
            avg_loss = (avg_loss * (window - 1)) / window
        else:
            avg_gain = (avg_gain * (window - 1)) / window
            avg_loss = (avg_loss * (window - 1) + fabs(current_delta)) / window
        
        rs = avg_gain / max(avg_loss, 1e-10)
        rsi = 100 - (100 / (1 + rs))
    return rsi