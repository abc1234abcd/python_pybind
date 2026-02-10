# C++ Memory Leak Detection & Fix Summary

## 🔴 CRITICAL FINDINGS

Your C++ project in `test/tech-test/cpp` contains **6 memory leak vulnerabilities** across multiple files. Below is a detailed breakdown with line-by-line fixes.

---

## 1️⃣ **BondTradeLoader.cpp - Line 31** ⚠️ CRITICAL

### The Problem:
```cpp
BondTrade* trade = new BondTrade(items[6], tradeType);  // ← RAW POINTER, NO DELETION
```

### Why It Leaks:
- `new` allocates memory on the heap
- The pointer is returned in a vector: `std::vector<ITrade*>`
- When the vector is destroyed, **the raw pointers are NOT deleted**
- The actual BondTrade objects remain in memory forever

### Memory Flow Diagram:
```
main()
  ↓
SerialTradeLoader::loadTrades()
  ↓
BondTradeLoader::loadTrades()
  ↓
createTradeFromLine() creates: new BondTrade() → RAW POINTER
  ↓
Returns vector of raw pointers
  ↓
Vector goes out of scope → MEMORY LEAK (BondTrade objects still allocated!)
```

### The Fix:
```cpp
// CHANGE FROM:
BondTrade* trade = new BondTrade(items[6], tradeType);

// CHANGE TO:
auto trade = std::make_unique<BondTrade>(items[6], tradeType);

// Return type changes from:
std::vector<ITrade*> BondTradeLoader::loadTrades()

// To:
std::vector<std::unique_ptr<ITrade>> BondTradeLoader::loadTrades()
```

**Why this works:**
- `std::make_unique` returns a `std::unique_ptr`
- `unique_ptr` automatically deletes the object when it goes out of scope
- No manual `delete` needed - RAII principle

---

## 2️⃣ **FxTradeLoader.cpp - Line 59** ⚠️ CRITICAL

### The Problem:
```cpp
FxTrade* trade = new FxTrade(items[8], tradeType);  // ← IDENTICAL LEAK AS ABOVE
```

### Why It Leaks:
Same as BondTradeLoader - raw pointer with no cleanup

### Memory Flow:
```
FxTradeLoader::loadTrades()
  ↓
createTradeFromLine() → new FxTrade() → RAW POINTER
  ↓
Vector of raw pointers returned
  ↓
LEAK when vector destroyed
```

### The Fix:
```cpp
// Use unique_ptr instead
auto trade = std::make_unique<FxTrade>(items[8], tradeType);
return std::vector<std::unique_ptr<ITrade>>;
```

---

## 3️⃣ **ParallelPricer.cpp - Lines 61-69** ⚠️ CRITICAL + EXCEPTION UNSAFE

### The Problem:
```cpp
threads.emplace_back([this, trade, &threadSafeReceiver]() {
    IPricingEngine* engine = nullptr;  // ← RAW POINTER
    const std::string& typeName = it->second;
    
    if (typeName == "...GovBondPricingEngine") {
        engine = new GovBondPricingEngine();  // ← RAW NEW
    } else if (typeName == "...CorpBondPricingEngine") {
        engine = new CorpBondPricingEngine();  // ← RAW NEW
    } else if (typeName == "...FxPricingEngine") {
        engine = new FxPricingEngine();  // ← RAW NEW
    } else {
        threadSafeReceiver.addError(...);
        return;  // ← LEAK HERE! engine not deleted if nullptr
    }
    
    engine->price(trade, &threadSafeReceiver);
    delete engine;  // ← May not execute if exception thrown above
});
```

### Why It Leaks (Multiple Reasons):

**Issue 1: Unknown Engine Type Path**
```
If engine type is "UnknownType":
  → No allocation happens (engine remains nullptr)
  → But if some allocations happened earlier, they'd leak
  → return statement doesn't delete
```

**Issue 2: Exception Safety**
```
If engine->price() throws an exception:
  → delete engine is NEVER executed
  → Exception-unsafe code!
  → MEMORY LEAK in error conditions
```

**Issue 3: Thread Safety**
```
Threads are created in vector and run asynchronously
If main() thread ends before worker threads finish:
  → References to threadSafeReceiver become invalid
  → Undefined behavior
```

