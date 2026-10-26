import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .errors import MonitorError, RejectedMessage

LOG = logging.getLogger(__name__)
ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def message_batches(performances):
    # 15 funciones por mensaje mantiene texto muy por debajo del límite de Telegram.
    # Un formato inesperadamente extenso se trunca sólo para la presentación.
    by_film = {}
    for perf in performances:
        by_film.setdefault(perf.film_id, []).append(perf)
    for perfs in by_film.values():
        for start in range(0, len(perfs), 15):
            chunk = perfs[start:start + 15]
            lines = ["🎟 Dune 3: funciones a la venta en IMAX Norcenter", "", "Nuevas funciones publicadas por Showcase (hora de Argentina):"]
            lines += [f"• {p.day} · {p.show_time} · {p.format_name[:80]}" for p in chunk]
            lines += ["", "Comprar / elegir función:", chunk[0].url, "", "No se consultó disponibilidad de butacas."]
            yield chunk, "\n".join(lines)


def resolve_pending(store, state, resolution):
    pending = state["pending"]
    if pending is None:
        LOG.info("No hay envío pendiente de resolución.")
        return
    if resolution == "sent":
        state["sent"].update({key: timestamp() for key in pending["keys"]})
    elif resolution != "retry":
        raise MonitorError("Resolución desconocida.")
    state["pending"] = None
    store.save(state)
    LOG.info("Pendiente resuelto: %s. No se envió ningún mensaje en esta ejecución.", resolution)


def run_monitor(showcase, store, telegram, *, dry_run=False, now=None):
    state = store.load()
    if state["pending"] is not None:
        raise MonitorError("Hay un envío pendiente de confirmación. Revisar Telegram y ejecutar resolve-sent o resolve-retry; se detienen los envíos para evitar duplicados.")
    now = now or datetime.now(ARGENTINA)
    today = now.astimezone(ARGENTINA).date()
    known_ids = set(state["film_ids"])
    discovery_error = None
    try:
        ids = known_ids | showcase.discover()
    except MonitorError as exc:
        if not known_ids:
            raise
        LOG.warning("Descubrimiento falló; se siguen consultando los IDs ya conocidos.")
        discovery_error = exc
        ids = known_ids
    all_performances = []
    # Validar todos los candidatos antes de enviar cualquier aviso.
    for film_id in sorted(ids):
        all_performances.extend(showcase.performances(film_id, today))
    fresh = [p for p in all_performances if p.key not in state["sent"]]
    LOG.info("Películas candidatas: %s; funciones IMAX publicadas: %s; nuevas: %s", len(ids), len(all_performances), len(fresh))
    state["film_ids"] = sorted(ids)
    if dry_run:
        for _, text in message_batches(fresh):
            LOG.info("SIMULACIÓN, sin envío ni cambio de estado:\n%s", text)
    else:
        if ids != known_ids:
            store.save(state)
        for chunk, text in message_batches(fresh):
            state["pending"] = {"keys": [p.key for p in chunk], "created_at": timestamp(), "text": text}
            # Reservar antes de transmitir. Si guardar falla, no enviar.
            store.save(state)
            try:
                telegram.send(text)
            except RejectedMessage:
                # Telegram confirmó que NO aceptó el mensaje: permitir reintento futuro.
                state["pending"] = None
                store.save(state)
                raise
            # Un error incierto conserva el pendiente durable; no se repite a ciegas.
            state["sent"].update({p.key: timestamp() for p in chunk})
            state["pending"] = None
            store.save(state)
            LOG.info("Aviso confirmado para %s funciones nuevas.", len(chunk))
    if discovery_error:
        raise discovery_error
    return len(fresh)
