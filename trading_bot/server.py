"""
Entry point – run with:
    python -m trading_bot.server
or:
    uvicorn trading_bot.server:app
"""
import uvicorn

# Re-export `app` so `uvicorn trading_bot.server:app` resolves correctly.
from .api import app  # noqa: F401


def start(host: str = "0.0.0.0", port: int = 8000) -> None:
    uvicorn.run("trading_bot.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    start()
