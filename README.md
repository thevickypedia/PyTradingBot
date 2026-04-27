# PyTradingBot
PyTradingBot is a python based trading bot API.

![Python][label-pyversion]

![Platform][label-platform]

[![pypi][label-actions-pypi]][gha_pypi]

[![Pypi][label-pypi]][pypi]
[![Pypi-format][label-pypi-format]][pypi-files]
[![Pypi-status][label-pypi-status]][pypi]

## Summary

PyTradingBot is a python based trading bot API based on FinViz screener fields, and Yahoo finance.

## Installation

```shell
pip install PyTradingBot
```

## Usage

**Initiate - IDE**
```python
from pytradingbot.server import start

if __name__ == '__main__':
    start()
```

**Initiate - CLI**
```shell
pytradingbot start
```

> Use `pytradingbot --help` for usage instructions.

## Containerized

**Build**
```shell
docker build -t pytradingbot .
```

**Run**
```shell
docker run --name pytradingbot -p 5005:5005 -e PORT=5005 pytradingbot
```

## Environment Variables
> All environment variables are optional.

**API basics**
- **PORT**: API port. _Defaults to 8080_
- **LOG_LEVEL**: Log level for the API server. _Defaults to `DEBUG`_
- **SCAN_COOLDOWN_SECONDS**: Cooldown time before requesting another scan. _Defaults to 60_

**Authentication**
- **USERNAME**: Username to protect the server with authentication.
- **PASSWORD**: Password to protect the server with authentication.
- **TIMEOUT**: Time in seconds before the authentication token expires. _Defaults to 3600_

**Notification setup**
- **TELEGRAM_BOT_TOKEN**: Telegram bot token to notify the user.
- **TELEGRAM_CHAT_IDS**: Comma separated list of chat IDs to notify.

> To get the chat ID, message the bot on Telegram and run the command:
> ```shell
> curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getUpdates" \
> | jq '.result[].message.chat.id'
> ```

### Background Scheduler

The API runs a background async scheduler that triggers scans automatically (EST) and stores each run in the existing sqlite DB.

#### Default schedule:

- Pre-Market (04:00-09:30): every 15 minutes
- Market Open (09:30-10:30): every 5 minutes
- Mid Day (10:30-14:00): every 30 minutes
- Power Hour (14:00-16:00): every 5 minutes
- After Hours (16:00-20:00): once at 16:15

You can override these rules from the Dashboard `Schedule` tab, or through:

- `GET /schedule` to read current/default config
- `POST /schedule` to save overrides

## [Release Notes][release-notes]
**Requirement**
```shell
python -m pip install gitverse
```

**Usage**
```shell
gitverse-release reverse -f release_notes.rst -t 'Release Notes'
```

## Linting
`pre-commit` will ensure linting

**Requirement**
```shell
python -m pip install pre-commit
```

**Usage**
```shell
pre-commit run --all-files
```

## Pypi Package
[![pypi-module][label-pypi-package]][pypi-repo]

[https://pypi.org/project/PyTradingBot/][pypi]

## License & copyright

&copy; Vignesh Rao

Licensed under the [MIT License][license]

[license]: https://github.com/thevickypedia/PyTradingBot/blob/main/LICENSE
[label-pypi-package]: https://img.shields.io/badge/Pypi%20Package-PyTradingBot-blue?style=for-the-badge&logo=Python
[label-pyversion]: https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue
[label-platform]: https://img.shields.io/badge/Platform-Linux|macOS|Windows-1f425f.svg
[label-actions-pypi]: https://github.com/thevickypedia/PyTradingBot/actions/workflows/python-publish.yml/badge.svg
[label-pypi]: https://img.shields.io/pypi/v/PyTradingBot
[label-pypi-format]: https://img.shields.io/pypi/format/PyTradingBot
[label-pypi-status]: https://img.shields.io/pypi/status/PyTradingBot
[gha_pypi]: https://github.com/thevickypedia/PyTradingBot/actions/workflows/python-publish.yml
[pypi]: https://pypi.org/project/PyTradingBot
[pypi-files]: https://pypi.org/project/PyTradingBot/#files
[pypi-repo]: https://packaging.python.org/tutorials/packaging-projects/
[release-notes]: https://github.com/thevickypedia/PyTradingBot/blob/main/release_notes.rst
