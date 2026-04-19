"""
=================================================================
EXCEPTIONS.PY - Custom Exceptions
=================================================================
Excepciones personalizadas para el bot de trading.
=================================================================
"""


class BotException(Exception):
    """Excepción base del bot"""
    pass


class ConfigError(BotException):
    """Error de configuración"""
    pass


class APIError(BotException):
    """Error de API"""
    pass


class MarketDataError(APIError):
    """Error al obtener datos de mercado"""
    pass


class ScoringError(BotException):
    """Error en cálculo de scoring"""
    pass


class RiskError(BotException):
    """Error en gestión de riesgo"""
    pass


class NotificationError(BotException):
    """Error al enviar notificación"""
    pass


class StateError(BotException):
    """Error en gestión de estado"""
    pass
