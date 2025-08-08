# cython: language_level=3
import numpy as np
cimport numpy as np
from libc.math cimport fabs

cdef class RSICalculator:
    cdef:
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
            # Subsequent updates - exponential moving average
            current_delta = deltas[-1]
            if current_delta > 0:
                self.avg_gain = (self.avg_gain * (self.window - 1) + current_delta) / self.window
                self.avg_loss = (self.avg_loss * (self.window - 1)) / self.window
            else:
                self.avg_gain = (self.avg_gain * (self.window - 1)) / self.window
                self.avg_loss = (self.avg_loss * (self.window - 1) + fabs(current_delta)) / self.window
        
        # Calculate RSI
        cdef np.float32_t rs = self.avg_gain / max(self.avg_loss, 1e-10)
        return 100 - (100 / (1 + rs))