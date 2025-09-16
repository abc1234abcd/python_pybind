import aiohttp
import asyncio
import logging
import hmac
import time
import urllib.parse
from typing import Dict, Any, Optional, List
from hashlib import sha256
from utils.security import SecurityManager
from utils.data_class import OrderSide, OrderType
from pathlib import Path
from dotenv import dotenv_values

class AioMexcApiClient:
    def __init__(self, api_key: SecurityManager, api_secret: SecurityManager, timeout: tuple = (1, 2), pool_config: dict = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_base_url = "https://api.mexc.com"
        self.timeout = aiohttp.ClientTimeout(total=timeout[0], connect=timeout[1])
        # aiohttp connection pool configuration
        connector_args = {
            'limit': 20,  
            'limit_per_host': 10,  
        }
        if pool_config:
            connector_args.update({
                'limit': pool_config.get('pool_maxsize', 20),
                'limit_per_host': pool_config.get('pool_connections', 10),
            })
        
        self.connector = aiohttp.TCPConnector(**connector_args)
        self.session = None
        self.headers = None
        
    async def __aenter__(self):
        await self.create_session()
        return self
    async def __aexit__(self):
        await self.close_session()
    async def create_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession(
                connector=self.connector,
                timeout=self.timeout,
                headers = self.headers
            )
    async def close_session(self):
        if self.session:
            await self.session.close()
            self.session = None
   
    async def get_headers(self):
        if self.headers is None:
            with self.api_key.get_secret().get() as key:
                self.headers = {
                    "X-MEXC-APIKEY": key,
                    "Content-Type": "application/json"
                }
        return self.headers
    def _sign_message(self, params: dict) -> Dict[str, Any]:
        totalParams = {**params}
        query_string = urllib.parse.urlencode(sorted(totalParams.items()))
        if 'signature' in params:
            logging.warning(f"{totalParams} is already signed.")
        with self.api_secret.get_secret().get() as secret:
            totalParams['signature'] = hmac.new(
                secret.encode('utf-8'), 
                query_string.encode('utf-8'), 
                sha256
            ).hexdigest()
        return totalParams
    async def _make_request(self, method: str, url_path: str, headers: dict = None, params: dict = None) -> dict:
        if self.session is None:
            await self.create_session()
        url = self.api_base_url + url_path
        try:
            async with self.session.request(
                method=method.upper(),
                url=url,
                headers = headers,
                params=params
            ) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            logging.error(f"Request failed: {e}")
            raise
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            raise
    async def generate_listen_key(self) -> SecurityManager:
        url_path = "/api/v3/userDataStream"
        totalParams = self._sign_message(params={'timestamp': str(int(time.time()*1000))})
        headers = await self.get_headers()
        try:
            result =await self._make_request('POST', url_path, headers = headers, params=totalParams)
            return SecurityManager(result['listenKey'])
        except Exception as e:
            logging.error(f"mexc generate listen key failed on exception: {e}.")
            raise
    async def put_listen_key(self, listenKey: SecurityManager) -> bool:
        url_path = "/api/v3/userDataStream"
        with listenKey.get_secret().get() as listen_key:
            params = {'listenKey': listen_key, 'timestamp': str(int(time.time()*1000))}
            totalParams = self._sign_message(params=params)
            headers = await self.get_headers()
            try:
                result = await self._make_request('PUT', url_path, headers = headers, params=totalParams)
                return result['listenKey'] == listen_key
            except Exception as e:
                logging.error(f"put listen key fail on exception: {e}.")
                return False
    async def delete_listen_key(self, listenKey: SecurityManager) -> bool:
        url_path = "/api/v3/userDataStream"
        with listenKey.get_secret().get() as listen_key:
            params = {'listenKey': listen_key, 'timestamp':str(int(time.time()*1000))}
            totalParams = self._sign_message(params=params)
            headers = await self.get_headers()
            try:
                result = await self._make_request('DELETE', url_path, headers = headers, params=totalParams)
                return result.get('listenKey') == listen_key
            except Exception as e:
                logging.error(f"delete listen key failed on exception: {e}")
                return False
    async def submit_orders(self, params: dict) -> dict:
        url_path = "/api/v3/order"
        totalParams = self._sign_message(params=params)
        print(totalParams)
        headers = await self.get_headers()
        print(headers)
        try:
            return await self._make_request('POST', url_path, headers = headers, params=totalParams)
        except Exception as e:
            logging.error(f"mexc make order failed on exception: {e}.")
            raise

    async def cancel_order(self, symbol: str, orderId: Optional[str], origClientOrderId: Optional[str], newClientOrderId: Optional[str], recvWindow: Optional[int]) -> dict:
        url_path = "/api/v3/order/test"
        params = {
            "timestamp": int(time.time() * 1000),
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
            
        totalParams = self._sign_message(params=params)
        headers = await self.get_headers()
        try:
            return await self._make_request('POST', url_path, params=totalParams)
        except Exception as e:
            logging.error(f"mexc cancel order failed on exception: {e}.")
            raise
    async def cancel_all_orders(self, symbol: str, recvWindow: Optional[int]) -> dict:
        url_path = "/api/v3/openOrders"
        params = {
            "symbol": symbol.upper(),
            "timestamp": str(int(time.time() * 1000)),
        }
        if recvWindow is not None:
            params['recvWindow'] = recvWindow
            
        totalParams = self._sign_message(params=params)
        try:
            return await self._make_request('DELETE', url_path, params=totalParams)
        except Exception as e:
            logging.error(f"mexc cancel all order failed on exception: {e}.")
            raise
    async def order_status(self, orderId: str) -> dict:
        url_path = "/api/v3/order"
        params = {
            'orderId': orderId, 
            'symbol': 'XRPUSDT', 
            'timestamp': str(int(time.time() * 1000))
        }
        totalParams = self._sign_message(params=params)
        headers = await self.get_headers()
        try:
            return await self._make_request('GET', url_path, headers = headers, params=totalParams)
        except Exception as e:
            logging.error(f"mexc order status enquiry failed on exception: {e}.")
            raise
    async def account_balance(self) -> float:
        url_path = '/api/v3/account'
        params = {'timestamp': int(time.time() * 1000)}
        totalParams = self._sign_message(params=params)
        
        try:
            result = await self._make_request('GET', url_path, params=totalParams)
            balances = result.get('balances', [])
            usdt_balance = next((float(b['free']) + float(b['locked']) for b in balances if b['asset'] == 'USDT'), 0.0)
            return float(usdt_balance)
        except Exception as e:
            logging.error(f"mexc get account balance failed on exception: {e}.")
            raise

    async def get_exchange_info(self, symbol: str) -> dict:
        url_path = '/api/v3/exchangeInfo'
        params = {"symbol": symbol}
        
        try:
            return await self._make_request('GET', url_path, params=params)
        except Exception as e:
            logging.error(f"get exchange info failed on exception: {e}.")
            raise

    async def get_default_symbol(self) -> dict:
        url_path = '/api/v3/selfSymbols'
        totalParams = self._sign_message(params={})
        try:
            return await self._make_request('GET', url_path, params=totalParams)
        except Exception as e:
            logging.error(f"get exchange info failed on exception: {e}.")
            raise

    async def get_hist_kline(self, symbol: str, interval: str) -> List:
        url_path = '/api/v3/klines'
        params = {
            "symbol": symbol.upper(),
            "timestamp": str(int(time.time() * 1000)),
            "interval": interval
        }
        try:
            return await self._make_request('GET', url_path, params=params)
        except Exception as e:
            logging.error(f"get historical kline failed on exception: {e}.")
            raise
'''
if __name__=='__main__':
    async def run_client():
        api_key = SecurityManager(dotenv_values(Path(__file__).parent.parent/".env")[f"MEXC_API_KEY"])
        api_secret = SecurityManager(dotenv_values(Path(__file__).parent.parent/".env")[f"MEXC_SECRET"])
        symbol = "XRPUSDT"
        interval = '1m'
        buy_order = {
            "quoteOrderQty":  "1",  
            "side": OrderSide.BUY.value,
            "symbol": "XRPUSDT",
            "timestamp": str(int(time.time()*1000)),  
            "type": OrderType.MARKET.value
        }
        #mexchttpclient_instance = MexcApiClient(api_key=api_key, api_secret=api_secret, timeout=tuple((10,20)))
        #http_kline = mexchttpclient_instance.generate_listen_key()
        #print(f"http kline:{ http_kline}")
        mexcapiclient_instance = AioMexcApiClient(api_key=api_key, api_secret = api_secret, timeout=tuple((10, 20)))
        #headers = await self.get_headers()
        try:
            # Create session manually
            await mexcapiclient_instance.create_session()
            # Use await for the async method
            return_data = await mexcapiclient_instance.order_status(orderId = "C02__596646700169351168099")
            print(f"aio Kline data: {return_data}")
            
            # You can make more async calls here
            # balance = await mexcapiclient_instance.account_balance()
            # print(f"Balance: {balance}")
                
        finally:
            # Always close the session
            await mexcapiclient_instance.close_session()

asyncio.run(run_client())
'''