#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <arm_neon.h>  // ARM's SIMD header

namespace py = pybind11;

__attribute__((always_inline)) 
inline float fast_slope(const float* prices, size_t size) {
    if (size < 2) return 0.0f;
    
    // ARM NEON vector accumulators
    float32x4_t sum_x = vdupq_n_f32(0);
    float32x4_t sum_y = vdupq_n_f32(0);
    float32x4_t sum_xy = vdupq_n_f32(0);
    float32x4_t sum_x2 = vdupq_n_f32(0);
    
    size_t i = 0;
    for (; i + 3 < size; i += 4) {
        float32x4_t x = {i+0.f, i+1.f, i+2.f, i+3.f};
        float32x4_t y = vld1q_f32(prices + i);
        
        sum_x = vaddq_f32(sum_x, x);
        sum_y = vaddq_f32(sum_y, y);
        sum_xy = vaddq_f32(sum_xy, vmulq_f32(x, y));
        sum_x2 = vaddq_f32(sum_x2, vmulq_f32(x, x));
    }

    // Horizontal add
    float total_x = vaddvq_f32(sum_x);
    float total_y = vaddvq_f32(sum_y);
    float total_xy = vaddvq_f32(sum_xy);
    float total_x2 = vaddvq_f32(sum_x2);

    // Process remaining elements
    for (; i < size; ++i) {
        float x = static_cast<float>(i);
        float y = prices[i];
        total_x += x;
        total_y += y;
        total_xy += x * y;
        total_x2 += x * x;
    }

    float n = static_cast<float>(size);
    float denominator = n * total_x2 - total_x * total_x;
    
    return (denominator != 0.0f) 
           ? (n * total_xy - total_x * total_y) / denominator
           : 0.0f;
}

PYBIND11_MODULE(slope_calculator, m) {
    m.def("calculate_slope", [](py::array_t<float> arr) {
        py::buffer_info buf = arr.request();
        if (buf.ndim != 1) {
            throw std::runtime_error("Only 1D arrays supported");
        }
        return fast_slope(static_cast<float*>(buf.ptr), buf.size);
    });
}