import requests

from pytradingbot.constants import LOGGER, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

async def make_request(path: str, payload: dict, retry: bool = False) -> requests.Response:
    """Helper function to make a POST request to the Telegram Bot API."""
    url = f"{BASE_URL}/{path}"
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response
    except requests.RequestException as error:
        error = str(error).replace(TELEGRAM_BOT_TOKEN, "******")
        if retry:
            LOGGER.error(f"Telegram API request failed after retry: {error}")
        else:
            LOGGER.warning(f"Telegram API request failed before retry: {error}")
            return await make_request(path, payload, retry=True)


async def send_telegram_message(
        message: str,
        parse_mode: str | None = "markdown",
    ) -> None:
    """Send a message to a Telegram chat using the Bot API."""
    if all((TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS)):
        for chat_id in TELEGRAM_CHAT_IDS:
            LOGGER.debug(f"Sending Telegram message to chat_id={chat_id}: {message}")
            await make_request(
                path="sendMessage",
                payload={"chat_id": chat_id, "text": message, "parse_mode": parse_mode},
            )
    else:
        LOGGER.warning("Telegram Bot token or chat IDs not configured. Skipping message: %s", message)
