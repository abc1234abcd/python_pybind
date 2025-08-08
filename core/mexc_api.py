import requests
import logging
import hmac
import time
import urllib.parse
from typing import Dict, Any, Optional
from hashlib import sha256
from utils.security import SecurityManager
from utils.data_class import OrderSide, OrderType


class MexcApiClient:
    def __init__(self, api_key: SecurityManager, api_secret: SecurityManager, timeout: tuple =(0.5, 0.8), pool_config: dict = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_base_url = "https://api.mexc.com"
        self.timeout = timeout
        #pool config: allow queued connections, fast fail, non-block if pool full.
        default_pool_config = {
            'pool_connections': 5,
            'pool_maxsize': 10,
            'max_retries': 0,
            'pool_block': False
        }
        if pool_config:
            default_pool_config.update(pool_config)
        adapter = requests.adapters.HTTPAdapter(**default_pool_config)
        self.session = requests.Session()
        self.session.mount('https://', adapter)
        self.session.headers = None

    @property
    def headers(self):
        if not self.session.headers:
            with self.api_key.get_secret().get() as key:
                self.session.headers ={"X-MEXC-APIKEY": key}
        return self.session.headers
    
    def _sign_message(self, params: dict) -> Dict[str, Any]:
        #fast copy
        totalParams = {**params}
        if 'timestamp' not in totalParams:
            totalParams['timestamp'] = int(time.time()*1000)
        query_string = urllib.parse.urlencode(sorted(totalParams.items()))
        if 'signature' in params:
            logging.warning(f"{totalParams} is already signed.")
        with self.api_secret.get_secret().get() as secret:
            totalParams['signature'] = hmac.new(secret.encode('utf-8'), query_string.encode('utf-8'), sha256).hexdigest()
        return totalParams
    
    def generate_listen_key(self) -> SecurityManager:
        url_path = "/api/v3/userDataStream"
        totalParams = self._sign_message(params = {})
        try: 
            request = requests.Request('POST', self.api_base_url+url_path, headers = self.session.headers, params = totalParams).prepare()
            response = self.session.send(request, timeout = self.timeout)
            response.raise_for_status()
            return SecurityManager(mexc_listen_key = request.json()['listenKey'])
        except Exception as e:
            logging.error(f"mexc generate listen key failed on exception: {e}.")
    
    def put_listen_key(self, listenKey: SecurityManager) -> bool:
        url_path = "/api/v3/userDataStream"
        with listenKey.get_secret().get() as listen_key:
            params = {'listenKey': listen_key}
            totalParams = self._sign_message(params = params)
            try:
                request = requests.Request('PUT', self.api_base_url + url_path, headers = self.session.headers, params = totalParams).prepare()
                response = self.session.send(request, timeout = self.timeout)
                response.raise_for_status()
                return response.json()['listenKey'] == listen_key
            except Exception as e:
                logging.error(f"put listen key fail on exception: {e}.")
                return False
        
    def delete_listen_key(self, listenKey: SecurityManager) -> bool:
        url_path = "/api/v3/userDataStream"
        with listenKey.get_secret().get() as listen_key:
            params = {'listenKey': listen_key}
            totalParams = self._sign_message(params = params)
            try:
                request = requests.Request('DELETE', self.api_base_url + url_path, headers = self.session.headers, params = totalParams).prepare()
                response = self.session.send(request, timeout = self.timeout)
                response.raise_for_status()
                return response.json(['listenKey']) == listen_key
            except Exception as e:
                logging.error(f"delete listen key failed on exception: {e}")
                return False
    
    def submit_orders(self, params: dict, quantity: Optional[float] = None, quoteOrderQty: Optional[float] = None, price: Optional[float] = None, newClientOrderId: Optional[str] = None, recvWindow: Optional[int] = None) -> dict:
        url_path = "/api/v3/order/test"
        if quantity is not None:
            params['quantity'] = quantity
        if quoteOrderQty is not None:
            params['quoteOrderQty'] = quoteOrderQty
        if price is not None:
            params['price'] = price
        if newClientOrderId is not None:
            params['newClientOrderId'] = newClientOrderId
        if recvWindow is not None:
            params['recvWindow'] = recvWindow
        totalParams = self._sign_message(params = params)
        try:
            request = requests.Request('POST', self.api_base_url + url_path, headers = self.session.headers, params = totalParams).prepare()
            response = self.session.send(request, timeout = self.timeout, allow_redirects=False)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"mexc make order failed on exception: {e}.")
            raise
    
    def cancel_order(self, symbol: str, orderId: Optional[str], origClientOrderId: Optional[str], newClientOrderId: Optional[str], recvWindow: Optional[int]) -> dict:
        url_path = "/api/v3/order"
        params = {
            "timestamp": int(time.time()*1000),
            "symbol": symbol.upper(),
        }
        if orderId is not None:
            params['orderId'] = orderId 
        if origClientOrderId is not None:
            params['origClientOrderId'] = origClientOrderId
        if newClientOrderId is not None:
            params['newClientOrderId'] = newClientOrderId
        if recvWindow is not None:
            params['recvWindow'] = recvWindow
        totalParams = self._sign_message(params = params)
        try:
            request = requests.Request('POST', self.api_base_url + url_path, headers = self.session.headers, params = totalParams).prepare()
            response = self.session.send(request, timeout = self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"mexc cancel order failed on exception: {e}.")
    
    def cancel_all_orders(self, symbol: str, recvWindow: Optional[int]) -> dict:
        url_path = "/api/v3/openOrders"
        #symbol	maximum input 5 symbols,separated by ",". e.g. "BTCUSDT,MXUSDT,ADAUSDT"
        params = {
            "timestamp": int(time.time()*1000),
            "symbol": symbol.upper(),
        }
        if recvWindow is not None:
            params['recvWindow'] = recvWindow
        totalParams = self._sign_message(params = params)
        try:
            req = requests.Request('DELETE',self.api_base_url + url_path, headers = self.session.headers, params = totalParams).prepare()
            response = self.session.send(req, timeout= self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"mexc cancel all order failed on exception: {e}.")

    def order_status(self, orderId: str) -> dict:
        url_path = "/api/v3/order"
        try:
            params = {'timestamp': int(time.time()*1000), 'orderId': orderId}
            req = requests.Request('GET', self.api_base_url + url_path, headers = self.session.headers, params = params).prepare()
            response = self.session.send(req, timeout = self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error("mexc order status enquiry failed on exceptio: {e}.")

        



