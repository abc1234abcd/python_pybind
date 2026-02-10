#include <iostream>
#include <vector>

class RingBuffer {
    std::vector<int> buffer;
    int head = 0;
    int tail = 0;
    int capacity;
    int count = 0;
public:
    RingBuffer(int size) : buffer(size), capacity(size) {}

    bool push(int value) {
        if (count == capacity) 
            return false;
        buffer[head] = value;
        head = (head + 1)%capacity;
        count++;
        return true;
    }

    bool pop(int &value){
        if (count == 0)
            return false;
        value = buffer[tail];
        tail = (tail + 1) % capacity;
        count--;
        return true;
    }
};