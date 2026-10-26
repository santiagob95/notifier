import logging
import time
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

import requests

from .errors import MonitorError

LOG = logging.getLogger(__name__)
TIMEOUT = (5, 25)
RETRY_STATUSES = {429, 500, 502, 503, 504}


def retry_delay(value: str | None, attempt: int) -> float:
    if value:
        try:
            delay = float(value)
        except ValueError:
            try:
                delay = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                delay = 2 ** attempt
        if delay > 60:
            raise MonitorError("El servidor pide esperar más de 60 s; se difiere a la próxima ejecución.")
        return max(0, delay)
    return float(2 ** attempt)


class Http:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "imax-notifier/1.0 (public showtimes; 30min polling)"

    def get(self, url: str, *, label: str, **kwargs):
        """Tres intentos como máximo; nunca imprimir exceptions/URLs de requests."""
        for attempt in range(3):
            try:
                response = self.session.get(url, timeout=TIMEOUT, **kwargs)
            except requests.RequestException:
                if attempt == 2:
                    raise MonitorError(f"{label}: fallo de red tras 3 intentos.") from None
                LOG.warning("%s: fallo de red, reintento %s/2", label, attempt + 1)
                time.sleep(2 ** attempt)
                continue
            if response.status_code not in RETRY_STATUSES or attempt == 2:
                return response
            LOG.warning("%s: HTTP %s, reintento %s/2", label, response.status_code, attempt + 1)
            delay = retry_delay(response.headers.get("Retry-After"), attempt)
            response.close()
            time.sleep(delay)
        raise AssertionError("unreachable")

    def write(self, method: str, url: str, *, label: str, **kwargs):
        # No repetir escrituras de resultado desconocido.
        try:
            return self.session.request(method, url, timeout=TIMEOUT, allow_redirects=False, **kwargs)
        except requests.RequestException:
            raise MonitorError(f"{label}: escritura sin confirmación; no se reintenta automáticamente.") from None


def json_body(response, label: str):
    try:
        return response.json()
    except (ValueError, requests.RequestException):
        raise MonitorError(f"{label}: respuesta JSON inválida.") from None
