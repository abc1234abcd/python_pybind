# python and pybind

Key components:

1. spot and future market data streamer(spot market is able to stream personal topics too).
2. real time indicators: relative strength index, true range, 20-level order book pressure, closing price fitted slope(rolling window, mean square error, nonpolynomial)
3. take_profit.py: for mexc zero fee spot market. future market data streamer is added for mointoring funding rate, and do a "cash and carry" arbitragy but have not finished off yet. currently this script only do a very simple regime switching mean reversion auto trading. stop loss is removed as true range does a bad job so far.
