import asyncio
import logging
from queue import Queue
from websockets import connect
from string import Template
from utils.data_class import Exchange
from typing import Dict
from utils.mexc_user_listen_key import mexc_sign_message, mexc_generate_listen_key, put_mexc_listen_key, delete_mexc_listen_key

from proto_wrapper_mexc import PushDataV3ApiWrapper

#spot_account_upate, spot_account_deals, spot_account_orders

#lisenKey valid 60 mins, doing a PUT extend anthor 60 mins, doinga  delete will invalid the key

class UserDataStreamer:
    def __init__(self, exchange: str, queue: Queue, topics: Dict[str]):
        self.exchange = Exchange(exchange.lower())
        self.queue = queue
        self.ws = None
        self._is_active = False
        

        async def connect(self):
            self._is_active = True
            while self._is_active:
                try:
                    async with connect(private_socket_url, ping_interval = None) as private_websocket:
                        self.ws = private_websocket
                        logging.info(f"{self.exchange.name} connects to private socket success!")
                        await self.subscribe()
                        await asyncio.gather(

                        )
                except Exception as e:
                    logging.error(f"{self.exchange.name} connect to private websocket failed: {e}. Reconnecting immediately...")
        async def subscribe(self):
            if not self.ws:
                logging.error(f"{self.exchange.name} is not connected yet while trying to make subscription.")




