# Detailed Code-by-Code Comparison: Leaks vs Fixes

## 1. BondTradeLoader - Memory Leak Analysis

### ❌ ORIGINAL (LEAKS MEMORY)
**File:** [Loaders/BondTradeLoader.cpp](Loaders/BondTradeLoader.cpp#L9-L31)

```cpp
BondTrade* BondTradeLoader::createTradeFromLine(const std::string& line) {
    std::vector<std::string> items;
    std::stringstream ss(line);
    std::string item;
    char separator = ',';
    
    while (std::getline(ss, item, separator)) {
        if (!item.empty() && item.back() == '\r') {
            item.pop_back();
        }
        items.push_back(item);
    }

    if (items.size() < 7) {
        throw std::runtime_error("Invalid line format");
    }
    
    std::string tradeType = BondTrade::GovBondTradeType;
    if (items[0] == "CorpBond"){
        tradeType = BondTrade::CorpBondTradeType;
    }
    
    // 🔴 PROBLEM: Raw pointer allocated but never deleted
    BondTrade* trade = new BondTrade(items[6], tradeType);
  
    
    std::tm tm = {};
    std::istringstream dateStream(items[1]);
    dateStream >> std::get_time(&tm, "%Y-%m-%d");
    auto timePoint = std::chrono::system_clock::from_time_t(std::mktime(&tm));
    trade->setTradeDate(timePoint);
    
    trade->setInstrument(items[2]);
    trade->setCounterparty(items[3]);
    trade->setNotional(std::stod(items[4]));
    trade->setRate(std::stod(items[5]));
    
    return trade;  // 🔴 Caller must manually delete, or leak occurs
}

std::vector<ITrade*> BondTradeLoader::loadTrades() {
    BondTradeList tradeList;
    loadTradesFromFile(dataFile_, tradeList);
    
    std::vector<ITrade*> result;
    for (size_t i = 0; i < tradeList.size(); ++i) {
        result.push_back(tradeList[i]);
    }
    return result;  // 🔴 Returns vector of raw pointers - no ownership transfer
}
```

### Memory Leak Scenario:
```
main()
  └─> SerialTradeLoader::loadTrades()
        └─> BondTradeLoader::loadTrades()
              └─> createTradeFromLine() [CALLED MULTIPLE TIMES]
                    └─> new BondTrade() ← HEAP ALLOCATION
                    └─> return raw pointer
              └─> Add to vector<ITrade*>
        └─> return vector
  └─> Use vector...
  └─> vector goes out of scope ← MEMORY LEAK! Objects never freed
```

### ✅ FIXED (NO LEAKS)

```cpp
std::unique_ptr<BondTrade> BondTradeLoader::createTradeFromLine(const std::string& line) {
    std::vector<std::string> items;
    std::stringstream ss(line);
    std::string item;
    char separator = ',';
    
    while (std::getline(ss, item, separator)) {
        if (!item.empty() && item.back() == '\r') {
            item.pop_back();
        }
        items.push_back(item);
    }

    if (items.size() < 7) {
        throw std::runtime_error("Invalid line format");
    }
    
    std::string tradeType = BondTrade::GovBondTradeType;
    if (items[0] == "CorpBond"){
        tradeType = BondTrade::CorpBondTradeType;
    }
    
    // ✅ SOLUTION: Use make_unique for automatic memory management
    auto trade = std::make_unique<BondTrade>(items[6], tradeType);
    
    std::tm tm = {};
    std::istringstream dateStream(items[1]);
    dateStream >> std::get_time(&tm, "%Y-%m-%d");
    auto timePoint = std::chrono::system_clock::from_time_t(std::mktime(&tm));
    trade->setTradeDate(timePoint);
    
    trade->setInstrument(items[2]);
    trade->setCounterparty(items[3]);
    trade->setNotional(std::stod(items[4]));
    trade->setRate(std::stod(items[5]));
    
    return trade;  // ✅ unique_ptr ownership transfers automatically
}

std::vector<std::unique_ptr<ITrade>> BondTradeLoader::loadTrades() {
    BondTradeList tradeList;
    loadTradesFromFile(dataFile_, tradeList);
    
    std::vector<std::unique_ptr<ITrade>> result;
    for (size_t i = 0; i < tradeList.size(); ++i) {
        result.push_back(std::unique_ptr<ITrade>(tradeList[i]));
    }
    return result;  // ✅ Clear ownership semantics
}
```

### Why This Works:
- `std::make_unique<T>()` creates a unique_ptr that owns the allocation
- When unique_ptr goes out of scope → destructor automatically calls `delete`
- Exception-safe: Works even if exception thrown
- No manual delete needed

---

## 2. FxTradeLoader - Identical Leak as BondTradeLoader

### ❌ ORIGINAL (LEAKS MEMORY)
**File:** [Loaders/FxTradeLoader.cpp](Loaders/FxTradeLoader.cpp#L50-L75)

```cpp
FxTrade* FxTradeLoader::createTradeFromLine(const std::string& line){
    std::vector<std::string> items = splitLine(line);
    if (items.size() < 9){
        throw std::runtime_error("Invalid FX trade line format");
    }

    std::string tradeType = FxTrade::FxSpotTradeType;
    if (items[0] =="FxFwd"){
        tradeType = FxTrade::FxForwardTradeType;
    }

    // 🔴 PROBLEM: Same as BondTradeLoader
    FxTrade* trade = new FxTrade(items[8], tradeType);

    std::tm tm ={};
    std::istringstream dateStream(items[1]);
    dateStream >> std::get_time(&tm, "%Y-%m-%d");
    auto timePoint = std::chrono::system_clock::from_time_t(std::mktime(&tm));
    trade->setTradeDate(timePoint);

    std::string instrument = items[2] + items[3];
    trade->setInstrument(instrument);

    trade->setCounterparty(items[7]);
    trade->setNotional(std::stod(items[4]));
    trade->setRate(std::stod(items[5]));

    std::tm valueTm = {};
    std::istringstream valueDateStream(items[6]);
    valueDateStream >> std::get_time(&valueTm, "%Y-%m-%d");
    auto valueTimePoint = std::chrono::system_clock::from_time_t(std::mktime(&valueTm));
    trade->setValueDate(valueTimePoint);

    return trade;  // 🔴 LEAK
}

std::vector<ITrade*> FxTradeLoader::loadTrades() {
    std::vector<ITrade*> trades;
    loadTradesFromFile(dataFile_, trades);
    return trades;  // 🔴 LEAK
}
```

### ✅ FIXED (NO LEAKS)

```cpp
std::unique_ptr<FxTrade> FxTradeLoader::createTradeFromLine(const std::string& line){
    std::vector<std::string> items = splitLine(line);
    if (items.size() < 9){
        throw std::runtime_error("Invalid FX trade line format");
    }

    std::string tradeType = FxTrade::FxSpotTradeType;
    if (items[0] =="FxFwd"){
        tradeType = FxTrade::FxForwardTradeType;
    }

    // ✅ SOLUTION: Use make_unique
    auto trade = std::make_unique<FxTrade>(items[8], tradeType);

    std::tm tm ={};
    std::istringstream dateStream(items[1]);
    dateStream >> std::get_time(&tm, "%Y-%m-%d");
    auto timePoint = std::chrono::system_clock::from_time_t(std::mktime(&tm));
    trade->setTradeDate(timePoint);

    std::string instrument = items[2] + items[3];
    trade->setInstrument(instrument);

    trade->setCounterparty(items[7]);
    trade->setNotional(std::stod(items[4]));
    trade->setRate(std::stod(items[5]));

    std::tm valueTm = {};
    std::istringstream valueDateStream(items[6]);
    valueDateStream >> std::get_time(&valueTm, "%Y-%m-%d");
    auto valueTimePoint = std::chrono::system_clock::from_time_t(std::mktime(&valueTm));
    trade->setValueDate(valueTimePoint);

    return trade;  // ✅ Safe ownership transfer
}

std::vector<std::unique_ptr<ITrade>> FxTradeLoader::loadTrades() {
    std::vector<std::unique_ptr<ITrade>> trades;
    loadTradesFromFile(dataFile_, trades);
    return trades;  // ✅ Safe
}
```

---

## 3. ParallelPricer - Most Complex Leak (Threading + Exception Safety)

### ❌ ORIGINAL (LEAKS + EXCEPTION UNSAFE)
**File:** [RiskSystem/ParallelPricer.cpp](RiskSystem/ParallelPricer.cpp#L45-L78)

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
                    threadSafeReceiver.addError(trade->getTradeId(), 
                        "No Pricing Engines available for this trade type");
                    return;
                }
                
                // 🔴 PROBLEM 1: Raw pointer with new/delete
                IPricingEngine* engine = nullptr;
                const std::string& typeName = it->second;
                
                if (typeName == "HmxLabs.TechTest.Pricers.GovBondPricingEngine") {
                    engine = new GovBondPricingEngine();
                } else if (typeName == "HmxLabs.TechTest.Pricers.CorpBondPricingEngine") {
                    engine = new CorpBondPricingEngine();
                } else if (typeName == "HmxLabs.TechTest.Pricers.FxPricingEngine") {
                    engine = new FxPricingEngine();
                } else {
                    threadSafeReceiver.addError(trade->getTradeId(), 
                        "Unknown pricing engine type: " + typeName);
                    return;  // 🔴 LEAK: If no engine created, but doesn't matter since engine is nullptr
                }
                
                // 🔴 PROBLEM 2: If price() throws, delete never executes
                engine->price(trade, &threadSafeReceiver);
                delete engine;  // 🔴 EXCEPTION UNSAFE
            });
        }
    }
    
    for (auto& thread : threads) {
        thread.join();
    }
}
```

**Problems with this code:**
1. **Raw pointer management** - Manual new/delete error-prone
2. **Exception safety** - If `price()` throws, `delete` never runs
3. **Memory leak in error path** - If engine nullptr, no cleanup logic
4. **Thread reference capture** - `&threadSafeReceiver` captured by reference, unsafe if receiver destroyed

### ✅ FIXED (SAFE + EXCEPTION-PROOF)

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
                    threadSafeReceiver.addError(trade->getTradeId(), 
                        "No Pricing Engines available for this trade type");
                    return;
                }
                
                // ✅ SOLUTION: Use unique_ptr for automatic cleanup
                std::unique_ptr<IPricingEngine> engine;
                const std::string& typeName = it->second;
                
                if (typeName == "HmxLabs.TechTest.Pricers.GovBondPricingEngine") {
                    engine = std::make_unique<GovBondPricingEngine>();
                } else if (typeName == "HmxLabs.TechTest.Pricers.CorpBondPricingEngine") {
                    engine = std::make_unique<CorpBondPricingEngine>();
                } else if (typeName == "HmxLabs.TechTest.Pricers.FxPricingEngine") {
                    engine = std::make_unique<FxPricingEngine>();
                } else {
                    threadSafeReceiver.addError(trade->getTradeId(), 
                        "Unknown pricing engine type: " + typeName);
                    return;  // ✅ Safe: unique_ptr auto-cleanup (no allocation happened)
                }
                
                // ✅ EXCEPTION-SAFE: delete automatic even if price() throws
                engine->price(trade, &threadSafeReceiver);
                // ✅ No manual delete: unique_ptr destructor runs automatically
                // ✅ Works if exception, normal exit, early return, etc.
            });
        }
    }
    
    for (auto& thread : threads) {
        thread.join();
    }
}
```

