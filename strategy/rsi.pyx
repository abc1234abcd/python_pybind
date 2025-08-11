
import numpy as np
cimport numpy as np
from libc.math cimport fabs


cdef class RSICalculator:
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
        np.float32_t[:] price_buffer
        int window
        int buffer_size
        int current_pos
        np.float32_t avg_gain
        np.float32_t avg_loss
        bint initialized
    
    def __cinit__(self, int window):
        self.window = window
        self.buffer_size = window + 1
        self.price_buffer = np.zeros(self.buffer_size, dtype=np.float32)
        self.current_pos = 0
        self.avg_gain = 0.0
        self.avg_loss = 1e-10
        self.initialized = False
    
    cpdef update(self, np.float32_t new_price):
        # Update circular buffer
        self.price_buffer[self.current_pos] = new_price
        self.current_pos = (self.current_pos + 1) % self.buffer_size
        
        # Need window+1 prices to calculate window deltas
        if self.current_pos < self.window and not self.initialized:
            return float('nan')
        
        # Get the most recent window+1 prices
        cdef np.float32_t[:] window_prices = np.zeros(self.window + 1, dtype=np.float32)
        cdef int start_idx = (self.current_pos - self.window - 1) % self.buffer_size
        cdef int i
        for i in range(self.window + 1):
            window_prices[i] = self.price_buffer[(start_idx + i) % self.buffer_size]
        
        # Calculate price deltas
        cdef np.float32_t[:] deltas = np.zeros(self.window, dtype=np.float32)
        cdef np.float32_t sum_gain = 0.0
        cdef np.float32_t sum_loss = 0.0
        cdef np.float32_t current_delta
        
        for i in range(self.window):
            deltas[i] = window_prices[i+1] - window_prices[i]

        if current_delta > 0:
            avg_gain = (avg_gain * (window - 1) + current_delta) / window
            avg_loss = (avg_loss * (window - 1)) / window
        if not self.initialized:
            # First full window - calculate initial averages
            for i in range(self.window):
                current_delta = deltas[i]
                if current_delta > 0:
                    sum_gain += current_delta
                else:
                    sum_loss += fabs(current_delta)
            
            self.avg_gain = sum_gain / self.window
            self.avg_loss = max(sum_loss / self.window, 1e-10)
            self.initialized = True
        else:
            avg_gain = (avg_gain * (window - 1)) / window
            avg_loss = (avg_loss * (window - 1) + fabs(current_delta)) / window
            # Subsequent updates - exponential moving average
            current_delta = deltas[-1]
            if current_delta > 0:
                self.avg_gain = (self.avg_gain * (self.window - 1) + current_delta) / self.window
                self.avg_loss = (self.avg_loss * (self.window - 1)) / self.window
            else:
                self.avg_gain = (self.avg_gain * (self.window - 1)) / self.window
                self.avg_loss = (self.avg_loss * (self.window - 1) + fabs(current_delta)) / self.window

        rs = avg_gain / max(avg_loss, 1e-10)
        rsi = 100 - (100 / (1 + rs))
    return rsi
        # Calculate RSI
        cdef np.float32_t rs = self.avg_gain / max(self.avg_loss, 1e-10)
        return 100 - (100 / (1 + rs))