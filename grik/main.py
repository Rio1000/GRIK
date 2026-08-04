"""
Grik entrypoint.

  python -m grik.main                       # full voice mode (mic + all keys)
  GRIK_TEXT_MODE=true python -m grik.main    # type instead of talk (dev)
  GRIK_WEB_MODE=true python -m grik.main    # web UI on port 7777
"""
import logging

from .config import config
from .brain import Grik


def main():
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    if config.web_mode:
        from .web.server import run
        run()
    elif config.text_mode:
        grik = Grik()
        print("Grik (text mode). Type a command, or 'quit'.\n")
        while True:
            try:
                text = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text.lower() in {"quit", "exit"}:
                break
            if text:
                print(f"grik> {grik.ask(text)}\n")
    else:
        from .voice.loop import run_voice_loop
        run_voice_loop()


if __name__ == "__main__":
    main()