### The Fix:
```cpp
threads.emplace_back([this, trade, &threadSafeReceiver]() {
    // ... earlier code ...
    
    // USE unique_ptr - automatic cleanup!
    std::unique_ptr<IPricingEngine> engine;
    
    if (typeName == "...GovBondPricingEngine") {
        engine = std::make_unique<GovBondPricingEngine>();
    } else if (typeName == "...CorpBondPricingEngine") {
        engine = std::make_unique<CorpBondPricingEngine>();
    } else if (typeName == "...FxPricingEngine") {
        engine = std::make_unique<FxPricingEngine>();
    } else {
        threadSafeReceiver.addError(...);
        return;  // ✓ Safe now - unique_ptr auto-deletes
    }
    
    engine->price(trade, &threadSafeReceiver);
    // ✓ No delete needed - unique_ptr handles it
    // ✓ Exception-safe - destructor runs even if exception thrown
});
```

**Why this is better:**
- RAII: Resource Acquisition Is Initialization
- Exception-safe: Works even if `price()` throws
- Thread-safe: Each thread owns its own unique_ptr
- No manual delete needed

---

## 4️⃣ **SerialPricer.cpp - Line 46** ⚠️ CRITICAL (DOUBLE DELETE)

### The Problem:
```cpp
void SerialPricer::price(...) {
    // ... setup code ...
    for (ITrade* trade : tradeContainer) {
        // ... pricing code ...
        delete trade;  // ← DOUBLE DELETE BUG!
    }
}
```

### Why It Crashes:

**Ownership Violation:**
```
SerialTradeLoader owns the trades (they were allocated by loaders)
  ↓
main() receives vector of trades from loader
  ↓
SerialPricer::price() receives the SAME trades
  ↓
SerialPricer deletes trades → BUG! They're not owned by SerialPricer
  ↓
main() exits, loaders' destructors run
  ↓
Attempt to delete already-deleted memory → CRASH/UNDEFINED BEHAVIOR
```

**Visual Timeline:**
```
Time 1: BondTradeLoader allocates trade via new
        ↓
        Trade pointer added to vector
        ↓
        Passed to main()
        
Time 2: main() passes to SerialPricer::price()
        ↓
        SerialPricer tries: delete trade  ← INVALID!
        ↓
        Heap corrupted
        
Time 3: main() function ends
        ↓
        Loaders try to clean up
        ↓
        CRASH - double delete or use-after-free
```

### The Fix:
```cpp
// REMOVE THE DELETE STATEMENT:
for (ITrade* trade : tradeContainer) {
    // ... pricing code ...
    // DON'T delete trade - SerialPricer doesn't own it!
}

// The trades are owned by SerialTradeLoader
// They should be cleaned up by the loader, not the pricer
```

**Better Approach - Refactor Ownership:**
```cpp
// Change SerialTradeLoader to return unique_ptrs
// Then main() owns them properly:

int main() {
    SerialTradeLoader tradeLoader;
    auto allTrades = tradeLoader.loadTrades();  // Returns vector<unique_ptr>
    
    ScalarResults results;
    ParallelPricer pricer;
    
    // Convert unique_ptrs to raw ptrs for pricer (pricer doesn't own)
    std::vector<std::vector<ITrade*>> rawTrades;
    for (const auto& uniqueTrades : allTrades) {
        std::vector<ITrade*> rawVec;
        for (const auto& ut : uniqueTrades) {
            rawVec.push_back(ut.get());
        }
        rawTrades.push_back(rawVec);
    }
    
    pricer.price(rawTrades, &results);  // Safe - pricer doesn't own
    
    return 0;
}  // allTrades cleaned up automatically via unique_ptr destructors
```

---

## 5️⃣ **TradeList.h** ⚠️ MEDIUM (Missing Destructor)

### The Problem:
```cpp
class TradeList : public ITradeReceiver {
private:
    std::vector<ITrade*> trades_;  // ← RAW POINTERS, NO CLEANUP!
    
    // NO DESTRUCTOR = NO CLEANUP
};
```

### Why It Leaks:
- `TradeList` stores raw pointers to trades
- When `BondTradeList` (derived class) is destroyed, NO destructor runs
- The contained trade objects are never deleted
- **All trades in the list leak**

### The Fix:
```cpp
class TradeList : public ITradeReceiver {
public:
    virtual ~TradeList() {  // ← ADD destructor
        for (auto trade : trades_) {
            delete trade;
        }
        trades_.clear();
    }
    
private:
    std::vector<ITrade*> trades_;
};
```

**Or use unique_ptr (better):**
```cpp
class TradeList : public ITradeReceiver {
public:
    virtual ~TradeList() = default;  // unique_ptr handles cleanup
    
private:
    std::vector<std::unique_ptr<ITrade>> trades_;
};
```

---

## 6️⃣ **ScalarResults Memory Cache** ⚠️ LOW

### The Problem:
```cpp
class ScalarResults {
private:
    std::vector<std::string> tradeIds_;  // ← Unbounded cache
    std::map<std::string, double> results_;
    std::map<std::string, std::string> errors_;
};
```

