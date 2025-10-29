import asyncio
import json 
import logging 
import hmac
import time
from hashlib import sha256
from websockets import connect 
from utils.config_loader import ExchangeConfig
from utils.data_class import Market, Access, Stream
from typing import Optional, List
from abc import ABC, abstractmethod
from string import Template
from core.aioapiclient import AioMexcApiClient

'''
this script makes subscription to spot and future market data from mexc exchange. unsubscription is not setup as when websocket is closed properly, the subscription expires automatically anyways.

exchange.market.access.stream -> eg. mexc.spot.public.kline or mexc.future.public.ticker

'''
class DataStreamer(ABC): 
    def __init__(self, ticker: str, exchange_name: str, market: Market, access: Access, stream: List[Stream], exchange_client: Optional[AioMexcApiClient] = None):
        self.ticker = ticker.upper()
        self.exchange_name = exchange_name.lower()
        self.market = market
        self.access = access
        self.stream = stream
        self.exchange_client = exchange_client
        #exchange config
        self.exchange_config = ExchangeConfig(exchange_name=exchange_name.lower(), market = market).model_dump()
        #DataStreamer connection management variables
        self.ws = None
        self._is_active = False

    @classmethod 
    async def private_streamer(cls, ticker: str, exchange_name: str, market: Market, access: Access, stream: List[Stream], exchange_client: AioMexcApiClient):
        instance = cls(ticker, exchange_name, market, access, stream, exchange_client)
        await instance.exchange_client.open_session()
        return instance
    
    @classmethod
    async def public_streamer(cls, ticker: str, exchange_name: str, market: Market, access: Access, stream: List[Stream]):
        if access == access.PRIVATE:
            raise ValueError(f"{access.value} should use private streamer.")
        instance = cls(ticker, exchange_name, market, access, stream, exchange_client = None)
        return instance

    async def connect(self):
        self._is_active = True
        socket_url = self.exchange_config['socket_url']
        #public endpoint:
        if self.access == Access.PUBLIC:
            final_socket_url = socket_url['public']            
            while self._is_active and final_socket_url:
                try:
                    async with connect(final_socket_url, ping_interval = None) as websocket:
                        self.ws = websocket
                        logging.info(f"{self.exchange} connects to {self.market.value} public websocket success!")
                        await self.subscribe()
                        await asyncio.gather(
                            self._ping_manager(),
                            self._message_handler()
                            )
                except Exception as e:
                    logging.error(f"{self.exchange} connect failed: {e}. Reconnecting immediately...")
        #private endpoint: spot.private
        elif self.access == Access.PRIVATE and self.market == Market.SPOT:
            socket_url_template = Template(socket_url['private'])
            listen_key = await self.exchange_client.generate_listen_key()
            print(f"debug in datastreamer, my liseten key: {listen_key}")
            while self._is_active:
                try:
                    with listen_key.get_secret().get() as secret:
                        async with connect(socket_url_template.substitute(listenKey = secret), ping_interval=None) as websocket:
                            self.ws = websocket
                            logging.info(f"{self.exchange_name} connects to {self.market.value} private websocket success!")
                            await self.subscribe()
                            await asyncio.gather(
                                self._ping_manager(),
                                self._message_handler()
                                )
                except Exception as e:
                    logging.error(f"{self.exchange} connect failed: {e}. Reconnecting immediately...")
        #private endpoint: future.private
        elif self.access == Access.PRIVATE and self.market == Market.FUTURES:
            final_socket_url = socket_url['private']
            while self._is_activate and final_socket_url:
                try:
                    async with connect(final_socket_url, ping_interval = None) as websocket:
                        self.ws = websocket
                        await self.ws.send(json.dumps(self.future_login_msg()))
                        logging.info(f"{self.exchange_name} future private login success!")
                        await self.subscribe()
                        await asyncio.gather(
                            self._ping_manager(),
                            self._message_handler()
                        )
                except Exception as e:
                    logging

    async def future_login_msg(self):
        if self._is_active and self.market == Market.FUTURE and self.access == Access.PRIVATE and self.exchange_client:
            try:
                future_login_msg = await self.exchange_client.future_market_login_msg()
                print(f"dubbug future login msg: {future_login_msg}")
                return future_login_msg
            except Exception as e:
                logging.error(f"{self.exchange_name} {self.market.value} {self.access.value} stream failed on exception in generating login msg:{e}.")

    async def subscribe(self):
        #ticker string validation
        left, right = self.ticker.split("/")
        spot_symbol = left.upper() + right.upper()
        future_symbol = left.upper() +"_"+right.upper()
        if not self.ws:
            logging.error(f"{self.exchange} is not connected yet while trying to make subscription.") 
        #topics: spot public 
        if self.access == Access.PUBLIC and self.market == Market.SPOT:
            params = []
            for item in self.stream:
                param_template = Template(self.exchange_config['topic_template']['public'][item.value]).substitute(symbol=spot_symbol)
                params.append(param_template)
            topics = {"method": "SUBSCRIPTION", "params": params}
            if self.ws and params:
                try:
                    await self.ws.send(json.dumps(topics))
                except Exception as e:
                    logging.error(f"{self.exchange_name} subscription {topics} failed: {e}.")
                    raise
            else:
                logging.error(f"{self.exchange_name} spot public topics generation failed on exception: {e}.")
        #topics: spot private
        elif self.market == Market.SPOT and self.access == Access.PRIVATE:
            params = []
            for item in self.stream:
                param = self.exchange_config['topic_template']['private'][item.value]
                params.append(param)
            topics = {"method": "SUBSCRIPTION", "params": params}
            if self.ws and params:
                try:
                    await self.ws.send(json.dumps(topics))
                except Exception as e:
                    logging.error(f"{self.exchange_name} spot private topics generation failed on exception: {e}.")
        #topics: future public 
        elif self.market == Market.FUTURE and self.access == Access.PUBLIC:
            topics = []
            for item in self.stream:
                topic_template = Template(self.exchange_config['topic_template']['public'][item.value]).substitute(symobl = future_symbol)
                topics.append(topic_template)
            if self.ws and topics:
                for topic in topics:
                    try:
                        await self.ws.send(json.dumps(topic))
                    except Exception as e:
                        logging.error(f"{self.exchange_name} future public topic {topic} fail subscription on exception: {e}.")
        elif self.market == Market.FUTURE and self.access == Access.PRIVATE:
            topics = []
            for item in self.stream:
                topic = self.exchange_config['topic_template']['private'][item.value]
                topics.append(topic)
            if self.ws and topics:
                for topic in topics:
                    try:
                        await self.ws.send(json.dumps(topic))
                    except Exception as e:
                        logging.error(f"{self.exchange_name} future private {topic} subscription fail on exception: {e}")

    @abstractmethod
    async def _message_handler(self):
        pass

    async def _ping_manager(self):
        if not (self.exchange_config['ping_message'] and self.exchange_config['ping_interval']):
            return
        while self._is_active:
            try:
                await asyncio.gather(
                self.ws.send(json.dumps(self.exchange_config['ping_message'])),
                asyncio.sleep(int(self.exchange_config['ping_interval']))
                )
            except Exception as e:
                logging.error(f"{self.exchange} conenction manager failed pinging (retry immediately).")
                await asyncio.sleep(0)

    async def safe_close(self) -> None:
        self._is_active = False
        if hasattr(self, 'ws') and self.ws:
            try:
                if not hasattr(self.ws, 'closed'):
                    await self.ws.close(code=1000)
                logging.info(f"{self.exchange} websocket closed safely.")
            except Exception as e:
                logging.error(f"{self.exchange} websocket closing on exception: {e}.")
            finally:
                self.ws = None
        if hasattr(self, 'exchange_client') and self.exchange_client:
            try:
                await self.exchange_client.close_session()
            except Exception as e:
                logging.error(f"{self.exchange} aio client close failed on exception: {e}.")
