from mexc_api_client import MexcApiClient
import time
from typing import Dict, Any
from utils.security import SecurityManager
from dotenv import dotenv_values
from pathlib import Path

class UltraFastMexcClient:
    def __init__(self, api_key: SecurityManager, api_secret: SecurityManager):
        with api_key.get_secret().get() as key, api_secret.get_secret().get() as secret:
            self.cpp_client = MexcApiClient(key, secret)
        
    def submit_order(self, order_params: Dict[str, str]) -> Dict[str, Any]:

        start = time.perf_counter_ns()
        
        # Ensure all values are strings
        str_params = {k: str(v) if v is not None else "" for k, v in order_params.items()}
        
        result = self.cpp_client.submit_order(
            symbol=str_params["symbol"],
            side=str_params["side"],
            type=str_params["type"],
            quantity=str_params.get("quantity", ""),
            price=str_params.get("price", ""),
            quoteOrderQty=str_params.get("quoteOrderQty", "")
        )
        
        latency = (time.perf_counter_ns() - start) / 1e6
        print(f"Order executed in {latency:.2f}ms")
        return result
    
    def order_status(self, order_id: str, symbol: str) -> Dict[str, Any]:
        start = time.perf_counter_ns()
        result = self.cpp_client.order_status(
            orderId=str(order_id),
            symbol=str(symbol)
        )
        latency = (time.perf_counter_ns() - start) / 1e6
        print(f"Status checked in {latency:.2f}ms")
        return result

if __name__=='__main__':
    api_key = SecurityManager(dotenv_values(Path(__file__).parent.parent/".env")["MEXC_API_KEY"])
    api_secret = SecurityManager(dotenv_values(Path(__file__).parent.parent/".env")["MEXC_SECRET"])
    mexc_api_client = UltraFastMexcClient(api_key = api_key, api_secret=api_secret)
    sell_order = {
            "quantity": "0.059",  
            "side": "SELL",
            "symbol": "SOLUSDT",
            "timestamp": str(int(time.time()*1000)),  
            "type": "MARKET"
        }
    #resp = mexc_api_client.account_balance()
    orderId = 'C02__582526780620046337099'
    default_symbol = mexc_api_client.submit_order(params = sell_order)
    print(f"order status: {default_symbol}")