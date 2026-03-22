import logging
import pathlib

import uvicorn

from pytradingbot.api import app
from pytradingbot.constants import env


class HealthCheckFilter(logging.Filter):
    """Custom logging filter to exclude health check logs from the output."""

    def filter(self, record):
        """Filter out logs related to health checks."""
        # 'record.getMessage()' contains the log text
        # Skip logs containing 'GET /health' (from curl)
        return "/health" not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())


def start() -> None:
    """Start server."""
    module_name = pathlib.Path(__file__)
    uvicorn.run(
        host=env.HOST,
        port=env.PORT,
        app=f"{module_name.parent.stem}.{module_name.stem}:{app.__name__}",
    )
