import base64
import json
from pathlib import Path
import re
from urllib.parse import quote

from .errors import MonitorError
from .http import json_body


def empty_state():
    return {"version": 1, "film_ids": [], "sent": {}, "pending": None}


def validate_state(state):
    try:
        if not isinstance(state, dict) or state.get("version") != 1:
            raise ValueError
        if not isinstance(state["film_ids"], list) or any(type(x) is not int or x <= 0 for x in state["film_ids"]):
            raise ValueError
        if not isinstance(state["sent"], dict):
            raise ValueError
        if any(not re.fullmatch(r"\d+:18:\d+", k) or not isinstance(v, str) for k, v in state["sent"].items()):
            raise ValueError
        pending = state["pending"]
        if pending is not None:
            if not isinstance(pending, dict) or not isinstance(pending["keys"], list) or not pending["keys"]:
                raise ValueError
            if any(not isinstance(k, str) or not re.fullmatch(r"\d+:18:\d+", k) for k in pending["keys"]):
                raise ValueError
            if not isinstance(pending["created_at"], str) or not isinstance(pending["text"], str):
                raise ValueError
        return state
    except (ValueError, KeyError, TypeError):
        raise MonitorError("Estado inválido; no se reinicia automáticamente para evitar avisos duplicados.") from None


class LocalStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self):
        if not self.path.exists():
            return empty_state()
        try:
            return validate_state(json.loads(self.path.read_text(encoding="utf-8-sig")))
        except (OSError, ValueError):
            raise MonitorError("No se pudo leer el estado local; no se enviarán avisos.") from None

    def save(self, state):
        validate_state(state)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            raise MonitorError("No se pudo guardar el estado local.") from None


class GitHubStore:
    """Estado durable en monitor-state/state/monitor.json, con control de SHA."""
    branch = "monitor-state"
    path = "state/monitor.json"

    def __init__(self, http, repository: str, token: str, default_branch: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not token or not default_branch:
            raise MonitorError("Faltan GITHUB_REPOSITORY, GITHUB_TOKEN o GITHUB_DEFAULT_BRANCH válidos.")
        if default_branch == self.branch:
            raise MonitorError("monitor-state no puede ser la rama principal.")
        self.http = http
        self.base = f"https://api.github.com/repos/{repository}"
        self.default_branch = default_branch
        self.headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"}
        self.sha = None
        self.branch_exists = False

    def get(self, path, **kwargs):
        return self.http.get(self.base + path, label="Estado GitHub", headers=self.headers, allow_redirects=False, **kwargs)

    def load(self):
        ref = self.get(f"/git/ref/heads/{self.branch}")
        if ref.status_code == 404:
            # Comprobar acceso al repo: no interpretar falta de permisos como estado vacío.
            repo = self.get("")
            if repo.status_code != 200:
                raise MonitorError(f"No se puede leer el repositorio de estado: HTTP {repo.status_code}.")
            return empty_state()
        if ref.status_code != 200:
            raise MonitorError(f"No se puede leer la rama de estado: HTTP {ref.status_code}.")
        self.branch_exists = True
        response = self.get(f"/contents/{self.path}", params={"ref": self.branch})
        if response.status_code != 200:
            raise MonitorError(f"Archivo de estado ausente/inaccesible en una rama existente: HTTP {response.status_code}. Revisar sin reiniciar.")
        data = json_body(response, "Estado GitHub")
        try:
            if data["encoding"] != "base64" or not isinstance(data["sha"], str):
                raise ValueError
            state = validate_state(json.loads(base64.b64decode(data["content"]).decode("utf-8")))
            self.sha = data["sha"]
            return state
        except (KeyError, TypeError, ValueError, UnicodeError):
            raise MonitorError("Contenido de estado GitHub inválido.") from None

    def save(self, state):
        validate_state(state)
        if not self.branch_exists:
            base = self.get("/git/ref/heads/" + quote(self.default_branch, safe="/"))
            if base.status_code != 200:
                raise MonitorError(f"No se puede leer la rama principal: HTTP {base.status_code}.")
            try:
                sha = json_body(base, "Referencia GitHub")["object"]["sha"]
            except (KeyError, TypeError):
                raise MonitorError("Referencia GitHub inválida.") from None
            response = self.http.write("POST", self.base + "/git/refs", label="Crear rama de estado", headers=self.headers,
                                       json={"ref": f"refs/heads/{self.branch}", "sha": sha})
            if response.status_code != 201:
                raise MonitorError(f"No se pudo crear la rama de estado: HTTP {response.status_code}.")
            self.branch_exists = True
        payload = {
            "message": "Update ticket monitor state [skip ci]",
            "branch": self.branch,
            "content": base64.b64encode((json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode()).decode(),
        }
        if self.sha:
            payload["sha"] = self.sha
        response = self.http.write("PUT", self.base + f"/contents/{self.path}", label="Guardar estado GitHub", headers=self.headers, json=payload)
        if response.status_code not in {200, 201}:
            raise MonitorError(f"Estado no guardado: HTTP {response.status_code}. No se sobrescribe ni se reintenta a ciegas.")
        try:
            self.sha = json_body(response, "Guardar estado GitHub")["content"]["sha"]
        except (KeyError, TypeError):
            raise MonitorError("GitHub no confirmó el SHA del estado.") from None
