import requests
from cryptography.fernet import Fernet
from security import SecuirtyManager
from dotenv import dotenv_values

key = Fernet.generate_key()
cipher = Fernet(key)


