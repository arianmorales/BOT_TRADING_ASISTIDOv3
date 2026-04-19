"""
=================================================================
QUANTUM MOMENTUM BOT v2.0 - RESTRUCTURED
=================================================================
Bot de Trading Asistido refactorizado con arquitectura modular:
- Sistema de Scoring Ponderado
- Gestión de Riesgo Completa
- Filtros Dinámicos
- Métricas Profesionales
- API Async con Cache
=================================================================

Estructura del proyecto:
    src/
    ├── core/           # Componentes centrales
    │   ├── __init__.py
    │   ├── config.py   # Configuración
    │   ├── logger.py   # Logging
    │   └── exceptions.py
    ├── trading/        # Lógica de trading
    │   ├── __init__.py
    │   ├── analyzer.py # Analizador de mercado
    │   ├── scoring.py  # Sistema de scoring
    │   ├── filters.py  # Filtros dinámicos
    │   ├── risk.py     # Gestión de riesgo
    │   └── metrics.py  # Métricas
    ├── market/         # Datos de mercado
    │   ├── __init__.py
    │   └── api_client.py
    ├── notifications/  # Notificaciones
    │   ├── __init__.py
    │   ├── whatsapp.py
    │   └── email.py
    └── utils/          # Utilidades
        ├── __init__.py
        └── helpers.py
"""

__version__ = "2.0.0"
__author__ = "Quant Developer Senior"
