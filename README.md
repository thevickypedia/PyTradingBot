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
import pytradingbot

if __name__ == '__main__':
    pytradingbot.start()
```

**Initiate - CLI**
```shell
pytradingbot start
```

> Use `pytradingbot --help` for usage instructions.

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
[label-pyversion]: https://img.shields.io/badge/python-3.10%20%7C%203.11-blue
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
