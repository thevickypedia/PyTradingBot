import logging
import os
import socket

import pandas as pd

os.makedirs("logs", exist_ok=True)

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
handler = logging.FileHandler(
    filename=os.path.join("logs", f"trading_bot_{pd.Timestamp.now().strftime('%Y-%m-%d')}.log"),
    mode='a',
)
handler.setFormatter(
    fmt=logging.Formatter(
        datefmt="%b-%d-%Y %I:%M:%S %p",
        fmt="%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s",
    )
)
LOGGER.addHandler(hdlr=handler)

DEFAULT_FILTERS = {
    'Exchange': 'NASDAQ',
    'Country': 'USA',
    'Average Volume': 'Over 500K',
    'Price': 'Under $50',
    'Relative Volume': 'Over 2',
    'Gap': 'Up',
    'Change': 'Up 5%',
    'RSI (14)': 'Not Overbought (<60)',
}

TWELVEDATA_API_KEY = (
    os.getenv("TWELVEDATA_API_KEY") or os.getenv("TWELVEDATA_APIKEY") or
    os.getenv("twelvedata_api_key") or os.getenv("twelvedata_apikey") or
    "demo"
)

HOST = (
    os.getenv("HOST") or os.getenv("host") or socket.gethostbyname("localhost") or "0.0.0.0"
)

PORT = int(
    os.getenv("PORT") or os.getenv("port") or "8080"
)
