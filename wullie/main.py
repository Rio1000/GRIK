"""
Wullie entrypoint.

  python -m wullie.main                       # full voice mode (mic + all keys)
  WULLIE_TEXT_MODE=true python -m wullie.main    # type instead of talk (dev)
  WULLIE_WEB_MODE=true python -m wullie.main    # web UI on port 7777
"""
import logging

from .config import config
from .brain import Wullie


def main():
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    if config.web_mode:
        from .web.server import run
        run()
    elif config.text_mode:
        wullie = Wullie()
        print("Wullie (text mode). Type a command, or 'quit'.\n")
        while True:
            try:
                text = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text.lower() in {"quit", "exit"}:
                break
            if text:
                print(f"wullie> {wullie.ask(text)}\n")
    else:
        from .voice.loop import run_voice_loop
        run_voice_loop()


if __name__ == "__main__":
    main()
