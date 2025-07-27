import asyncio
import logging
from queue import Queue
from utils.data_class import Exchange
from utils.mexc_user_listen_key import mexc_sign_message, mexc_generate_listen_key, put_mexc_listen_key, delete_mexc_listen_key

from proto_wrapper_mexc import PushDataV3ApiWrapper



#lisenKey valid 60 mins, doing a PUT extend anthor 60 mins, doinga  delete will invalid the key

class UserDataStreamer:
    def __init__(self, exchange: str, queue: Queue):
        self.exchange = Exchange(exchange.lower())
        self.queue = queue
        


