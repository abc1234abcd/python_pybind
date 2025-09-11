import time
import logging
import asyncio
import numpy as np
from typing import List
from pathlib import Path
from dotenv import dotenv_values
from utils.security import SecurityManager
from utils.data_class import OrderSide, OrderType, Kline, OrderBook, OrderFlow
from core.market_data_streamer import MarketDataStreamer
from core.mexc_api import MexcApiClient
#from numba import njit: consumes too much cache, and re-compile consumes way too much time 
import copy

#C++ extention
from proto_wrapper_mexc import PushDataV3ApiWrapper
from rsi_calculator import RSICalculator
from slope_calculator import calculate_slope
from order_flow import compute_order_flow

'''
true range: max(curr_high - curr_low, abs(curr_high - prev_close), abs(curr_low - prev_close))

average of true range: a simply moving average of true range values(typically a 14-period.)

1. to avoid local high trap:

solution: setup entry upfront: either a ma +- 1*std or 2*std or kline based signals: shooting star/hammer/resist level/support level

2. exit policy:

current: avg_true_range*pnl_threshold. pnl_threshold based on kline_slope_14min beta, if beta < 0, small threshold, > 0 big threshold.

solution: alpha*current_range + (1 - alpha)*avg_true_range. alpha = current_range /sum_of_range

3. cannot beat beta:

what on earth decides the price movement?

4. use ob to get live support and resist level. 

5. candle shooting star: a. (high - max(open, close))/(high - low)> 0.7 (long upper wick) b. abs(open - close) /(high - low) < 0.3 (small body) c. (min(open, close) - low)/(high - low) < 0.1 (small lower wick).

1. fix my exit policy.

'''

