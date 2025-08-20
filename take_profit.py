import time
import logging
import asyncio
import numpy as np
from typing import List
from pathlib import Path
from dotenv import dotenv_values
from utils.security import SecurityManager
from utils.data_class import OrderSide, OrderType, KlineCache, OrderBookCache, OrderFlowCache
from core.market_data_streamer import MarketDataStreamer
from core.mexc_api import MexcApiClient
from numba import njit

#C++ extention
from proto_wrapper_mexc import PushDataV3ApiWrapper
from rsi_calculator import RSICalculator
from slope_calculator import calculate_slope
from order_flow import compute_order_flow
'''

params:

order_type: 1: buy 2: sell

n = 200: is the length of both price_buffer and rsi_buffer. now, it is the length that we expect complete one complete run of this st. 

rsi_buffer is used to calculate the rsi_mean and rsi_std over the fixed n gap. It dynamically adjust entry/exit point.
price_buffer is used to calculate the slope(np.polyfit(x, y, 1)[0]) so entry/exit point can be re-adjusted based on +/- slope.

window = 7: rsi window. rsi convention has a window of 14, but we take it shorter so that temporary movement will be amplified. 

'''

class TakeProfit(MarketDataStreamer):

    def __init__(self, exchange: str, topics: List[dict], api_client: MexcApiClient):
        super().__init__(exchange, topics)
        self.api_client = api_client
        self.msg_parser = PushDataV3ApiWrapper()
        #rsi 
        self.rsi_calculator = RSICalculator(7)
        self.kline_cache = KlineCache()
        self.rsi_value = None

        self.ob_cache = OrderBookCache()
        self.order_flow_cache = OrderFlowCache()

        #buffer
        self.price_buffer = np.zeros(200, np.float64)
        self.rsi_buffer = np.zeros(200, np.float64)

        #pre-allocate buy/sell order
        self.filled_entry_price = None
        self.filled_qty = None
        self.max_position = "10" 
        self._buy_order = {
            "quoteOrderQty":  self.max_position,  
            "side": OrderSide.BUY.value,
            "symbol": "SOLUSDT",
            "timestamp": None,  
            "type": OrderType.MARKET.value
        }
        self._sell_order = {
            "quantity": None,  
            "side": OrderSide.SELL.value,
            "symbol": "SOLUSDT",
            "timestamp": None,  
            "type": OrderType.MARKET.value
        }

        #strategy based buffer
        self.oversold_threshold = None
        self.overbrought_threshold = None
        self.position = None
        self.prev_filled_price = None
        self.slope = None
        self.filled_rsi = None
        self.cummulated_price_delta = None

        #latency control notification
        self.last_latency = 0

    async def _message_handler(self):  
        while self._is_active and self.ws:
            try:
                #binary protobuf
                msg = await self.ws.recv()                
                if isinstance(msg, bytes):
                    if self.msg_parser.parse(msg):
                        #ob cache
                        if self.msg_parser.has_book_ticker():
                            book = self.msg_parser.book_ticker()
                            self.ob_cache.update(
                                bid=float(book.bid_price()),
                                ask=float(book.ask_price())
                            )
                        #kline and rsi
                        if self.msg_parser.has_kline():
                            kline = self.msg_parser.kline()
                            self.kline_cache.update(kline.closing_price(), kline.highest_price(), kline.lowest_price(), kline.opening_price(), kline.window_start())
                            self.rsi_value = self.rsi_calculator.update(np.float32(self.kline_cache.closing_price))
                            self.rsi_buffer = np.roll(self.rsi_buffer, -1)
                            self.rsi_buffer[-1] = self.rsi_value
                            self.rsi_buffer[1] = self.rsi_value
                            self.price_buffer = np.roll(self.price_buffer, -1)
                            self.price_buffer[-1] = self.kline_cache.closing_price
                        #order_flow
                        if self.msg_parser.has_public_aggredeals():
                                trades = self.msg_parser.trades()
                                if trades and trades.deals():
                                    order_flow= compute_order_flow(trades.deals())
                                    self.order_flow_cache.update(order_flow.bid_volume, order_flow.ask_volume, order_flow.net_flow, order_flow.price_delta, order_flow.normalized_net_flow)
                        if (self.order_flow_cache is not None and self.rsi_value is not None and self.ob_cache is not None) and all(item != 0 for item in self.rsi_buffer) and(item != 0 for item in self.price_buffer):
                                slope = calculate_slope(self.price_buffer)
                                rsi_mean = np.mean(self.rsi_buffer)
                                rsi_std = np.std(self.rsi_buffer)
                                print(self.rsi_value, self.kline_cache.closing_price, slope, rsi_mean, rsi_std)
                                await self._execute_strategy(slope, rsi_mean, rsi_std)
                    else:
                        logging.error(f"parse protobuf msg {self.msg_parser} failed.")
                else:
                    logging.warning(f"Non-bytes message: {msg}")
            except Exception as e:
                logging.error(f"cplus msg decoder fail on exception: {e}.")
                raise
    
    async def _execute_strategy(self, slope, rsi_mean, rsi_std):
        start_ns = time.time_ns()
        # Micro-structure filter
        if self.ob_cache.is_thin():
            return
        #dynamic thresholds
        if slope >= 0:
            self.oversold_threshold = rsi_mean - rsi_std
            self.overbrought_threshold = rsi_mean + rsi_std
            pnl_threshold = 0.001
        else:
            self.oversold_threshold = rsi_mean - 0.5*rsi_std
            self.overbrought_threshold =rsi_mean + 0.3*rsi_std
            pnl_threshold = 0.0005

        if (self.position is None and self.prev_filled_price is None):
            entry_position =( 
              self.rsi_buffer[-2] < self.oversold_threshold and
              self.rsi_buffer[-1] < self.oversold_threshold and
              self.rsi_buffer[-2] < self.rsi_buffer[-1] and
              self.order_flow_cache.normalized_net_flow != -1 
            )
        if (self.position is None and self.prev_filled_price is not None):
            entry_position =(
              self.rsi_buffer[-2] < self.oversold_threshold and
              self.rsi_buffer[-1] < self.oversold_threshold and
              self.rsi_buffer[-1] >self.rsi_buffer[-2] and
              self.order_flow_cache.normalized_net_flow != -1 and
              self.ob_cache.asks <= self.prev_filled_price
            )
            if entry_position:
                print("****************entry*****************")
                print(f"buy sigal: prev rsi: {self.rsi_buffer[-2]},  curr rsi: {self.rsi_value},normalized flow: {self.order_flow_cache.normalized_net_flow}, price delta: {self.order_flow_cache.price_delta}")
                self._buy_order['timestamp'] = str(int(time.time() * 1000))
                self.filled_rsi = self.rsi_buffer[-1]
                # exec order
                buy_order_response= self.api_client.submit_orders(params = self._buy_order)
                buy_order_id = buy_order_response.get('orderId')
                buy_order_status = self.api_client.order_status(orderId= buy_order_id)
                if buy_order_status.get('status') in ['FILLED', 'PARTIALLY_FILLED']:
                    self.filled_qty = float(buy_order_status['executedQty'])
                    self.filled_entry_price = float(buy_order_status['cummulativeQuoteQty'])/self.filled_qty
                    self.position = 'LONG'
                    self.prev_filled_price = self.filled_entry_price
                    print(f"buy order filled: entry price : {self.filled_entry_price}")
                elif buy_order_status.get('status') == "NEW":
                    cancel_order = self.api_client.cancel_order(symbol = 'SOLUSDT', orderId = buy_order_id)
                    if cancel_order['status'] == 'CANCELED':
                        self.position = None
                        self.filled_entry_price = 0.0
                        self.filled_qty = 0.0
                        self.filled_rsi = 0.0
        if self.position == "LONG":
                curr_pnl = (self.ob_cache.bids - self.filled_entry_price)/self.filled_entry_price
                self.cummulated_price_delta += self.order_flow_cache.price_delta
                take_profit_condition = (
                    curr_pnl > 0.00025 and
                    self.rsi_buffer[-1] - self.filled_rsi > rsi_std and
                    self.order_flow_cache.normalized_net_flow != 1
                )
                if take_profit_condition:
                    print("********exit*******")
                    print(f"sell signal: rsi: {self.rsi_value}, normalized flow: {self.order_flow_cache.normalized_net_flow}, price delta: {self.order_flow_cache.price_delta}")
                    self._sell_order["quantity"] = str(self.filled_qty)
                    self._sell_order['timestamp'] = str(int(time.time() * 1000))
                    try:
                        sell_order_response =  self.api_client.submit_orders(params = self._sell_order) 
                        sell_order_id = sell_order_response.get('orderId')
                        sell_order_status =  self.api_client.order_status(orderId = sell_order_id)
                        if sell_order_status.get('status') in ['FILLED', 'PARTIALLY_FILLED']:
                            filled_sell_qty = float(sell_order_status['executedQty'])
                            filled_sell_price = float(sell_order_status['cummulativeQuoteQty'])/filled_sell_qty
                            print(f"sell order filled: exit price:{filled_sell_price}")
                            if filled_sell_qty == self.filled_qty:
                                print(f"position cleared: profit: {filled_sell_price*self.filled_qty - self.filled_qty*self.filled_entry_price}, entry: {self.filled_entry_price},  exit: {filled_sell_price}")
                                self.position = None
                                self.filled_entry_price = None
                                self.filled_qty = None
                                
                            else:
                                print("position is not cleared in full.")
                    except Exception as e:
                        logging.error(f"submit market order exec failed on exception: {e}.")
        else:
            pass
        #latency checks
        self.last_latency = (time.time_ns() - start_ns) / 1e6
        if self.last_latency > 2.0:  # 2ms threshold
            logging.warning(f"Slow execution: {self.last_latency:.2f}ms")  
   
async def main(exchange: str, api_key: SecurityManager, api_secret: SecurityManager, topics: List[dict]):
    mexc_api_client = MexcApiClient(api_key = api_key, api_secret=api_secret)
    sol_take_profit_instance = TakeProfit(exchange = exchange, topics = topics, api_client = mexc_api_client)
    await asyncio.gather(
        sol_take_profit_instance.connect(),
    )

if __name__=='__main__':
    exchange = 'mexc'
    topics = [{"method": "SUBSCRIPTION", "params":["spot@public.aggre.bookTicker.v3.api.pb@100ms@SOLUSDT", "spot@public.kline.v3.api.pb@SOLUSDT@Min1", "spot@public.aggre.deals.v3.api.pb@100ms@SOLUSDT"]}]
    api_key = SecurityManager(dotenv_values(Path(__file__).parent/".env")[f"{exchange.upper()}_API_KEY"])
    api_secret = SecurityManager(dotenv_values(Path(__file__).parent/".env")[f"{exchange.upper()}_SECRET"])
    asyncio.run(main(exchange = exchange, api_key=api_key, api_secret=api_secret, topics=topics))



