import pathlib

import uvicorn

from pytradingbot.api import app
from pytradingbot.constants import HOST, PORT


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
