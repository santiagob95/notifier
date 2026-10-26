import logging
import time

import requests

from .errors import MonitorError, RejectedMessage, UncertainMessage
from .http import TIMEOUT, json_body

LOG = logging.getLogger(__name__)


class Telegram:
    def __init__(self, token: str, chat_id: str, session=None):
        if not token or not chat_id:
            raise MonitorError("Configurar TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en GitHub Secrets o en el entorno.")
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id
        self.session = session or requests.Session()

    def send(self, text: str):
        for attempt in range(3):
            try:
                response = self.session.post(self.url, json={
                    "chat_id": self.chat_id, "text": text,
                    "link_preview_options": {"is_disabled": True},
                }, timeout=TIMEOUT, allow_redirects=False)
            except requests.RequestException:
                raise UncertainMessage("Telegram: resultado de envío incierto por fallo de red. Revisar el chat y resolver el pendiente.") from None
            try:
                data = response.json()
            except ValueError:
                raise UncertainMessage("Telegram: respuesta no interpretable. Revisar el chat y resolver el pendiente.") from None
            if isinstance(data, dict) and data.get("ok") is True and response.status_code == 200:
                return
            if isinstance(data, dict) and data.get("ok") is False and data.get("error_code") == 429:
                delay = data.get("parameters", {}).get("retry_after", 1)
                if type(delay) is int and 0 <= delay <= 60 and attempt < 2:
                    LOG.warning("Telegram: límite temporal; reintento en %s s", delay)
                    time.sleep(delay)
                    continue
                raise RejectedMessage("Telegram: límite de envíos; se reintentará en la próxima ejecución.")
            if isinstance(data, dict) and data.get("ok") is False and 400 <= response.status_code < 500:
                raise RejectedMessage(f"Telegram rechazó el mensaje: HTTP {response.status_code}. Revisar bot y destino.")
            raise UncertainMessage("Telegram: no confirmó recepción. Revisar el chat y resolver el pendiente.")
        raise AssertionError("unreachable")


def show_chat_ids(http, token: str):
    if not token:
        raise MonitorError("Configurar TELEGRAM_BOT_TOKEN para consultar el destino.")
    response = http.get(f"https://api.telegram.org/bot{token}/getUpdates", label="Telegram getUpdates", params={"timeout": 0}, allow_redirects=False)
    data = json_body(response, "Telegram getUpdates")
    if response.status_code != 200 or not isinstance(data, dict) or data.get("ok") is not True:
        raise MonitorError("No se pudieron consultar los chats. Enviar /start al bot y comprobar que no tiene un webhook activo.")
    ids = set()
    for update in data.get("result", []):
        for field in ("message", "channel_post", "my_chat_member"):
            chat_id = update.get(field, {}).get("chat", {}).get("id")
            if type(chat_id) is int:
                ids.add(chat_id)
    for chat_id in sorted(ids):
        print(chat_id)
    if not ids:
        LOG.info("No hay chats en las actualizaciones pendientes; enviá /start al bot y repetí la consulta.")
