import asyncio
import logging
import json
from websockets import connect
from string import Template
from utils.data_class import Exchange
from typing import List
from queue import Queue
from proto_wrapper_mexc import PushDataV3ApiWrapper
from core.mexc_api import MexcApiClient
from utils.security import SecurityManager

class UserDataStreamer:
    def __init__(self, exchange: str, queue: Queue, topics: List[dict], api_key: SecurityManager, api_secret: SecurityManager):
        self.exchange = Exchange(exchange.lower())
        self.topics = topics
        self.queue = queue
        self.api_key = api_key
        self.api_secret = api_secret
        self.ws = None
        self._is_active = False
        self.listen_key = self._create_encrypted_listen_key()

    def _create_encrypted_listen_key(self):
        with self.api_key.get_secret().get() as key, self.api_secret.get_secret().get() as secret:
            return SecurityManager(mexc_generate_listen_key(api_key=key, api_secret=secret))
        
    async def connect(self):
        self._is_active = True
        while self._is_active:
            try:  
                #use encrypted secret as utils.SafeString for memory safety
                with self.listen_key.get_secret().get() as listenKey:
                    async with connect(Template(self.exchange.private_socket_url_template).substitute(listenKey = listenKey), ping_interval=60) as private_websocket:
                        self.ws = private_websocket
                        logging.info(f"{self.exchange.name} private socket connects successfully!")
                        await self.subscribe()
                        await asyncio.gather(
                            self._connection_manager(),
                            self.message_decoder_cplus(),
                        )
            except Exception as e:
                logging.error(f"{self.exchange.name} connect to private websocket failed: {e}. Reconnecting immediately...")
    async def subscribe(self):
        if not self.ws:
            logging.error(f"{self.exchange.name} is not connected yet while trying to make subscription.")
        if self.ws and self.topics:
            try:
                for topic in self.topics:
                    await self.ws.send(json.dumps(topic))
            except Exception as e:
                logging.error(f"{self.exchange.name} subscription failed on exception: {e}.")
                raise
    async def _connection_manager(self):
        while self._is_active:
            try:
                await self.ws.send(json.dumps(self.exchange.ping_message))
                await asyncio.sleep(30)
            except Exception as e:
                logging.error(f"{self.exchange.name} conenction manager failed pinging (retry in 1s).")
                await asyncio.sleep(1)
    async def message_decoder_cplus(self):
        while self._is_active and self.ws:
            try:
                msg = await self.ws.recv() 
                print(msg) 
            except Exception as e:
                logging.error(f"cplus message decoder error:{e}.")
                await asyncio.sleep(1)  
    async def safe_close(self):
        self._is_active = False
        if hasattr(self, 'ws') and self.ws:
            try:
                if not self.ws.closed:
                    await self.ws.close(code = 100)
                logging.info(f"{self.exchange.name} private websocket safe closed.")
            except Exception as e:
                logging.error(f"{self.exchange.name} private socket safe closed failed on exception: {e}.")
            finally:
                self.ws = None
        #delete listenKey from mexc server and all secrets local memory
        if self.listen_key:
            try:
                with self.api_key.get_secret().get() as key, self.api_secret.get_secret().get() as secret, self.listen_key.get_secret().get() as listenKey:
                    delete_mexc_listen_key(api_key=key, api_secret=secret, listen_key=listenKey)
                    logging.info("listen key is deleted from server. ")
            except Exception as e:
                logging.error(f"listenkey delete failed on exception: {e}.")
            finally:
                del self.api_key, self.api_secret, self.listen_key
                    

                
        



