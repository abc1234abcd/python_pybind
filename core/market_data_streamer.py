import asyncio
import json 
import logging 
import time
from queue import Queue
from websockets import connect 
from utils.data_class import Exchange
from typing import List, Any
from core.mexc_api import MexcApiClient
from mexc_protobuf import PushDataV3ApiWrapper_pb2
from proto_wrapper_mexc import PushDataV3ApiWrapper
from rsi import calculate_rsi

'''
i would either seperate each market data streamer: e.g book_ticker_streamer, and kline_streamer. so i do not need to redirect each msg from mexc server.

that would be: kline_streamer, with rsi.pyx to generate buy/sell directly, and send the signal through a msg queue to book_ticker_streamer, check book and then
make orders through api. so rsi.super(kline_streamer), mexc_api.super(book_ticker)
finally, the user data streamer to verify if order is filled and account updates etc. 

or:

stream kline and book_ticker from the same socket, direct msg, rsi consumes kline.closeprice to generate buy/sell,signal, 
if signal, check book_ticker to use mexc-api to make order.

data streamer to use them 
'''

class MarketDataStreamer:    
    def __init__(self, exchange: str, api_client: MexcApiClient, kline_queue: Queue, trades_queue: Queue, book_ticker_queue: Queue, topics: List[Any]):
        self.api_client = api_client
        self.exchange = Exchange(exchange.lower())
        self.kline_queue = kline_queue
        self.trades_queue = trades_queue
        self.book_ticker_queue = book_ticker_queue
        self.topics = topics
        self.ws = None
        self._is_active = False
    async def connect(self):
        self._is_active = True
        while self._is_active:
            try:
                async with connect(self.exchange.public_socket_url, ping_interval = None) as websocket:
                    self.ws = websocket 
                    logging.info(f"{self.exchange.name} connects to public websocket success!")
                    await self.subscribe()
                    await asyncio.gather(
                        self._connection_manager(),
                        self.message_decoder_cplus()
                        )
            except Exception as e:
                logging.error(f"{self.exchange.name} connect failed: {e}. Reconnecting immediately...")
    async def subscribe(self):
        if not self.ws:
            logging.error(f"{self.exchange.name} is not connected yet while trying to make subscription.") 
        if (self.topics and self.ws):
            try:
                for topic in self.topics:
                    await self.ws.send(json.dumps(topic))
            except Exception as e:
                logging.error(f"{self.exchange.name} subscription failed: {e}.")
                raise
    async def _connection_manager(self):
        if not (self.exchange.ping_message and self.exchange.ping_interval):
            return
        while self._is_active:
            try:
                await self.ws.send(json.dumps(self.exchange.ping_message))
                await asyncio.sleep(30)
            except Exception as e:
                logging.error(f"{self.exchange.name} conenction manager failed pinging (retry in 2s).")
                await asyncio.sleep(2)
    async def message_decoder_py(self):
        #pre-allocate avoid overhead
        result = PushDataV3ApiWrapper_pb2.PushDataV3ApiWrapper()
        while (self._is_active and self.ws):
            try:
                #binary protobuf 
                msg = await self.ws.recv()
                result.ParseFromString(msg)
                print(f"python parser: {result}.")
            except Exception as e:
                logging.error(f"either data streamer stopped or websocket lost connection so message_decoder_py failed:{e}.")
                raise
    async def message_decoder_cplus(self):
        msg_protobuf_holder = PushDataV3ApiWrapper()
        while self._is_active and self.ws:
            try:
                msg = await self.ws.recv()                
                if isinstance(msg, bytes):
                    if msg_protobuf_holder.parse(msg):
                        if msg_protobuf_holder.has_kline():
                            kline = msg_protobuf_holder.kline()
                            kline_dict = {
                                "symbol": msg_protobuf_holder.symbol,
                                "timestamp": int(time.time()*1000),
                                "openingprice": kline.opening_price(),
                                "closingprice": kline.closing_price(),
                                "windowstart": kline.window_start(),
                                "windowend": kline.window_end(),
                            }
                        elif msg_protobuf_holder.has_book_ticker():
                            book = msg_protobuf_holder.book_ticker()
                            book_ticker_dict = {
                                "symbol": msg_protobuf_holder.symbol,
                                "timestamp": int(time.time()*1000),
                                "bidprice": book.bid_price(),
                                "bidqty": book.bid_quantity(),
                                "askprice": book.ask_price(),
                                "askqty": book.ask_quantity()
                            }
                            print(book_ticker_dict)
                        elif msg_protobuf_holder.has_public_aggredeals():
                            trades = msg_protobuf_holder.trades()
                            for deal in trades.deals():
                                trade_dict ={
                                    "symbol": msg_protobuf_holder.symbol,
                                    "timestamp": int(time.time()*1000),
                                    "price": deal.price(),
                                    "quantity": deal.quantity(),
                                    "tradetype": deal.trade_type(),
                                    "tradetime": deal.time()
                                }
                                print(trade_dict)
                        else:
                            logging.error(f"{msg} parsed but no recognized data type")
                    else:
                        logging.error("Failed to parse protobuf message")
                else:
                    #pong and subscription confirmation msg etc.
                    logging.warning(f"Non-bytes message: {msg}")
            except Exception as e:
                logging.error(f"cplus message decoder fail on exception:{e}.")
                raise
    async def safe_close(self) -> None:
        self._is_active = False
        if hasattr(self, 'ws') and self.ws:
            try:
                if not self.ws.closed:
                    await self.ws.close(code=1000)
                logging.info(f"{self.exchange.name} websocket closed safely.")
            except Exception as e:
                logging.error(f"{self.exchange.name} websocket closing on exception: {e}.")
            finally:
                self.ws = None
 