### Why It's a Problem:
- Cache can grow indefinitely
- No limit on memory growth
- Not a critical leak but efficiency issue

### The Fix:
```cpp
// Already handled by default destructor
// But could add explicit cleanup:
~ScalarResults() {
    tradeIds_.clear();
    tradeIds_.shrink_to_fit();
    results_.clear();
    errors_.clear();
}
```

---

## 📊 LEAK SUMMARY TABLE

| Issue | File | Line | Leak Type | Severity | Objects Affected |
|-------|------|------|-----------|----------|------------------|
| Raw new without delete | BondTradeLoader.cpp | 31 | Heap | 🔴 CRITICAL | ALL BondTrade objects |
| Raw new without delete | FxTradeLoader.cpp | 59 | Heap | 🔴 CRITICAL | ALL FxTrade objects |
| Raw new + exception unsafe | ParallelPricer.cpp | 61-69 | Heap | 🔴 CRITICAL | Pricing engines |
| Double delete attempt | SerialPricer.cpp | 46 | Heap | 🔴 CRITICAL | ALL trades |
| Missing destructor | TradeList.h | N/A | Heap | 🟠 MEDIUM | Trades in list |
| Unbounded cache | ScalarResults.cpp | N/A | Memory | 🟡 LOW | Trade ID strings |

---

## 🛠️ QUICK REFERENCE: BEFORE & AFTER

### Before (LEAKS):
```cpp
BondTrade* trade = new BondTrade(...);
std::vector<ITrade*> trades;
trades.push_back(trade);
return trades;  // ← LEAK! trades never deleted
```

### After (SAFE):
```cpp
auto trade = std::make_unique<BondTrade>(...);
std::vector<std::unique_ptr<ITrade>> trades;
trades.push_back(std::move(trade));
return trades;  // ✓ Auto-cleaned up
```

---

## 🔧 Implementation Steps

1. **Update BondTradeLoader**
   - Use `std::make_unique` in `createTradeFromLine()`
   - Change return type to `std::vector<std::unique_ptr<ITrade>>`
   
2. **Update FxTradeLoader**
   - Use `std::make_unique` in `createTradeFromLine()`
   - Change return type to `std::vector<std::unique_ptr<ITrade>>`

3. **Fix ParallelPricer**
   - Replace raw `new` with `std::make_unique`
   - Remove manual `delete engine`

4. **Fix SerialPricer**
   - Remove `delete trade` statement

5. **Update TradeList**
   - Add virtual destructor with cleanup
   - Or switch to `std::vector<std::unique_ptr<ITrade>>`

6. **Update main.cpp** (if needed)
   - Adjust for unique_ptr returns from loaders
   - Use `.get()` to convert to raw pointers if needed

---

## 📝 Testing for Leaks

### On macOS with Clang:
```bash
cd /Users/bingxu/Documents/vs/bot/test/tech-test/cpp
clang++ -fsanitize=address -g -o app main.cpp *.cpp && ./app
```

### With Valgrind (Linux):
```bash
valgrind --leak-check=full --show-leak-kinds=all ./app
```

### Output should show: `SUMMARY: AddressSanitizer: 0 bytes leaked`

---

## 📚 C++ Smart Pointers Quick Reference

| Pointer Type | Ownership | When to Use | Auto Delete |
|-------------|-----------|------------|------------|
| `T*` | None (raw) | ❌ Avoid | ❌ No |
| `unique_ptr<T>` | Single owner | ✅ Single allocation | ✓ Yes |
| `shared_ptr<T>` | Multiple owners | ✅ Shared resources | ✓ Yes (refcount) |
| `weak_ptr<T>` | Borrowed access | ✅ Break cycles | ❌ No |

**Rule of Thumb:** Use `unique_ptr` by default, `shared_ptr` only if needed.

---

## ✅ Files Provided

Fixed versions have been created with `_FIXED` suffix:
- `BondTradeLoader_FIXED.h`
- `BondTradeLoader_FIXED.cpp`
- `FxTradeLoader_FIXED.cpp`
- `ParallelPricer_FIXED.cpp`
- `SerialPricer_FIXED.cpp`
- `TradeList_FIXED.h`

---

## 🎯 Conclusion

**Total Memory Leaks Found: 6**
- **Critical (4):** Immediate fix required
- **Medium (1):** Should be fixed soon
- **Low (1):** Nice to have

All leaks are in the **memory management layer** (loaders, pricers, containers). The fixes involve using C++ smart pointers (`unique_ptr`, `shared_ptr`) instead of raw pointers with manual `delete`.

**Time to implement fixes: ~30 minutes**
**Complexity: Medium**
**Risk level: Low** (only memory management changes)

