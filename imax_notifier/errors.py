class MonitorError(Exception):
    """Error seguro para logs: nunca contiene URLs con credenciales."""


class RejectedMessage(MonitorError):
    """Telegram confirmó que el mensaje no fue aceptado."""


class UncertainMessage(MonitorError):
    """No se puede determinar si Telegram recibió el mensaje."""
