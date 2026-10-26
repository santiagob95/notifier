import argparse
import logging
import os
from pathlib import Path

from .config import load_config
from .errors import MonitorError
from .http import Http
from .runner import resolve_pending, run_monitor
from .showcase import Showcase
from .state import GitHubStore, LocalStore
from .telegram import Telegram, show_chat_ids


def main():
    parser = argparse.ArgumentParser(description="Monitor Dune 3 / IMAX Norcenter")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--state", type=Path, default=Path(".local/state.json"))
    parser.add_argument("--github-state", action="store_true")
    parser.add_argument("--mode", choices=("monitor", "dry-run", "test-telegram", "chat-id", "resolve-sent", "resolve-retry"), default="monitor")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Evitar que clientes HTTP impriman una URL que contenga el token de Telegram.
    logging.getLogger("urllib3").setLevel(logging.CRITICAL)
    http = Http()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    try:
        if args.mode == "chat-id":
            show_chat_ids(http, token)
            return 0
        if args.mode == "test-telegram":
            Telegram(token, chat_id).send("✅ Prueba de IMAX Notifier. El bot puede enviar mensajes a este chat. Esto no es una alerta de venta.")
            logging.info("Mensaje de prueba enviado.")
            return 0
        store = GitHubStore(http, os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_TOKEN", ""), os.environ.get("GITHUB_DEFAULT_BRANCH", "main")) if args.github_state else LocalStore(args.state)
        if args.mode.startswith("resolve-"):
            resolve_pending(store, store.load(), args.mode.removeprefix("resolve-"))
            return 0
        config = load_config(args.config)
        telegram = None if args.mode == "dry-run" else Telegram(token, chat_id)
        run_monitor(Showcase(http, config), store, telegram, dry_run=args.mode == "dry-run")
        return 0
    except MonitorError as exc:
        logging.error("%s", exc)
        return 1
    except Exception as exc:
        # Sin repr/traceback de errores externos que puedan contener credenciales.
        logging.error("Error inesperado (%s). Revisar configuración y tests; no se imprime información sensible.", type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
