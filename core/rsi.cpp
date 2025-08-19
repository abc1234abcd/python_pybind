#include <vector>
#include <cmath>
#include <stdexcept>
#include <pybind11/pybind11.h>

namespace py = pybind11;

class RSICalculator {
private:
    const size_t window;
    std::vector<float> price_buffer;
    size_t buffer_pos;
    bool initialized;
    float avg_gain;
    float avg_loss;
    const float epsilon = 1e-10f;
    const float nan_value = std::numeric_limits<float>::quiet_NaN();

public:
    RSICalculator(size_t window_size) 
        : window(window_size),
          price_buffer(window_size + 1, 0.0f),
          buffer_pos(0),
          initialized(false),
          avg_gain(0.0f),
          avg_loss(0.0f) {
        
        if (window_size < 1) {
            throw std::invalid_argument("Window size must be at least 1");
        }
    }

    float update(float price) {
        // Store price in circular buffer
        price_buffer[buffer_pos] = price;
        buffer_pos = (buffer_pos + 1) % price_buffer.size();

        // Wait until we have enough data (window+1 prices)
        if (!initialized) {
            if (buffer_pos == 0) {  // Buffer is full
                calculate_initial_averages();
                initialized = true;
            }
            return nan_value;
        }

        // Calculate price change
        const size_t prev_pos = (buffer_pos - 2 + price_buffer.size()) % price_buffer.size();
        const float delta = price - price_buffer[prev_pos];

        // Update averages using Wilder's EMA
        if (delta > 0) {
            avg_gain = (avg_gain * (window - 1) + delta) / window;
            avg_loss = (avg_loss * (window - 1)) / window;
        } else {
            avg_gain = (avg_gain * (window - 1)) / window;
            avg_loss = (avg_loss * (window - 1) + std::fabs(delta)) / window;
        }

        // Calculate RSI with epsilon protection
        const float rs = avg_gain / std::max(avg_loss, epsilon);
        return 100.0f - (100.0f / (1.0f + rs));
    }

    void reset() {
        std::fill(price_buffer.begin(), price_buffer.end(), 0.0f);
        buffer_pos = 0;
        initialized = false;
        avg_gain = 0.0f;
        avg_loss = 0.0f;
    }

private:
    void calculate_initial_averages() {
        float sum_gain = 0.0f;
        float sum_loss = 0.0f;

        for (size_t i = 1; i < price_buffer.size(); ++i) {
            const float delta = price_buffer[i] - price_buffer[i-1];
            if (delta > 0) {
                sum_gain += delta;
            } else {
                sum_loss += std::fabs(delta);
            }
        }

        avg_gain = sum_gain / window;
        avg_loss = std::max(sum_loss / window, epsilon);
    }
};

PYBIND11_MODULE(rsi_calculator, m) {
    py::class_<RSICalculator>(m, "RSICalculator")
        .def(py::init<size_t>())
        .def("update", &RSICalculator::update)
        .def("reset", &RSICalculator::reset);
}