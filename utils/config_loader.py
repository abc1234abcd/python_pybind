import yaml
import os
import logging
from pathlib import Path
from pydantic import Field
from utils.data_class import Market
from typing import Dict, Any, Union, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource

#this script loads public-safe exchange config through pydantic package. e.g mexc_config = ExchangeConfig(exchange = "mexc", market = Market.SPOT).model_dump() 

class ExchangeConfig(BaseSettings):
    exchange_name: str 
    market: Market 
    socket_url: Union[str, Dict, None] = Field(None)
    ping_message: Optional[Dict] = Field(None)
    ping_interval: Union[str, int, None] = Field(None)
    topic_template: Optional[Dict] = Field(None)

    model_config =SettingsConfigDict(
        yaml_file = Path(__file__).resolve().parent/"exchanges_config.yaml",
        yaml_file_encoding = 'utf-8',
        extra = "allow"
    )
    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
        return (init_settings, YamlConfigSettingsSource(init_settings,settings_cls))

class YamlConfigSettingsSource:
    def __init__(self, init_settings, settings_cls: type[BaseSettings]):
        self.init_settings = init_settings
        self.settings_cls = settings_cls       
    
    def __call__(self) -> Dict[str, Any]:
        yaml_file = self.settings_cls.model_config.get('yaml_file')
        if yaml_file and os.path.exists(yaml_file):
            try:
                with open(yaml_file, 'r') as file:
                    yaml_config = yaml.safe_load(file)
                init_data = self.init_settings()
                exchange_name = init_data.get('exchange_name')
                market = init_data.get('market')
                if exchange_name and market:
                    exchangename_market_data = yaml_config.get('exchanges', {}).get(exchange_name, {}).get(market.value, {})
                    return exchangename_market_data
            except Exception as e:
                logging.error(f"exchange config yaml file source settings failed on exception:{e}.")
