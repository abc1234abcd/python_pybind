import ctypes
from cryptography.fernet import Fernet
from dotenv import dotenv_values

# memory safety
class SafeString:
    def __init__(self, value:str):
        if not isinstance(value, str):
            raise TypeError("only string is allowed.")
        self._buffer = ctypes.create_string_buffer(value.encode('utf-8'))
    def get(self) -> str:
        try:
            return self._buffer.value.decode('utf-8')
        finally:
            #clear buffer
            if hasattr(self, '_buffer'):
                ctypes.memset(self._buffer, 0, len(self._buffer))
    #garbage
    def __del__(self):
        ctypes.memset(self._buffer, 0, len(self._buffer))

#secret encryption
class SecuirtyManager:
    def __init__(self, secret: str):
        self._cipher = Fernet(dotenv_values(".env")["FERNET_KEY"].encode())
        self._encrypt_secret = self._cipher.encrypt(secret.encode('utf-8'))
    def get_secret(self) -> str:
        decrypted = self._cipher.decrypt(self._encrypt_secret)
        return SafeString(decrypted.decode('utf-8'))