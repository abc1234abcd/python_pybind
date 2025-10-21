import asyncio
import json 
import logging 
from websockets import connect 
from utils.config_loader import ExchangeConfig
from utils.data_class import Market, DataType
from utils.security import SecurityManager
from typing import List, Any, Optional
from abc import ABC, abstractmethod
from string import Template
from aioapiclient import AioMexcApiClient

class DataStreamer(ABC):    

    @classmethod 
    def private_streamer(cls, exchange: str, market: Market, topics: List[Any], api_key: SecurityManager, api_secret: SecurityManager, exchange_client: AioMexcApiClient, timeout: tuple):
        return cls(exchange, market, DataType.PRIVATE, topics, api_key, api_secret, exchange_client, timeout)
    
    @classmethod
    def public_streamer(cls, exchange: str, market: Market, data_type: DataType, topics: List[Any]):
        if data_type == DataType.PRIVATE:
            raise ValueError(f"{data_type.value} should use private streamer.")
        return cls(exchange, market, data_type, topics, None, None)
    
    def __init__(self, exchange: str, market: Market, data_type: DataType, topics: List[Any], api_key: Optional[SecurityManager], api_secret: Optional[SecurityManager], exchange_client: Optional[AioMexcApiClient], timeout: Optional[tuple]):
        self.exchange = ExchangeConfig(exchange.lower(), market)
        self.data_type = data_type
        self.marekt = market
        self.topics = topics
        self.ws = None
        self._is_active = False
        self.api_key = api_key
        self.api_secret = api_secret
        self.exchange_client = AioMexcApiClient(api_key, api_secret, timeout)
        
    async def connect(self):
        self._is_active = True
        socket_url = self.exchange['socket_url']

        if self.data_type == DataType.PUBLIC:
            final_socket_url = socket_url['public']
            while self._is_active and final_socket_url:
                try:
                    async with connect(final_socket_url, ping_interval = None) as websocket:
                        self.ws = websocket
                        logging.info(f"{self.exchange.name} connects to public websocket success!")
                        await self.subscribe()
                        await asyncio.gather(
                            self._ping_manager(),
                            self._message_handler()
                            )
                except Exception as e:
                    logging.error(f"{self.exchange.name} connect failed: {e}. Reconnecting immediately...")

        elif self.data_type == DataType.PRIVATE and self.market == Market.SPOT:
            socket_url_template = Template(socket_url['private'])
            listen_key = await self.exchange_client.generate_listen_key()
            while self._is_active and socket_url_template:
                try:
                    with listen_key.get_secret().get() as secret:
                        async with connect(socket_url_template.substitute(listenKey = secret), ping_interval=None) as websocket:
                            self.ws = websocket
                            logging.info(f"{self.exchange.name} connects to public websocket success!")
                            await self.subscribe()
                            await asyncio.gather(
                                self._ping_manager(),
                                self._message_handler()
                                )
                except Exception as e:
                    logging.error(f"{self.exchange.name} connect failed: {e}. Reconnecting immediately...")
        elif self.data_type == DataType.PRIVATE and self.market == Market.FUTURES:
            #no config yet
            pass

    async def subscribe(self):
        if not self.ws:
            logging.error(f"{self.exchange.name} is not connected yet while trying to make subscription.") 
        if (self.topics and self.ws):
            try:
                for topic in self.topics:
                    await self.ws.send(json.dumps(topic))
            except Exception as e:
                logging.error(f"{self.exchange.name} subscription {topic} failed: {e}.")
                raise

    @abstractmethod
    async def _message_handler(self):
        pass

    async def _ping_manager(self):
        if not (self.exchange.spot_ping_message and self.exchange.ping_interval):
            return
        while self._is_active:
            try:
                await asyncio.gather(
                self.ws.send(json.dumps(self.exchange.spot_ping_message)),
                asyncio.sleep(self.exchange.ping_interval)
                )
            except Exception as e:
                logging.error(f"{self.exchange.name} conenction manager failed pinging (retry immediately).")
                await asyncio.sleep(0)

    async def safe_close(self) -> None:
        self._is_active = False
        if hasattr(self, 'ws') and self.ws:
            try:
                if not hasattr(self.ws, 'closed'):
                    await self.ws.close(code=1000)
                logging.info(f"{self.exchange.name} websocket closed safely.")
            except Exception as e:
                logging.error(f"{self.exchange.name} websocket closing on exception: {e}.")
            finally:
                self.ws = None
 
if __name__