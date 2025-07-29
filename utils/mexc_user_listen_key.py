import requests
import logging
import hmac
import urllib.parse
import time
from typing import Dict, Any
from hashlib import sha256

  
def mexc_sign_message(api_secret: str, params: Dict[str, Any]) -> Dict[str, Any]:
    totalParams = params.copy()
    if 'timestamp' not in totalParams:
        totalParams['timestamp'] = int(time.time()*1000)
    query_string = urllib.parse.urlencode(sorted(totalParams.items()))
    if 'signature' in params:
        logging.warning(f"{totalParams} is already signed.")
    totalParams['signature'] = hmac.new(api_secret.encode('utf-8'), query_string.encode('utf-8'), sha256).hexdigest()
    return totalParams
def mexc_generate_listen_key(api_key: str, api_secret: str) -> Dict[str, Any]:
    api_base_url = "https://api.mexc.com"
    url_path = "/api/v3/userDataStream"
    headers = {"X-MEXC-APIKEY": api_key}
    totalParams = mexc_sign_message(api_secret, params = {})
    request = requests.post(api_base_url+url_path, headers = headers, params = totalParams)
    if request.status_code != 200:
        logging.error("request user listen key failed: {request.status_code}.")
    mexc_listen_key = request.json()['listenKey']
    return mexc_listen_key
def put_mexc_listen_key(api_key: str, api_secret: str, listen_key: str) -> bool:
    base_url = "https://api.mexc.com"
    url_path = "/api/v3/userDataStream"
    headers = {"X-MEXC-APIKEY": api_key}
    params = {'listenKey': listen_key}
    totalParams = mexc_sign_message(api_secret, params)
    request = requests.put(base_url + url_path, headers = headers, params = totalParams)
    if request.status_code != 200:
        logging.error(f"listen key extension failed: {request.status_code}")
    req = request.json()
    if req['listenKey'] == listen_key:
        return True
    return False
def delete_mexc_listen_key(api_key:str, api_secret:str, listen_key: str) -> bool:
    base_url = "https://api.mexc.com"
    url_path = "/api/v3/userDataStream"
    headers = {"X-MEXC-APIKEY": api_key}
    params = {'listenKey': listen_key}
    totalParams = mexc_sign_message(api_secret, params)
    request = requests.delete(base_url + url_path, headers = headers, params = totalParams)
    if request.status_code != 200:
        logging.error(f"listen key deletion failed: {request.status_code}")
    req = request.json()
    if req['listenKey'] == listen_key:
        return True
    return False


