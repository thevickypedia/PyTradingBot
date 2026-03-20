"""Entry point:

    python -m trading_bot.server
or:
    uvicorn trading_bot.server:app
"""

import pathlib

import uvicorn

from trading_bot.api import app
from trading_bot.constants import HOST, PORT


def start() -> None:
    """Start server."""
    module_name = pathlib.Path(__file__)
    uvicorn.run(
        host=HOST,
        port=PORT,
        app=f"{module_name.parent.stem}.{module_name.stem}:{app.__name__}",
    )


if __name__ == "__main__":
    start()