class TakeProfit(MarketDataStreamer):
    def __init__(self, exchange: str, topics: List[dict], api_client: MexcApiClient):
        super().__init__(exchange, topics)
        self.api_client = api_client
        self.msg_parser = PushDataV3ApiWrapper()
        self.rsi_calculator = RSICalculator(14)
        self.kline = Kline()
        self.ob = OrderBook()
        self.order_flow = OrderFlow()
        self._hist_kline_handler()
        #buffers
        self.price_buffer =[]
        self.rsi_buffer = np.full(14, np.nan)

        #pre-allocate buy/sell order
        self.filled_entry_price = 0.0
        self.filled_qty = 0.0
        self.max_position = "200" 
        self._buy_order = {
            "quoteOrderQty":  self.max_position,  
            "side": OrderSide.BUY.value,
            "symbol": "XRPUSDT",
            "timestamp": None,  
            "type": OrderType.MARKET.value
        }
        self._sell_order = {
            "quantity": None,  
            "side": OrderSide.SELL.value,
            "symbol": "XRPUSDT",
            "timestamp": None,  
            "type": OrderType.MARKET.value
        }

        #strategy based variables
        self.oversold_threshold = None
        self.overbrought_threshold = None
        self.position = None
        self.rsi_value = 0.0
        self.rsi_mean = 0.0
        self.rsi_std = 0.0
        self.rsi_momentum = 0.0
        self.prev_kline_slope = None
        self.curr_kline_slope = None
        self.kline_slope_momentum = 0.0
        self.prev_exit_price = None
        self.prev_exit_time = None
        self.avg_low = None
        self.upper_wick_pct = 0.0
        self.lower_wick_pct = 0.0
        self.body_pct = 0.0
        self.curr_true_range = 0.0


        #latency control notification
        self.last_latency = 0        
        
    def _hist_kline_handler(self):
        #kline buffer record kline at 1 minute interval
        self.kline_buffer = np.full(14, None, dtype = object)
        #true range buffer record true range at 1 minute interval
        self.true_range_buffer = np.full(14, np.nan)
        #hist kline 
        hist_kline = self.api_client.get_hist_kline(symbol = "XRPUSDT", interval = "1m")[-16:]
        #support level is the min kline.lowest in the past 14 minutes
        self.support_level = min(item[3] for item in hist_kline[-16:-1])
       
        self.kline = Kline()
        #curr kline is -1, prev kline is 
        self.prev_kline = Kline()
        self.prev_kline.update(hist_kline[-2][4], hist_kline[-2][2], hist_kline[-2][3], hist_kline[-2][1], float(hist_kline[-2][0])/1000, hist_kline[-2][5])
        for i in range(-16, -2):
            self.kline.update(hist_kline[i+1][4], hist_kline[i+1][2], hist_kline[i+1][3], hist_kline[i+1][1], float(hist_kline[i+1][0])/1000, hist_kline[i+1][5])
            #copy of python obj
            self.kline_buffer = np.roll(self.kline_buffer, -1)
            self.kline_buffer[-1] = copy.deepcopy(self.kline)
            prev_high_range = abs(float(hist_kline[i][2]) - float(hist_kline[i+1][4]))
            prev_low_range = abs(float(hist_kline[i][3]) - float(hist_kline[i+1][4]))
            self.true_range = max(float(hist_kline[i+1][2]) - float(hist_kline[i+1][3]), prev_high_range, prev_low_range)
            self.true_range_buffer = np.roll(self.true_range_buffer, -1)
            self.true_range_buffer[-1] = copy.deepcopy(self.true_range)
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
                            #ob 
                            if self.msg_parser.has_book_ticker():
                                book = self.msg_parser.book_ticker()
                                self.ob.update(
                                    bids=float(book.bid_price()),
                                    asks=float(book.ask_price()),
                                    bids_qty = float(book.bid_quantity()),
                                    asks_qty = float(book.ask_quantity())
                                )
                            #kline
                            if self.msg_parser.has_kline():
                                kline = self.msg_parser.kline()
                                self.kline.update(kline.closing_price(), kline.highest_price(), kline.lowest_price(), kline.opening_price(), kline.window_start(), kline.volume())
                                #ris, ris_mean, rsi_std
                                self.rsi_value = self.rsi_calculator.update(self.kline.closing_price)
                                self.rsi_buffer = np.roll(self.rsi_buffer, -1)
                                self.rsi_buffer[-1] = copy.deepcopy(self.rsi_value)
                                self.rsi_momentum = self.rsi_buffer[-1] - self.rsi_buffer[-2]
                                if not np.any(np.isnan(self.rsi_buffer)) and all(item != 0 for item in self.rsi_buffer):
                                    self.rsi_mean = np.mean(self.rsi_buffer)
                                    self.rsi_std = np.std(self.rsi_buffer)
                                #update kline signals:
                                curr_kline = copy.deepcopy(self.kline)
                                if self.prev_kline.window_start == curr_kline.window_start: 
                                    #update without rolling 
                                    self.kline_buffer[-1] = copy.deepcopy(curr_kline)
                                    self.price_buffer.append(curr_kline.closing_price)
                                    prev_high_range = abs(self.kline_buffer[-2].highest_price - curr_kline.closing_price)
                                    prev_low_range = abs(self.kline_buffer[-2].lowest_price - curr_kline.closing_price)
                                    self.curr_true_range = max(curr_kline.highest_price - curr_kline.lowest_price, prev_high_range, prev_low_range)
                                    self.true_range_buffer[-1] = copy.deepcopy(self.curr_true_range)
                                    self.avg_true_range = np.mean(self.true_range_buffer)
                                elif self.prev_kline.window_start != curr_kline.window_start:
                                    #update with rolling
                                    self.kline_buffer = np.roll(self.kline_buffer, -1)
                                    self.kline_buffer[-1] = copy.deepcopy(curr_kline)
                                    self.price_buffer = [curr_kline.closing_price]
                                    prev_high_range = abs(self.kline_buffer[-2].highest_price - curr_kline.closing_price)
                                    prev_low_range = abs(self.kline_buffer[-2].lowest_price - curr_kline.closing_price)
                                    self.curr_true_range = max(curr_kline.highest_price - curr_kline.lowest_price, prev_high_range, prev_low_range)
                                    self.true_range_buffer = np.roll(self.true_range_buffer, -1)
                                    self.true_range_buffer[-1] = copy.deepcopy(self.curr_true_range)
                                    self.avg_true_range = np.mean(self.true_range_buffer)
                                self.prev_kline = copy.deepcopy(curr_kline)
                                self.support_level = min(element.lowest_price for element in self.kline_buffer)
                                self.kline_min14_slope = calculate_slope([item.lowest_price for item in self.kline_buffer])
                                self.kline_slope = calculate_slope(self.price_buffer)
                            if self.msg_parser.has_public_limit_depths():
                                limit_depth_ob = self.msg_parser.limit_depths()
                                total_bids_qty = sum([float(item.quantity()) for item in limit_depth_ob.bids()])
                                total_asks_qty = sum([float(item.quantity()) for item in limit_depth_ob.asks()])
                                total_ob = total_bids_qty+total_asks_qty
                                print(total_bids_qty/total_ob,total_asks_qty/total_ob)
                            #order flows
                            if self.msg_parser.has_public_aggredeals():
                                    trades = self.msg_parser.trades()
                                    if trades and trades.deals():
                                        order_flow= compute_order_flow(trades.deals())
                                        self.order_flow.update(order_flow.bid_volume, order_flow.ask_volume, order_flow.net_flow, order_flow.price_delta, order_flow.normalized_net_flow)
                            if self.rsi_std != 0 and all(item is not None for item in [self.kline_slope, self.avg_true_range, self.support_level, self.rsi_buffer]) and all(item != 0 for item in self.rsi_buffer):
                                print(f"(price:{curr_kline.closing_price}, curr slope:{self.kline_slope}, curr_beta: {(self.kline_slope>self.kline_min14_slope)},rsi: {self.rsi_value - self.rsi_mean}, order flow:{self.order_flow.normalized_net_flow}, avg true range: {self.avg_true_range}, curr tr: {self.curr_true_range}")
                                await self._execute_strategy()
                                
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
        # micro-structure filter: ob.asks - ob.bids > 0.0008, ob.is_stable <= 0.0002
        if self.ob.is_thin():
            return        
        #self.kline_slope_momentum: 
        curr_kline_slope = copy.deepcopy(self.kline_slope)
        if self.prev_kline_slope is None:
            self.kline_slope_momentum = 0
            self.prev_kline_slope = curr_kline_slope
        else: 
            self.kline_slope_momentum = curr_kline_slope - self.prev_kline_slope
            self.prev_kline_slope = curr_kline_slope        
        #rsi threshold
        self.overbrought_threshold = self.rsi_mean + self.rsi_std
        self.oversold_threshold = self.rsi_mean - self.rsi_std

        #take profit parmas turning: 
        if self.kline_min14_slope >= 0:
            self.take_profit_threshold = 0.001
        else:
            self.take_profit_threshold = 0.0005

        #define strong momentumn: 
        curr_kline = copy.deepcopy(self.kline)
        slope_ratio = self.kline_slope/abs(self.kline_min14_slope)
        avg_scale = self.avg_true_range/curr_kline.closing_price
        self.is_strong_upward = False
        self.is_strong_dropping = False
        if slope_ratio >= 1 or self.kline_slope >= avg_scale or curr_kline.highest_price == curr_kline.closing_price:
            self.is_strong_upward = True
        elif slope_ratio <= -1 or self.kline_slope <= -avg_scale or curr_kline.lowest_price == curr_kline.closing_price:
            self.is_strong_dropping = True
        print(self.is_strong_dropping, self.is_strong_upward)

        if self.prev_kline.window_start == curr_kline.window_start:
            curr_time_ms = int(time.time()*1000)
            window_end_time_ms = curr_kline.window_start*1000 + 60000
            time_left = window_end_time_ms - curr_time_ms
        else:
            time_left = 0

        if self.position is None:
            if self.prev_exit_price is None:
                entry_position =(
                self.rsi_momentum > 0 and
                curr_kline.closing_price > curr_kline.opening_price
                ) 
            elif self.prev_exit_price is not None:
                same_window = ((self.prev_exit_time//60000) == (int(time.time()*1000)//60000))
                if same_window:
                    entry_position = False 
                else:
                    entry_position =(
                    self.rsi_momentum > 0 and
                    curr_kline.closing_price > curr_kline.opening_price
                    )
            if entry_position:
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
                    print("**************************************")
                    print("**************entry*******************")
                    print(f"close: {self.kline.closing_price}, rsi: {self.rsi_value}, rsi_mean: {self.rsi_mean}, entry price : {self.filled_entry_price}")
                    print("**************************************")
                    print("**************************************")
                elif buy_order_status.get('status') == "NEW":
                    print("order exec failed.")
                    cancel_order = self.api_client.cancel_order(symbol = 'XRPUSDT', orderId = buy_order_id)
                    if cancel_order['status'] == 'CANCELED':
                        await self._reset_position()
          
        elif self.position == "LONG":
                curr_pnl = self.ob.bids - self.filled_entry_price
                if self.is_strong_upward:
                    take_profit_condition = (
                        curr_pnl > 0.001 and
                        self.rsi_momentum < 0 )
                else:
                    take_profit_condition = (
                        curr_pnl >  0.001 and
                        self.rsi_momentum < 0
                    )
                if take_profit_condition:
                    self._sell_order["quantity"] = str(self.filled_qty)
                    self._sell_order['timestamp'] = str(int(time.time() * 1000))
                    try:
                        sell_order_response =  self.api_client.submit_orders(params = self._sell_order) 
                        sell_order_id = sell_order_response.get('orderId')
                        sell_order_status =  self.api_client.order_status(orderId = sell_order_id)
                        if sell_order_status.get('status') in ['FILLED', 'PARTIALLY_FILLED']:
                            filled_sell_qty = float(sell_order_status['executedQty'])
                            filled_sell_price = float(sell_order_status['cummulativeQuoteQty'])/filled_sell_qty
                            self.prev_exit_time = int(time.time()*1000)
                            if filled_sell_qty == self.filled_qty:
                                print("**************************************")
                                print("**************exit********************")
                                print(f"position cleared: profit: {filled_sell_price*self.filled_qty - self.filled_qty*self.filled_entry_price}, entry: {self.filled_entry_price},  exit: {filled_sell_price}")
                                print("**************************************")
                                print("**************************************")
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
    xrp_take_profit_instance = TakeProfit(exchange = exchange, topics = topics, api_client = mexc_api_client)
    await asyncio.gather(
        xrp_take_profit_instance.connect(),
    )

if __name__=='__main__':
    exchange = 'mexc'
    symbol = "XRPUSDT"
    ob_depth_level = 5
    topics = [{"method": "SUBSCRIPTION", "params":[f"spot@public.aggre.bookTicker.v3.api.pb@100ms@{symbol}", f"spot@public.kline.v3.api.pb@{symbol}@Min1", f"spot@public.aggre.deals.v3.api.pb@100ms@{symbol}", f"spot@public.limit.depth.v3.api.pb@{symbol}@{ob_depth_level}"]}]
    api_key = SecurityManager(dotenv_values(Path(__file__).parent/".env")[f"{exchange.upper()}_API_KEY"])
    api_secret = SecurityManager(dotenv_values(Path(__file__).parent/".env")[f"{exchange.upper()}_SECRET"])
    asyncio.run(main(exchange = exchange, api_key=api_key, api_secret=api_secret, topics=topics))


