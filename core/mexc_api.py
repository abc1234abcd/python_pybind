import requests
import logging
import hmac
import time
import urllib.parse
from typing import Dict, Any, Optional
from decimal import Decimal
from hashlib import sha256
from utils.security import SecurityManager
from utils.data_class import OrderSide, OrderType
from dotenv import dotenv_values
from pathlib import Path


class MexcApiClient:
    def __init__(self, api_key: SecurityManager, api_secret: SecurityManager, timeout: tuple =(1, 2), pool_config: dict = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_base_url = "https://api.mexc.com"
        self.timeout = timeout
        #pool config: allow queued connections, fast fail, non-block if pool full.
        default_pool_config = {
            'pool_connections': 10,
            'pool_maxsize': 20,
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
        if not hasattr(self.session, 'headers') or not self.session.headers:
            with self.api_key.get_secret().get() as key:
                self.session.headers = {
                    "X-MEXC-APIKEY": key,
                    "Content-Type": "application/json"
                }
        return self.session.headers
    
    def _sign_message(self, params: dict) -> Dict[str, Any]:
        totalParams = {**params}
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
            headers = self.headers
            request = requests.Request('POST', self.api_base_url+url_path, headers = headers, params = totalParams).prepare()
            response = self.session.send(request, timeout = self.timeout)
            response.raise_for_status()
            return SecurityManager(response.json()['listenKey'])
        except Exception as e:
            logging.error(f"mexc generate listen key failed on exception: {e}.")
    
    def put_listen_key(self, listenKey: SecurityManager) -> bool:
        url_path = "/api/v3/userDataStream"
        with listenKey.get_secret().get() as listen_key:
            params = {'listenKey': listen_key}
            totalParams = self._sign_message(params = params)
            try:
                headers = self.headers
                request = requests.Request('PUT', self.api_base_url + url_path, headers = headers, params = totalParams).prepare()
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
                headers = self.headers
                request = requests.Request('DELETE', self.api_base_url + url_path, headers = headers, params = totalParams).prepare()
                response = self.session.send(request, timeout = self.timeout)
                response.raise_for_status()
                return response.json(['listenKey']) == listen_key
            except Exception as e:
                logging.error(f"delete listen key failed on exception: {e}")
                return False
    
    def submit_orders(self, params: dict) -> dict:
        url_path = "/api/v3/order"
        totalParams = self._sign_message(params = params)
        try:
            headers = self.headers
            request = requests.Request('POST', self.api_base_url + url_path, headers = headers, params = totalParams).prepare()
            response = self.session.send(request, timeout = self.timeout, allow_redirects=False)
            return response.json()
        except Exception as e:
            logging.error(f"mexc make order failed on exception: {e}.")
            raise
    
    def cancel_order(self, symbol: str, orderId: Optional[str], origClientOrderId: Optional[str], newClientOrderId: Optional[str], recvWindow: Optional[int]) -> dict:
        url_path = "/api/v3/order/test"
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
            headers = self.headers
            request = requests.Request('POST', self.api_base_url + url_path, headers = headers, params = totalParams).prepare()
            response = self.session.send(request, timeout = self.timeout)
            return response.json()
        except Exception as e:
            logging.error(f"mexc cancel order failed on exception: {e}.")
    
    def cancel_all_orders(self, symbol: str, recvWindow: Optional[int]) -> dict:
        url_path = "/api/v3/openOrders"
        #symbol	maximum input 5 symbols,separated by ",". e.g. "BTCUSDT,MXUSDT,ADAUSDT"
        params = {
            "symbol": symbol.upper(),
            "timestamp": str(int(time.time()*1000)),
        }
        if recvWindow is not None:
            params['recvWindow'] = recvWindow
        totalParams = self._sign_message(params = params)
        try:
            headers = self.headers
            req = requests.Request('DELETE',self.api_base_url + url_path, headers = headers, params = totalParams).prepare()
            response = self.session.send(req, timeout= self.timeout)
            return response.json()
        except Exception as e:
            logging.error(f"mexc cancel all order failed on exception: {e}.")

    def order_status(self, orderId: str) -> dict:
        url_path = "/api/v3/order"
        try:
            headers= self.headers
            params = {'orderId': orderId, 'symbol': 'SOLUSDT', 'timestamp': str(int(time.time()*1000))}
            totalParams = self._sign_message(params = params)
            req = requests.Request('GET', self.api_base_url + url_path, headers = headers, params = totalParams).prepare()
            response = self.session.send(req, timeout = self.timeout)
            return response.json()
        except Exception as e:
            logging.error("mexc order status enquiry failed on exceptio: {e}.")
    
    def account_balance(self) -> float:
        url_path = '/api/v3/account'
        try:
            params = {'timestamp': int(time.time()*1000)}
            totalParams = self._sign_message(params = params)
            headers = self.headers
            req = requests.Request("GET", self.api_base_url + url_path, headers = headers, params = totalParams).prepare()
            response = self.session.send(req, timeout = self.timeout)
            balances = response.json().get('balances', [])
            usdt_balance = next((float(b['free']) + float(b['locked']) for b in balances if b['asset'] == 'USDT'),0.0)
            return float(usdt_balance)
        except Exception as e:
            logging.error(f"mexc get account balance failed on exception: {e}.")
    
    def get_exchange_info(self, symbol: str) -> dict:
        url_path = '/api/v3/exchangeInfo'
        try:
            params ={"symbol": symbol}
            req = requests.Request("GET", self.api_base_url + url_path, params = params).prepare()
            response = self.session.send(req, timeout=self.timeout)
            return response.json()
        except Exception as e:
            logging.error(f"get exchange info failed on exception: {e}.")

    def get_default_symbol(self) -> dict:
        url_path = '/api/v3/selfSymbols'
        try:
            headers = self.headers
            totalParams = self._sign_message(params = {})
            req = requests.Request("GET", self.api_base_url + url_path, headers = headers,  params = totalParams).prepare()
            response = self.session.send(req, timeout=self.timeout)
            return response.json()
        except Exception as e:
            logging.error(f"get exchange info failed on exception: {e}.")

