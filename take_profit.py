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
import copy

#C++ extention
from proto_wrapper_mexc import PushDataV3ApiWrapper
from rsi_calculator import RSICalculator
from slope_calculator import calculate_slope
from order_flow import compute_order_flow

'''
trading intervel is set for 1 min per round. use kline.closing_price to get the slope,so we know kline is climbing up or dropping down.

true range:

max(curr_high - curr_low, abs(curr_high - prev_close), abs(curr_low - prev_close))

average of true range: a simply moving average of true range values(typically a 14-period.)

current st: simple mean reverting with dynamic take profit and stop loss using self.avg_true_range


my current avg_true_range takes past 14 minutes kline 
'''

class TakeProfit(MarketDataStreamer):
    def __init__(self, exchange: str, topics: List[dict], api_client: MexcApiClient):
        super().__init__(exchange, topics)
        self.api_client = api_client
        self.msg_parser = PushDataV3ApiWrapper()
        self.rsi_calculator = RSICalculator(14)
        #hist kline handler generates self.support_level and  ture_range for dynamic taking profit pct adjustments
        self._hist_kline_handler()
        self.kline_cache = KlineCache()
        self.ob_cache = OrderBookCache()
        self.order_flow_cache = OrderFlowCache()
        #price buffer records kline_cache.closing_price being pushed 
        self.price_buffer =[]
        #rsi_buffer records each new rsi value based on kline_cache.closing_price being pushed.
        self.rsi_buffer = np.full(14, np.nan)
        #pre-allocate buy/sell order
        self.filled_entry_price = 0.0
        self.filled_qty = 0.0
        self.max_position = "95" 
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

        #strategy based variables
        self.oversold_threshold = None
        self.overbrought_threshold = None
        self.position = None
        self.rsi_mean = 0.0
        self.rsi_std = 0.0

        self.prev_kline_slope = None
        self.curr_kline_slope = None
        self.kline_slope_momentum = 0.0
        self.prev_exit_price = None
        self.reentry_allowed = True

        #latency control notification
        self.last_latency = 0        
        
    def _hist_kline_handler(self):
        #kline buffer record kline at 1 minute interval
        self.kline_buffer = np.full(14, None, dtype = object)
        #true range buffer record true range at 1 minute interval
        self.true_range_buffer = np.full(14, np.nan)
        #hist kline 
        hist_kline = self.api_client.get_hist_kline(symbol = "SOLUSDT", interval = "1m")[-16:]
        #support level is the min kline.lowest in the past 14 minutes
        self.support_level = min(item[3] for item in hist_kline[-16:-1])
       
        self.kline_cache = KlineCache()
        #curr kline is -1, prev kline is 
        self.prev_kline_cache = KlineCache()
        self.prev_kline_cache.update(hist_kline[-2][4], hist_kline[-2][2], hist_kline[-2][3], hist_kline[-2][1], float(hist_kline[-2][0])/1000)
        for i in range(-16, -2):
            self.kline_cache.update(hist_kline[i+1][4], hist_kline[i+1][2], hist_kline[i+1][3], hist_kline[i+1][1], float(hist_kline[i+1][0])/1000)
            self.kline_buffer = np.roll(self.kline_buffer, -1)
            self.kline_buffer[-1] = self.kline_cache
            #print(self.kline_cache[0].window_start, self.kline_cache[-1].window_start)
            prev_high_range = abs(float(hist_kline[i][2]) - float(hist_kline[i+1][4]))
            prev_low_range = abs(float(hist_kline[i][3]) - float(hist_kline[i+1][4]))
            self.true_range = max(float(hist_kline[i+1][2]) - float(hist_kline[i+1][3]), prev_high_range, prev_low_range)
            self.true_range_buffer = np.roll(self.true_range_buffer, -1)
            self.true_range_buffer[-1] = self.true_range
            if all(item != 0 for item in self.true_range_buffer):
                self.avg_true_range = np.mean(self.true_range_buffer)
        self.kline_min14_slope = calculate_slope([item.closing_price for item in self.kline_buffer])

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
                                    bids=float(book.bid_price()),
                                    asks=float(book.ask_price()),
                                    bids_qty = float(book.bid_quantity()),
                                    asks_qty = float(book.ask_quantity())
                                )
                            #kline.
                            if self.msg_parser.has_kline():
                                kline = self.msg_parser.kline()
                                self.kline_cache.update(kline.closing_price(), kline.highest_price(), kline.lowest_price(), kline.opening_price(), kline.window_start())
                                #ris, ris_mean, rsi_std
                                self.rsi_value = self.rsi_calculator.update(self.kline_cache.closing_price)
                                self.rsi_buffer = np.roll(self.rsi_buffer, -1)
                                self.rsi_buffer[-1] = self.rsi_value
                                if not np.any(np.isnan(self.rsi_buffer)):
                                    self.rsi_mean = np.mean(self.rsi_buffer)
                                    self.rsi_std = np.std(self.rsi_buffer)
                                #update:
                                curr_kline_cache = self.kline_cache
                                if self.prev_kline_cache.window_start == curr_kline_cache.window_start: 
                                    #update without rolling 
                                    self.kline_buffer[-1] = curr_kline_cache
                                    self.price_buffer.append(curr_kline_cache.closing_price)
                                    prev_high_range = abs(self.kline_buffer[-2].highest_price - curr_kline_cache.closing_price)
                                    prev_low_range = abs(self.kline_buffer[-2].lowest_price - curr_kline_cache.closing_price)
                                    curr_true_range = max(curr_kline_cache.highest_price - curr_kline_cache.lowest_price, prev_high_range, prev_low_range)
                                    self.true_range_buffer[-1] = curr_true_range
                                    self.avg_true_range = np.mean(self.true_range_buffer)
                                elif self.prev_kline_cache.window_start != curr_kline_cache.window_start:
                                    #update with rolling
                                    self.kline_buffer = np.roll(self.kline_buffer, -1)
                                    self.kline_buffer[-1] = curr_kline_cache
                                    self.price_buffer = [curr_kline_cache.closing_price]
                                    prev_high_range = abs(self.kline_buffer[-2].highest_price - curr_kline_cache.closing_price)
                                    prev_low_range = abs(self.kline_buffer[-2].lowest_price - curr_kline_cache.closing_price)
                                    curr_true_range = max(curr_kline_cache.highest_price - curr_kline_cache.lowest_price, prev_high_range, prev_low_range)
                                    self.true_range_buffer = np.roll(self.true_range_buffer, -1)
                                    self.true_range_buffer[-1] = curr_true_range
                                    self.avg_true_range = np.mean(self.true_range_buffer)
                                self.prev_kline_cache = copy.deepcopy(curr_kline_cache)
                                self.support_level = min(element.lowest_price for element in self.kline_buffer)
                                self.kline_min14_slope = calculate_slope([item.closing_price for item in self.kline_buffer])
                                #deepcopy avoid reference the same obj
                                self.kline_slope = calculate_slope(self.price_buffer)
                            #order flow
                            if self.msg_parser.has_public_aggredeals():
                                    trades = self.msg_parser.trades()
                                    if trades and trades.deals():
                                        order_flow= compute_order_flow(trades.deals())
                                        self.order_flow_cache.update(order_flow.bid_volume, order_flow.ask_volume, order_flow.net_flow, order_flow.price_delta, order_flow.normalized_net_flow)
                            if self.rsi_std != 0 and all(item is not None for item in [self.kline_slope, self.avg_true_range, self.support_level, self.rsi_buffer]) and all(item != 0 for item in self.rsi_buffer):
                                print(f"14 mins slope:{self.kline_min14_slope}, curr slope:{self.kline_slope}, rsi: {self.rsi_value}, enter threshold: {self.rsi_mean - self.rsi_std}, order flow:{self.order_flow_cache.normalized_net_flow}")
                                #await self._execute_strategy()
                        else:
                            logging.error(f"parse protobuf msg {self.msg_parser} failed.")
                    else:
                        logging.warning(f"Non-bytes message: {msg}")
                except Exception as e:
                    logging.error(f"cplus msg decoder fail on exception: {e}.")
                    raise
    
    async def _execute_strategy(self):

        #latency control
        start_ns = time.time_ns()

        # micro-structure filter
        if self.ob_cache.is_thin():
            return
        
        #self.kline_slope_momentum: 
        curr_kline_slope = self.kline_slope
        if self.prev_kline_slope is None:
            self.kline_slope_momentum = 0
            self.prev_kline_slope = curr_kline_slope
        else: 
            self.kline_slope_momentum = curr_kline_slope - self.prev_kline_slope
            self.prev_kline_slope = curr_kline_slope
        #rsi momentum
        rsi_momentum = self.rsi_buffer[-1] - self.rsi_buffer[-2]
        
        #rsi threshold
        self.overbrought_threshold = self.rsi_mean + self.rsi_std
        self.oversold_threshold = self.rsi_mean - self.rsi_std

        if self.position is None and self.reentry_allowed:
            if self.prev_exit_price is None:
                entry_position =(
                rsi_momentum > 0 and
                self.rsi_value < self.oversold_threshold and
                self.kline_cache.closing_price >= self.prev_kline.opening_price and 
                self.kline_slope > -0.00015)
            elif self.prev_exit_price is not None:
                self.reentry_allowed = (self.ob_cache.asks > (self.prev_exit_price) and self.kline_slope > 0.01)
                entry_position = (
                rsi_momentum > 0 and
                self.rsi_value < self.oversold_threshold and
                self.kline_cache.closing_price < self.prev_kline.highest_price and 
                self.kline_slope > -0.001  
                #self.ob_cache.asks < self.prev_exit_price
                )
            if entry_position:
                print("****************entry*****************")
                print(f"buy sigal: prev rsi: {self.rsi_buffer[-2]},  curr rsi: {self.rsi_value},normalized flow: {self.order_flow_cache.normalized_net_flow}, price delta: {self.order_flow_cache.price_delta}")
                self._buy_order['timestamp'] = str(int(time.time() * 1000))
                # exec order
                buy_order_response= self.api_client.submit_orders(params = self._buy_order)
                buy_order_id = buy_order_response.get('orderId')
                buy_order_status = self.api_client.order_status(orderId= buy_order_id)
                if buy_order_status.get('status') in ['FILLED', 'PARTIALLY_FILLED']:
                    self.filled_qty = float(buy_order_status['executedQty'])
                    self.filled_entry_price = float(buy_order_status['cummulativeQuoteQty'])/self.filled_qty
                    self.filled_rsi = self.rsi_value
                    self.position = 'LONG'
                    
                    print(f"buy order filled: entry price : {self.filled_entry_price}")
                elif buy_order_status.get('status') == "NEW":
                    print("order exec failed.")
                    cancel_order = self.api_client.cancel_order(symbol = 'SOLUSDT', orderId = buy_order_id)
                    if cancel_order['status'] == 'CANCELED':
                        await self._reset_position()
          
        elif self.position == "LONG":
                curr_pnl = self.ob_cache.bids - self.filled_entry_price
                #self.cummulated_price_delta += self.order_flow_cache.price_delta
                take_profit_condition = (
                    curr_pnl > self.avg_true_range*0.5 and 
                    self.kline_slope < 0.001
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
                                self.prev_exit_price = filled_sell_price
                                await self._reset_position()
                            else:
                                print("position is not cleared in full.")
                    except Exception as e:
                        logging.error(f"submit market order exec failed on exception: {e}.")
            
        #latency checks
        self.last_latency = (time.time_ns() - start_ns) / 1e6
        if self.last_latency > 2.0:  # 2ms threshold
            logging.warning(f"Slow execution: {self.last_latency:.2f}ms")  

    async def _reset_position(self):
        self.position = None
        self.filled_entry_price = 0.0
        self.filled_qty = 0.0
        self.filled_rsi = 0.0
 
        
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


