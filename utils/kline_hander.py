import asyncio
from core.aioapiclient import AioMexcApiClient



async def kline_handler(self, rolling_wondow: int):
    def __init__(self, rolling_window: int):
        self.rolling_window = rolling_window
        self.api_client = AioMexcApiClient()
        asyncio.create_task(self.hist_kline())
    @property
    async def hist_kline(self):

