import asyncio
import logging
import json
import time
from websockets import connect
from string import Template
from utils.data_class import Exchange
from typing import Dict, Tuple
from multiprocessing import Porcess, Queue as MQueue
from queue import Queue
from dotenv import dotenv_values
from proto_wrapper_mexc import PushDataV3ApiWrapper
from utils.mexc_user_listen_key import mexc_generate_listen_key, delete_mexc_listen_key
from security import SafeString, SecuirtyManager

def create_user_data_streamer(exchange: str):

    #init encrypted secrets by exchange.
    api_key_manager = SecuirtyManager(dotenv_values(".env")[exchange.upper()]["API_KEY"])
    secret_manager = SecuirtyManager(dotenv_values(".env")[exchange.upper()]["SECRET"])
    #listenKey is exchange specific
    listenKey_manager = SecuirtyManager(mexc_generate_listen_key(api_key = api_key_manager.get_secret(), api_secret =secret_manager.get_secret()))

    class UserDataStreamer:
        #memory safe: auto-clear 
        @property
        def api_key(self) ->SafeString:
            return api_key_manager.get_secret()
        @property
        def secret(self) -> SafeString:
            return secret_manager.get_secret()
        @property
        def listenKey_credential(self) -> SafeString:
            return listenKey_manager.get_secret()
        
        #Construct UserDateStreamer
        def __init__(self, queue: Queue, topics: Dict[str]):
            self.exchange = Exchange(exchange.lower())
            self.topics = topics
            self.queue = queue
            self.ws = None
            self._is_active = False

        async def connect(self):
            self._is_active = True
            while self._is_active:
                try:
                    async with connect(Template(self.exchange.private_socket_url_template).substitute(listenKey = self.listenKey_credential), ping_message = None) as private_websocket:
                        self.ws = private_websocket
                        logging.info(f"{self.exchange.name} connects to private socket success!")
                        await self.subscribe()
                        await asyncio.gather(
                            self._listenKey_manager(),
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
        #mexc lisenKey valid for 24 hrs after successful connection. I do not need this just yet.
        async def _listenKey_manager(self):
            if not self.ws or not self._is_active:
                del self.listenKey_credential

        async def _connection_manager(self):
            if not (self.exchange.ping_message and self.exchange.ping_interval):
                return
            while self._is_active:
                try:
                    ping_start_time = time.perf_counter()
                    await self.ws.send(json.dumps(self.exchange.ping_message))
                    elapsed = time.perf_counter() - ping_start_time
                    #hardcoded inteval[int] takes seconds as unit
                    ping_interval_integer = 60
                    ping_precise_sleep_time = max(0, ping_interval_integer - elapsed)
                    await asyncio.sleep(ping_precise_sleep_time)
                except Exception as e:
                    logging.error(f"{self.exchange.name} conenction manager failed pinging (retry in 2s).")
                    await asyncio.sleep(2)
        async def message_decoder_cplus(self):
            msg_protobuf_holder = PushDataV3ApiWrapper()
            while self._is_active and self.ws:
                try:
                    msg = await self.ws.recv()                
                    if isinstance(msg, bytes):
                        if msg_protobuf_holder.parse(msg):
                            print(f"Channel: {msg_protobuf_holder.channel}")
                            if msg_protobuf_holder.has_account_update():
                                account_update = msg_protobuf_holder.account_update()
                                print(f"account update:  time: {account_update.time}, balance: {account_update.balance_amount}, balance change: {account_update.balance_amount_change}")
                            elif msg_protobuf_holder.has_private_deal():
                                private_deal = msg_protobuf_holder.private_deal()
                                print(f"private deals: {private_deal}")
                            elif msg_protobuf_holder.has_private_order():
                                private_order = msg_protobuf_holder.private_order()
                                print(f"private order: {private_order}")
                            else:
                                logging.error("Message parsed but no recognized data type")
                        else:
                            logging.error("Failed to parse protobuf message")
                    else:
                        logging.error(f"Non-bytes message: {msg}")
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
            #delete plain-text listenKey from mexc server
            if self.listenKey_credential:
                try:
                    await delete_mexc_listen_key(api_key = self.credentials[0], api_secret=self.credentials[1], listen_key=self.listenKey_credential)
                    logging.info("listenKey is deleted from mexc server. ")
                except Exception as e:
                    logging.error(f"listenkey delete failed on exception: {e}.")


                
        




