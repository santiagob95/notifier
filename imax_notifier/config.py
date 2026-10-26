from dataclasses import dataclass
from pathlib import Path
import tomllib

from .errors import MonitorError


@dataclass(frozen=True)
class Config:
    aliases: tuple[str, ...]
    house_id: int = 3250
    cinema_id: int = 18


def load_config(path: Path) -> Config:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
        aliases = data["movie"]["title_aliases"]
        if not isinstance(aliases, list) or not aliases or any(
            not isinstance(x, str) or not x.strip() for x in aliases
        ):
            raise ValueError
        # No permitir cambiar accidentalmente al Norcenter común.
        if data["cinema"]["house_id"] != 3250 or data["cinema"]["cinema_id"] != 18:
            raise ValueError
        return Config(tuple(aliases))
    except (OSError, ValueError, KeyError, TypeError):
        raise MonitorError("Configuración inválida; revisar config.toml.") from None
