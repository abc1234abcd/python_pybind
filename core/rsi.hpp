#pragma once
#include <vector>
#include <cmath>

class RSICalculator {
public:
    RSICalculator(int window);
    float update(float new_price);
    
private:
    std::vector<float> price_buffer_;
    int window_;
    int buffer_size_;
    int current_pos_;
    float avg_gain_;
    float avg_loss_;
    bool initialized_;
    
    inline float calculate_rsi() const;
};