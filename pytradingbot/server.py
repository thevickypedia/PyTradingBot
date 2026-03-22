import pathlib

import uvicorn

from pytradingbot.api import app
from pytradingbot.constants import Env


def start() -> None:
    """Start server."""
    module_name = pathlib.Path(__file__)
    uvicorn.run(
        host=Env.HOST,
        port=Env.PORT,
        app=f"{module_name.parent.stem}.{module_name.stem}:{app.__name__}",
    )
