import yaml
import logging
from pathlib import Path
from typing import Dict, Any

class ExchangeConfigLoader:
    @staticmethod
    def load_exchange_config(exchange: str) ->Dict[str, Any]:
        config_path = Path(__file__).parent.parent/'config'/'exchanges.yaml'
        try:
            full_path = Path(config_path).resolve()
            if not full_path.exists():
                logging.error(f"Config file is not found at:{full_path}.")
            with open(full_path) as file:
                exchanges_config = yaml.safe_load(file) or {}
                if exchange not in exchanges_config['exchanges']:
                    logging.error(f"{exchange} exchange is not configured yet.")
                return exchanges_config['exchanges'][exchange]
        except yaml.YAMLError as e:
            logging.error(f"Configuration file is not valid: {str(e)}.") 