**Why this is better:**
- **RAII (Resource Acquisition Is Initialization)**: Resource cleanup guaranteed
- **Exception-safe**: Destructor runs in all exit paths (return, throw, normal)
- **Thread-safe**: Each thread owns its own unique_ptr
- **Zero manual delete**: No chance of double-delete

---

## 4. SerialPricer - DOUBLE DELETE BUG

### ❌ ORIGINAL (DOUBLE DELETE)
**File:** [RiskSystem/SerialPricer.cpp](RiskSystem/SerialPricer.cpp#L30-L48)

```cpp
void SerialPricer::price(const std::vector<std::vector<ITrade*>>& tradeContainers, 
                         IScalarResultReceiver* resultReceiver) {
    loadPricers();
    
    for (const auto& tradeContainer : tradeContainers) {
        for (ITrade* trade : tradeContainer) {
            std::string tradeType = trade->getTradeType();
            if (pricers_.find(tradeType) == pricers_.end()) {
                resultReceiver->addError(trade->getTradeId(), 
                    "No Pricing Engines available for this trade type");
                continue;
            }
            
            IPricingEngine* pricer = pricers_[tradeType].get();
            pricer->price(trade, resultReceiver);
            
            // 🔴 CRITICAL BUG: DOUBLE DELETE!
            // SerialPricer doesn't own the trades!
            // They're owned by SerialTradeLoader
            delete trade;  // ← UNDEFINED BEHAVIOR
        }
    }
}
```

**Why this is catastrophic:**

```
Ownership Chain:
  
  BondTradeLoader allocates: new BondTrade() 
    ↓
  Creates vector<ITrade*> with this pointer
    ↓
  Returns to SerialTradeLoader
    ↓
  SerialTradeLoader returns to main()
    ↓
  main() passes to SerialPricer::price()
    ↓
  SerialPricer THINKS it owns the trades and deletes them ← WRONG!
    ↓
  Original loaders still hold pointers to deleted objects
    ↓
  When program exits: DOUBLE DELETE, CRASH, UNDEFINED BEHAVIOR
```

### ✅ FIXED (OWNERSHIP RESPECTED)

```cpp
void SerialPricer::price(const std::vector<std::vector<ITrade*>>& tradeContainers, 
                         IScalarResultReceiver* resultReceiver) {
    loadPricers();
    
    for (const auto& tradeContainer : tradeContainers) {
        for (ITrade* trade : tradeContainer) {
            std::string tradeType = trade->getTradeType();
            if (pricers_.find(tradeType) == pricers_.end()) {
                resultReceiver->addError(trade->getTradeId(), 
                    "No Pricing Engines available for this trade type");
                continue;
            }
            
            IPricingEngine* pricer = pricers_[tradeType].get();
            pricer->price(trade, resultReceiver);
            
            // ✅ REMOVED: delete trade;
            // Reason: SerialPricer does NOT own the trades
            // Trades are owned by SerialTradeLoader
            // Never delete objects you don't own!
        }
    }
}
```

**Better Architecture:**
```cpp
// If loaders return unique_ptrs:
int main() {
    SerialTradeLoader tradeLoader;
    auto allTrades = tradeLoader.loadTrades();  // Returns vector<vector<unique_ptr>>
    
    // Convert to raw pointers for price() (price doesn't take ownership)
    std::vector<std::vector<ITrade*>> rawTrades;
    for (const auto& uniqueTrades : allTrades) {
        std::vector<ITrade*> rawVec;
        for (const auto& ut : uniqueTrades) {
            rawVec.push_back(ut.get());
        }
        rawTrades.push_back(rawVec);
    }
    
    ScalarResults results;
    SerialPricer pricer;
    pricer.price(rawTrades, &results);  // Pass raw pointers, pricer doesn't own
    
    return 0;
}  // allTrades destroyed here, all unique_ptrs cleanup automatically
```

---

## 5. TradeList - Missing Destructor

### ❌ ORIGINAL (NO DESTRUCTOR = LEAK)
**File:** [Models/TradeList.h](Models/TradeList.h)

```cpp
class TradeList : public ITradeReceiver {
public:
    TradeList() = default;
    // 🔴 NO DESTRUCTOR! Raw pointers never deleted
    
    void add(ITrade* trade) override {
        trades_.push_back(trade);
    }
    
    size_t size() const { return trades_.size(); }
    ITrade* operator[](size_t index) const { return trades_[index]; }
    
private:
    std::vector<ITrade*> trades_;  // 🔴 Raw pointers without cleanup
};
```

**Memory leak scenario:**
```
BondTradeList list;  (inherits from TradeList)
  ↓
list.add(new BondTrade(...));  Multiple times
  ↓
Vector stores raw pointers: [ptr1, ptr2, ptr3, ...]
  ↓
list goes out of scope
  ↓
~TradeList() called (default destructor does nothing)
  ↓
Vector destroyed, but raw pointers not deleted
  ↓
MEMORY LEAK! BondTrade objects remain allocated
```

### ✅ FIXED (WITH DESTRUCTOR)

**Option 1: Raw Pointer Cleanup**
```cpp
class TradeList : public ITradeReceiver {
public:
    TradeList() = default;
    
    // ✅ ADD: Virtual destructor to clean up raw pointers
    virtual ~TradeList() {
        for (auto trade : trades_) {
            delete trade;
        }
        trades_.clear();
    }
    
    void add(ITrade* trade) override {
        trades_.push_back(trade);
    }
    
    size_t size() const { return trades_.size(); }
    ITrade* operator[](size_t index) const { return trades_[index]; }
    
private:
    std::vector<ITrade*> trades_;
};
```

**Option 2: Modern C++ with unique_ptr (RECOMMENDED)**
```cpp
class TradeList : public ITradeReceiver {
public:
    TradeList() = default;
    virtual ~TradeList() = default;  // unique_ptr handles cleanup
    
    void add(std::unique_ptr<ITrade> trade) {
        trades_.push_back(std::move(trade));
    }
    
    size_t size() const { return trades_.size(); }
    ITrade* operator[](size_t index) const { return trades_[index].get(); }
    
private:
    std::vector<std::unique_ptr<ITrade>> trades_;  // ✅ Auto-cleanup
};
```

---

## Summary of Changes Required

| File | Line | Change | Type |
|------|------|--------|------|
| BondTradeLoader.cpp | 9, 31 | `new` → `make_unique`, return unique_ptr | Replace |
| FxTradeLoader.cpp | 50, 59 | `new` → `make_unique`, return unique_ptr | Replace |
| ParallelPricer.cpp | 61-69 | `new` → `make_unique`, remove delete | Replace |
| SerialPricer.cpp | 46 | Remove `delete trade;` line | Delete |
| TradeList.h | ~(default) | Add destructor with cleanup | Add |
| ScalarResults.cpp | ~(default) | Optional explicit cleanup | Add (optional) |

---

