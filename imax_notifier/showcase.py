from dataclasses import dataclass
from datetime import date
import re
import unicodedata
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from .config import Config
from .errors import MonitorError
from .http import json_body

CATALOG_URL = "https://www.todoshowcase.com/"
FALLBACK_CATALOG_URL = "https://entradas.todoshowcase.com/showcase/"
API_BASE = "https://api.voyalcine.net"


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(x for x in value if not unicodedata.combining(x))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def matches_title(title: str, aliases: tuple[str, ...]) -> bool:
    title = normalized(title)
    suffix_words = {"imax", "2d", "3d", "sub", "subtitulada", "subtitulado", "doblada", "doblado", "castellano", "espanol", "ingles"}
    for alias in aliases:
        name = normalized(alias)
        if title == name:
            return True
        if title.startswith(name + " ") and set(title[len(name):].split()) <= suffix_words:
            return True
    return False


def discover(html: str, config: Config) -> set[int]:
    soup = BeautifulSoup(html, "html.parser")
    found, valid_titles = set(), 0
    for anchor in soup.select("a[href*='filmid=']"):
        parsed = urlparse(urljoin(FALLBACK_CATALOG_URL, anchor.get("href", "")))
        if parsed.scheme != "https" or parsed.hostname != "entradas.todoshowcase.com":
            continue
        if parsed.path not in {"/showcase/pelicula", "/showcase/pelicula.aspx"}:
            continue
        ids = parse_qs(parsed.query).get("filmid", [])
        if len(ids) != 1 or not ids[0].isdigit() or int(ids[0]) <= 0:
            continue
        title_node = anchor.select_one("h3.name")
        title = (title_node or anchor).get_text(" ", strip=True)
        if not title or normalized(title) in {"comprar entradas", "ver mas"}:
            continue
        valid_titles += 1
        if matches_title(title, config.aliases):
            found.add(int(ids[0]))
    if not valid_titles:
        raise MonitorError("Catálogo sin tarjetas reconocibles; posible cambio de HTML o bloqueo.")
    return found


@dataclass(frozen=True)
class Performance:
    film_id: int
    cinema_id: int
    performance_id: int
    day: str
    show_time: str
    format_name: str
    show_id: str

    @property
    def key(self) -> str:
        return f"{self.film_id}:{self.cinema_id}:{self.performance_id}"

    @property
    def url(self) -> str:
        # Enlace público estable, sin sesión ni tokens; permite elegir cualquier función.
        return f"https://entradas.todoshowcase.com/showcase/pelicula?filmid={self.film_id}&house_id=3250"


def positive_int(value) -> bool:
    return type(value) is int and value > 0


def parse_tree(data, film_id: int, config: Config, today: date) -> list[Performance]:
    try:
        if not isinstance(data, dict) or type(data.get("id")) is not int or data["id"] != film_id:
            raise ValueError
        if not isinstance(data.get("name"), str) or not isinstance(data.get("days"), dict):
            raise ValueError
        if not matches_title(data["name"], config.aliases):
            raise MonitorError(f"La película {film_id} no coincide con los títulos autorizados.")
        result = {}
        for day, cinemas in data["days"].items():
            parsed_day = date.fromisoformat(day)
            if parsed_day.isoformat() != day or not isinstance(cinemas, list):
                raise ValueError
            for cinema in cinemas:
                if not isinstance(cinema, dict) or not positive_int(cinema.get("id")):
                    raise ValueError
                if cinema["id"] != config.cinema_id:
                    continue
                if normalized(cinema.get("name", "")) != "imax theatre norcenter":
                    raise ValueError
                formats = cinema["formats"]
                if not isinstance(formats, list):
                    raise ValueError
                for fmt in formats:
                    description = fmt["formatDescription"]
                    if not isinstance(description, str):
                        raise ValueError
                    if "imax" not in normalized(description).split():
                        continue
                    show_id, perfs = fmt["showId"], fmt["performances"]
                    if not isinstance(show_id, str) or not show_id.strip() or not isinstance(perfs, list):
                        raise ValueError
                    for perf in perfs:
                        pid, show_time = perf["performanceId"], perf["showTime"]
                        if not positive_int(pid) or not isinstance(show_time, str) or not re.fullmatch(
                            r"(?:N )?(?:[01]\d|2[0-3]):[0-5]\d", show_time
                        ):
                            raise ValueError
                        # Se conservan las horas de la fecha actual y el prefijo de trasnoche
                        # tal como los publica Showcase; no se inventa una fecha efectiva.
                        if parsed_day < today:
                            continue
                        item = Performance(film_id, cinema["id"], pid, day, show_time, description, show_id)
                        if item.key in result and result[item.key] != item:
                            raise ValueError
                        result[item.key] = item
        return sorted(result.values(), key=lambda p: (p.day, p.show_time, p.film_id, p.performance_id))
    except (KeyError, TypeError, ValueError, AttributeError):
        raise MonitorError(f"Esquema de funciones inválido para película {film_id}; no se notificará.") from None


class Showcase:
    def __init__(self, http, config):
        self.http, self.config = http, config

    def discover(self):
        for url in (CATALOG_URL, FALLBACK_CATALOG_URL):
            try:
                response = self.http.get(url, label="Catálogo Showcase")
                if response.status_code != 200:
                    raise MonitorError(f"Catálogo: HTTP {response.status_code}.")
                return discover(response.text, self.config)
            except MonitorError:
                if url == FALLBACK_CATALOG_URL:
                    raise
                import logging
                logging.getLogger(__name__).warning("Catálogo principal no utilizable; consultando catálogo alternativo.")
        raise AssertionError("unreachable")

    def performances(self, film_id, today):
        response = self.http.get(f"{API_BASE}/films/{film_id}/tree/{self.config.house_id}", label="Funciones Showcase")
        if response.status_code != 200:
            raise MonitorError(f"Funciones Showcase: HTTP {response.status_code} para película {film_id}.")
        return parse_tree(json_body(response, "Funciones Showcase"), film_id, self.config, today)
