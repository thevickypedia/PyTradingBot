import sys

from pytradingbot.server import start

version = "0.0.0a0"


def commandline() -> None:
    """Starter function to invoke PyTradingBot via CLI commands.

    **Flags**
        - ``--version | -V``: Prints the version.
        - ``--help | -H``: Prints the help section.
        - ``start``: Start the API server.
    """
    assert sys.argv[0].lower().endswith("pytradingbot"), "Invalid commandline trigger!!"

    print_ver = "--version" in sys.argv or "-V" in sys.argv
    get_help = "--help" in sys.argv or "-H" in sys.argv
    start_server = "start" in sys.argv

    if print_ver:
        print(f"PyTradingBot {version}")
        sys.exit(0)

    options = {
        "--version | -V": "Prints the version.",
        "--help | -H": "Prints the help section.",
        "start": "Start the API server.",
    }

    # weird way to increase spacing to keep all values monotonic
    _longest_key = len(max(options.keys()))
    _pretext = "\n\t* "
    choices = _pretext + _pretext.join(
        f"{k} {'·' * (_longest_key - len(k) + 8)}→ {v}".expandtabs() for k, v in options.items()
    )

    if get_help:
        print(f"\nUsage: pytradingbot [arbitrary-command]\n\nOptions (and corresponding behavior):{choices}")
        sys.exit(0)

    if start_server:
        start()
    else:
        print(
            "Invalid commandline trigger!!\n\nUsage: pytradingbot [arbitrary-command]\n\n"
            f"Options (and corresponding behavior):{choices}"
        )
        sys.exit(1)
