import ctypes
from contextlib import contextmanager
from typing import ContextManager, Generator
from cryptography.fernet import Fernet
from dotenv import dotenv_values
from pathlib import Path

# memory safety
class SafeString:
    def __init__(self, value:str):
        if not isinstance(value, str):
            raise TypeError("only string is allowed.")
        self._buffer = ctypes.create_string_buffer(value.encode('utf-8'))
    @contextmanager
    def get(self) -> Generator[str, None, None]: # [yield type, send type, return type]
        try:
            yield self._buffer.value.decode('utf-8')
        finally:
            if hasattr(self, '_buffer'):
                ctypes.memset(self._buffer, 0, len(self._buffer))
    #garbage
    def __del__(self):
        ctypes.memset(self._buffer, 0, len(self._buffer))

#secret encryption and use secret as SafeString
class SecuirtyManager:
    def __init__(self, secret: str):
        self._cipher = Fernet(dotenv_values(Path(__file__).parent.parent/".env")["FERNET_KEY"].encode())
        self._encrypt_secret = self._cipher.encrypt(secret.encode('utf-8'))
    def get_secret(self) -> SafeString:
        return SafeString(self._cipher.decrypt(self._encrypt_secret).decode())
            

         