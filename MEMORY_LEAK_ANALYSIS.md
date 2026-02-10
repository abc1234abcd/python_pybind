# Memory Leak Analysis Report - C++ Tech Test Project

## Executive Summary
After detailed investigation of all C++ source files in `test/tech-test/cpp`, **I have identified MULTIPLE CRITICAL MEMORY LEAKS**. The issues stem from improper raw pointer management without corresponding cleanup.

---

## CRITICAL MEMORY LEAKS IDENTIFIED

### 1. **CRITICAL: Raw Pointers in BondTradeLoader.cpp - LINE 31**
**File:** [Loaders/BondTradeLoader.cpp](Loaders/BondTradeLoader.cpp#L31)

```cpp
BondTrade* trade = new BondTrade(items[6], tradeType);
```

**Problem:**
- Raw pointer allocated with `new` but NEVER deleted
- Used in `std::vector<ITrade*> BondTradeLoader::loadTrades()`
- The vector stores raw pointers that are never cleaned up
- When the vector goes out of scope, the dynamically allocated BondTrade objects leak

**Impact:** HIGH - Every bond trade loaded from file leaks memory

**Fix:**
```cpp
// Option 1: Return unique_ptr from vector
std::vector<std::unique_ptr<ITrade>> BondTradeLoader::loadTrades() {
    BondTradeList tradeList;
    loadTradesFromFile(dataFile_, tradeList);
    
    std::vector<std::unique_ptr<ITrade>> result;
    for (size_t i = 0; i < tradeList.size(); ++i) {
        result.push_back(std::unique_ptr<ITrade>(tradeList[i]));
    }
    return result;
}

// OR Option 2: Refactor createTradeFromLine to return unique_ptr
std::unique_ptr<BondTrade> BondTradeLoader::createTradeFromLine(const std::string& line) {
    // ... parsing code ...
    return std::make_unique<BondTrade>(items[6], tradeType);
}
```

---

### 2. **CRITICAL: Raw Pointers in FxTradeLoader.cpp - LINE 59**
**File:** [Loaders/FxTradeLoader.cpp](Loaders/FxTradeLoader.cpp#L59)

```cpp
FxTrade* trade = new FxTrade(items[8], tradeType);
```

**Problem:**
- Identical issue to BondTradeLoader
- Raw pointer allocated but never deleted
- Stored in vector that doesn't manage lifetime
- All FX trades leak memory on load

**Impact:** HIGH - Every FX trade loaded from file leaks memory

**Fix:** Same as BondTradeLoader - use `std::unique_ptr`

---

### 3. **CRITICAL: Raw Pointers in ParallelPricer.cpp - LINES 61-69**
**File:** [RiskSystem/ParallelPricer.cpp](RiskSystem/ParallelPricer.cpp#L61-L69)

```cpp
threads.emplace_back([this, trade, &threadSafeReceiver]() {
    // ... code ...
    IPricingEngine* engine = nullptr;
    const std::string& typeName = it->second;
    if (typeName == "HmxLabs.TechTest.Pricers.GovBondPricingEngine") {
        engine = new GovBondPricingEngine();
    } else if (typeName == "HmxLabs.TechTest.Pricers.CorpBondPricingEngine") {
        engine = new CorpBondPricingEngine();
    } else if (typeName == "HmxLabs.TechTest.Pricers.FxPricingEngine") {
        engine = new FxPricingEngine();
    } else {
        threadSafeReceiver.addError(trade->getTradeId(), "Unknown pricing engine type: " + typeName);
        return;  // ← MEMORY LEAK! engine is nullptr, but allocated if code reaches engine->price()
    }
    engine->price(trade, &threadSafeReceiver);
    delete engine;
});
```

**Problem:**
- **If-else path without engine creation**: When typeName is unknown, `engine` remains nullptr, but the function returns without cleanup
- **Exception safety issue**: If `engine->price()` throws, the `delete engine` is never executed
- **Threads are created in a vector but never properly awaited**: Race conditions possible
- **Captures by reference are unsafe**: `&threadSafeReceiver` is captured by reference; if threads outlive the receiver, undefined behavior

**Impact:** CRITICAL - Memory leaks in multi-threaded context + exception safety issues

**Fix:**
```cpp
void ParallelPricer::price(const std::vector<std::vector<ITrade*>>& tradeContainers, 
                           IScalarResultReceiver* resultReceiver) {
    loadPricers();

    ThreadSafeResultReceiver threadSafeReceiver(resultReceiver, resultMutex_);
    std::vector<std::thread> threads;

    for (const auto& tradeContainer : tradeContainers) {
        for (ITrade* trade : tradeContainer) {
            threads.emplace_back([this, trade, &threadSafeReceiver]() {
                std::string tradeType = trade->getTradeType();
                auto it = pricerTypes_.find(tradeType);
                if (it == pricerTypes_.end()) {
                    threadSafeReceiver.addError(trade->getTradeId(), "No Pricing Engines available for this trade type");
                    return;
                }
                
                std::unique_ptr<IPricingEngine> engine;
                const std::string& typeName = it->second;
                if (typeName == "HmxLabs.TechTest.Pricers.GovBondPricingEngine") {
                    engine = std::make_unique<GovBondPricingEngine>();
                } else if (typeName == "HmxLabs.TechTest.Pricers.CorpBondPricingEngine") {
                    engine = std::make_unique<CorpBondPricingEngine>();
                } else if (typeName == "HmxLabs.TechTest.Pricers.FxPricingEngine") {
                    engine = std::make_unique<FxPricingEngine>();
                } else {
                    threadSafeReceiver.addError(trade->getTradeId(), "Unknown pricing engine type: " + typeName);
                    return;  // ← Now exception-safe; unique_ptr auto-deletes
                }
                
                engine->price(trade, &threadSafeReceiver);
                // ← unique_ptr auto-deletes when function exits
            });
        }
    }
    
    for (auto& thread : threads) {
        thread.join();
    }
}
```

---

### 4. **SERIOUS: Double-Delete in SerialPricer.cpp - LINE 46**
**File:** [RiskSystem/SerialPricer.cpp](RiskSystem/SerialPricer.cpp#L46)

```cpp
for (const auto& tradeContainer : tradeContainers) {
    for (ITrade* trade : tradeContainer) {
        // ... pricing code ...
        delete trade;  // ← DOUBLE DELETE ISSUE!
    }
}
```

**Problem:**
- Trades are owned by `SerialTradeLoader` which returns a vector of raw pointers
- `SerialPricer` **does not own** these trades and should NOT delete them
- The trades are still referenced by the original loader; deleting them here causes **undefined behavior**
- When loader goes out of scope, it tries to deallocate already-deleted memory

**Impact:** CRITICAL - Undefined behavior, potential crash

**Fix:**
```cpp
// Option 1: Remove delete - trades are not owned by SerialPricer
for (const auto& tradeContainer : tradeContainers) {
    for (ITrade* trade : tradeContainer) {
        // ... pricing code ...
        // DO NOT delete trade - it's not owned by this class
    }
}

// Option 2: Change SerialTradeLoader to return unique_ptrs
// This requires refactoring the entire loading chain
```

---

### 5. **ISSUE: TradeList Container Leaks - TradeList.h**
**File:** [Models/TradeList.h](Models/TradeList.h#L15-L17)

```cpp
class TradeList : public ITradeReceiver {
private:
    std::vector<ITrade*> trades_;  // ← Raw pointers, no cleanup
};
```

**Problem:**
- `TradeList` stores raw pointers but has **NO destructor** to clean them up
- When `BondTradeList` (derived from `TradeList`) goes out of scope, all contained trades leak
- No `unique_ptr` or manual cleanup

**Impact:** MEDIUM - All trades stored in BondTradeList leak when the list is destroyed

**Fix:**
```cpp
class TradeList : public ITradeReceiver {
public:
    TradeList() = default;
    
    // ← ADD: Destructor to clean up raw pointers
    ~TradeList() {
        for (auto trade : trades_) {
            delete trade;
        }
        trades_.clear();
    }
    
    // OR BETTER: Refactor to use unique_ptr
    // std::vector<std::unique_ptr<ITrade>> trades_;
    
private:
    std::vector<ITrade*> trades_;
};
```

---

### 6. **ISSUE: ScalarResults Cache Memory - ScalarResults.h**
**File:** [Models/ScalarResults.h](Models/ScalarResults.h#L50-L71)

```cpp
class ScalarResults : public IScalarResultReceiver {
private:
    std::vector<std::string> tradeIds_;  // ← Cached, may grow unbounded
    bool tradeIdsCached_ = true;
    // ... other members not shown
};
```

**Problem:**
- `tradeIds_` vector grows indefinitely as trades are added
- No explicit cleanup/destruction pattern
- While this is technically not a memory leak (destructors clean up vectors), it can cause excessive memory growth

**Impact:** LOW - Not a critical leak, but memory efficiency issue

**Fix:**
```cpp
// Already handled by default destructor, but could add explicit:
~ScalarResults() {
    tradeIds_.clear();
    tradeIds_.shrink_to_fit();
}
```

---

## SUMMARY TABLE

| Line | File | Issue | Severity | Type | Fix |
|------|------|-------|----------|------|-----|
| 31 | BondTradeLoader.cpp | Raw pointer not freed | CRITICAL | Memory Leak | Use `unique_ptr` |
| 59 | FxTradeLoader.cpp | Raw pointer not freed | CRITICAL | Memory Leak | Use `unique_ptr` |
| 61-69 | ParallelPricer.cpp | Engine leaks in error path | CRITICAL | Memory Leak + Exception Unsafe | Use `unique_ptr` |
| 46 | SerialPricer.cpp | Double delete attempt | CRITICAL | UB/Crash | Remove delete or refactor ownership |
| 15-17 | TradeList.h | No destructor for raw pointers | MEDIUM | Memory Leak | Add destructor or use `unique_ptr` |
| N/A | ScalarResults.cpp | Unbounded cache growth | LOW | Memory Efficiency | Minor - already handled |

---

## MAIN ENTRY POINT ANALYSIS

**File:** [ConsoleApp/main.cpp](ConsoleApp/main.cpp#L30-L40)

```cpp
int main(int argc, char* argv[]) {
    SerialTradeLoader tradeLoader;
    auto allTrades = tradeLoader.loadTrades();  // ← Returns vector of raw pointers
    
    ScalarResults results;
    ParallelPricer pricer;
    pricer.price(allTrades, &results);  // ← May delete trades (DOUBLE DELETE)
    
    ScreenResultPrinter screenPrinter;
    screenPrinter.printResults(results);
    
    return 0;
}  // ← allTrades goes out of scope - memory leaks!
```

**Problem:**
1. `SerialTradeLoader.loadTrades()` returns `std::vector<std::vector<ITrade*>>`
2. `ParallelPricer.price()` receives these raw pointers but might try to delete them
3. When `main()` exits, the vectors go out of scope but the dynamically allocated trades are NOT cleaned up
4. **DOUBLE DELETE**: If `ParallelPricer` attempts to delete trades at line 69 (`delete engine`), but trades themselves are deleted, chaos ensues

---

## RECOMMENDED FIXES (PRIORITY ORDER)

### Priority 1: IMMEDIATE (CRITICAL)
1. **Remove `delete trade` from SerialPricer.cpp line 46**
   - Change ownership model to make loaders responsible for cleanup

2. **Replace all raw `new` with `std::make_unique` in loaders**
   - Files: BondTradeLoader.cpp, FxTradeLoader.cpp
   - Change return types from `std::vector<ITrade*>` to `std::vector<std::unique_ptr<ITrade>>`

3. **Fix ParallelPricer threading issue**
   - Use `std::unique_ptr` for engine allocation
   - Ensure proper RAII semantics

### Priority 2: IMPORTANT (MEDIUM)
1. **Add destructor to TradeList class**
   - Or refactor to use `unique_ptr` container

2. **Refactor ownership model throughout**
   - Decide: Should loaders own trades? Or should main?
   - Current model is ambiguous

### Priority 3: NICE-TO-HAVE (LOW)
1. **Add explicit memory cleanup in ScalarResults**
2. **Use `std::shared_ptr` for thread-safe result receiver if needed**

---

## TOOLS TO DETECT LEAKS

To verify fixes, use these tools:

```bash
# macOS (Clang Address Sanitizer)
clang++ -fsanitize=address -g main.cpp BondTradeLoader.cpp ... -o app

# Valgrind (Linux)
valgrind --leak-check=full --show-leak-kinds=all ./app

# Visual Studio (Windows)
# Built-in debugger memory profiler
```

---

