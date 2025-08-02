import requests
from cryptography.fernet import Fernet
from utils.security import SecuirtyManager
from dotenv import dotenv_values
from pathlib import Path

key = Fernet.generate_key()
cipher = Fernet(key)


