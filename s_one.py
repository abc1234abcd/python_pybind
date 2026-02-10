import logging
import asyncio
import numpy as np
from typing import List, Tuple, Any
from pathlib import Path
from dotenv import dotenv_values
from utils.security import SecurityManager
from utils.data_class import OrderSide, OrderType, Kline, BookTicker, OrderFlow, LimitDepthsOB, Market
from core.data_streamer import DataStreamer
from core.aioapiclient import AioMexcApiClient

#from numba import njit: consumes too much cache, and re-compile consumes way too much time 
import copy
#C++ extentions
from proto_wrapper_mexc import PushDataV3ApiWrapper
from rsi_calculator import RSICalculator
from slope_calculator import calculate_slope
from order_flow import compute_order_flow


class SOne(DataStreamer):
    def __init__(self, ticker: str, exchange: str,  exchange_client: AioMexcApiClient):
        super().__init__(exchange, market, data_type, topics, exchange_client)
        #protobuf msg parser
        self.msg_parser = PushDataV3ApiWrapper()
        #return data from DataStreame
        self.kline = Kline()
        self.ob_ticker = BookTicker()
        self.order_flow = OrderFlow()
        self.limit_depths_ob = LimitDepthsOB()

        self.exchange_client = exchange_client

        #pre-allocate buy/sell order
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

    async def _message_handler(self):  
            while self._is_active and self.ws:
                try:
                    #binary protobuf
                    msg = await self.ws.recv()                
                    if isinstance(msg, bytes):
                        if self.msg_parser.parse(msg):
                            #ob_ticker: 
                            if self.msg_parser.has_book_ticker():
                                book = self.msg_parser.book_ticker()
                                self.ob_ticker.update(
                                    bids=float(book.bid_price()),
                                    asks=float(book.ask_price()),
                                    bids_qty = float(book.bid_quantity()),
                                    asks_qty = float(book.ask_quantity())
                                )
                                print(f"ob_ticker: {self.ob_ticker}/ {book}")
                            #kline
                            if self.msg_parser.has_kline():
                                kline = self.msg_parser.kline()
                                self.kline.update(kline.closing_price(), kline.highest_price(), kline.lowest_price(), kline.opening_price(), kline.window_start(), kline.volume())
                                print(f"kline: {self.kline} /{kline}")
     
                            #limit depths of order book: 20 levels, generates book dynamic buy pressure based on bid and ask qantity gap in ptc.
                            if self.msg_parser.has_public_limit_depths():
                                temp_limit_depths_ob = self.msg_parser.limit_depths()
                                self.limit_depths_ob.update(temp_limit_depths_ob.bids(), temp_limit_depths_ob.asks())
                                print(f"20 level book: {self.limit_depths_ob} /{temp_limit_depths_ob}")
                                self.book_buy_pressure = self.limit_depths_ob.book_buy_pressure
                                print(f"20 lvel book: {self.book_buy_pressure}")
                            #order flows: based on market order at each push time interval, the bid and ask quantity gap in pct.
                            if self.msg_parser.has_public_aggredeals():
                                    trades = self.msg_parser.trades()
                                    print(f"trades : {trades}")
                                    if trades and trades.deals():
                                        order_flow= compute_order_flow(trades.deals())
                                        self.order_flow.update(order_flow.bid_volume, order_flow.ask_volume, order_flow.net_flow, order_flow.price_delta, order_flow.normalized_net_flow)
                                        print(f"flow: {self.order_flow}/ {trades}")
                        else:
                            logging.error(f"parse protobuf msg {self.msg_parser} failed.")
                    else:
                        logging.warning(f"Non-bytes message: {msg}")
                except Exception as e:
                    logging.error(f"cplus msg decoder fail on exception: {e}.")
                    raise

async def main(api_key: SecurityManager, api_secret: SecurityManager, timeout: Tuple, spot_public_topics: List[Any], spot_private_topics: List[Any]):
    exchange = "mexc"

    aio_exchange_client = AioMexcApiClient(api_key=api_key, api_secret=api_secret, timeout=timeout)
    mexc_public_streamer = await SOne.public_streamer(exchange, market, data_type, spot_public_topics)
    mexc_private_streamer = await SOne.private_streamer(exchange, market, data_type, spot_private_topics, aio_exchange_client)
    try:
        await asyncio.gather(
            mexc_public_streamer.connect(),
            mexc_private_streamer.connect(),
        )
    finally:
        await asyncio.gather(
            mexc_public_streamer.safe_close(),
            mexc_private_streamer.safe_close(),
        )

if __name__=='__main__':
    exchange = 'mexc'
    symbol = "XRPUSDT"
    ob_depth_level = 20
    timeout = tuple((6, 3))
    market = Market.SPOT
    data_type = DataType.PUBLIC
    mexc_spot_public_topics = [{"method": "SUBSCRIPTION", "params":[f"spot@public.aggre.bookTicker.v3.api.pb@100ms@{symbol}", f"spot@public.kline.v3.api.pb@{symbol}@Min1", f"spot@public.aggre.deals.v3.api.pb@100ms@{symbol}", f"spot@public.limit.depth.v3.api.pb@{symbol}@{ob_depth_level}"]}]

    api_key = SecurityManager(dotenv_values(Path(__file__).parent/".env")[f"{exchange.upper()}_API_KEY"])
    api_secret = SecurityManager(dotenv_values(Path(__file__).parent/".env")[f"{exchange.upper()}_SECRET"])

    asyncio.run(main(exchange = exchange, market = market, data_type=data_type, topics=topics))


'''

mexc_spot_public_streamer = DataStreamer.public_streamer("mexc", Market.SPOT, DataType.PUBLIC, spot_public_topics)

aio_client = ...

mexc_spot_private_streamer = DataStreamer.private_streamer("mexc", Market.SPOT, DataType.PUBLIC, spot_public_topics, aio_client)

mexc_futures_public_streamer = DataStreamer.public_streamer("mexc", Market.FUTURES, DataType.PUBLIC, futures_public_topics)

await asyncio.gather(
    streamer.connect()
)



'''
