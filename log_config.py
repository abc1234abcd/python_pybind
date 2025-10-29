import logging
from pathlib import Path 
from datetime import datetime

def configure_logging():
    log_file_path = Path(__file__).parent/'logs'/f"bot_{datetime.now().strftime('%Y-%m-%d')}.log"
    logging.basicConfig(
        filename = str(log_file_path),
        format = "%(asctime)s %(levelname)-7s%(message)s",
        level = logging.INFO,
        datefmt="%Y-%m-%D %H:%M:%S"
    )
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(console_handler)

