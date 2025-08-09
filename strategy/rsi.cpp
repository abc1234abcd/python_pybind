#include "rsi.hpp"
#include <pybind11/pybind11.h>

namespace py = pybind11;

RSICalculator::RSICalculator(int window) 
    : window_(window),
      buffer_size_(window + 1),
      current_pos_(0),
      avg_gain_(0.0f),
      avg_loss_(1e-10f),
      initialized_(false) {
    price_buffer_.resize(buffer_size_);
}

inline float RSICalculator::calculate_rsi() const {
    const float rs = avg_gain_ / std::max(avg_loss_, 1e-10f);
    return 100.0f - (100.0f / (1.0f + rs));
}

float RSICalculator::update(float new_price) {
    // Update circular buffer
    price_buffer_[current_pos_] = new_price;
    current_pos_ = (current_pos_ + 1) % buffer_size_;
    
    if (!initialized_) {
        if (current_pos_ < window_) return NAN;
        
        // Initial SMA calculation
        float sum_gain = 0, sum_loss = 0;
        for (int i = 1; i <= window_; ++i) {
            const float delta = price_buffer_[i % buffer_size_] - price_buffer_[(i-1) % buffer_size_];
            sum_gain += std::max(delta, 0.0f);
            sum_loss += std::max(-delta, 0.0f);
        }
        
        avg_gain_ = sum_gain / window_;
        avg_loss_ = std::max(sum_loss / window_, 1e-10f);
        initialized_ = true;
    } else {
        // EMA update
        const float delta = price_buffer_[(current_pos_-1) % buffer_size_] - 
                          price_buffer_[(current_pos_-2) % buffer_size_];
        const float gain = std::max(delta, 0.0f);
        const float loss = std::max(-delta, 0.0f);
        
        avg_gain_ = (avg_gain_*(window_-1) + gain)/window_;
        avg_loss_ = std::max((avg_loss_*(window_-1) + loss)/window_, 1e-10f);
    }
    
    return calculate_rsi();
}

PYBIND11_MODULE(rsi, m) {
    py::class_<RSICalculator>(m, "RSICalculator")
        .def(py::init<int>())
        .def("update", &RSICalculator::update);
}