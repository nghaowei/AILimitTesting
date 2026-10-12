import argparse
import asyncio
import logging

from .bot import list_chats, run
from .config import Config


def main() -> None:
    parser = argparse.ArgumentParser(prog="credit_sniper", description="Auto-claim RVRC dining credits.")
    parser.add_argument("--list-chats", action="store_true",
                        help="log in and print channel/bot IDs so you can fill in CHANNEL")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    logging.getLogger("telethon").setLevel(logging.WARNING)

    if args.list_chats:
        asyncio.run(list_chats(Config.from_env(require_channel=False)))
    else:
        try:
            asyncio.run(run(Config.from_env()))
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
