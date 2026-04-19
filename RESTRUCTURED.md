# Quantum Momentum Bot v2.0 - Estructura Reorganizada

## 📁 Nueva Estructura del Proyecto

```
/workspace/
├── src/                          # Código fuente principal
│   ├── __init__.py              # Package init con metadata
│   ├── main.py                  # Punto de entrada refactorizado
│   │
│   ├── core/                    # Componentes centrales
│   │   ├── __init__.py
│   │   ├── config.py            # Configuración (antes config_loader.py)
│   │   ├── logger.py            # Sistema de logging
│   │   └── exceptions.py        # Excepciones personalizadas
│   │
│   ├── trading/                 # Lógica de trading
│   │   ├── __init__.py
│   │   ├── analyzer.py          # Analizador de mercado
│   │   ├── scoring.py           # Sistema de scoring ponderado
│   │   ├── filters.py           # Filtros dinámicos
│   │   ├── risk.py              # Gestión de riesgo
│   │   └── metrics.py           # Métricas y tracking
│   │
│   ├── market/                  # Datos de mercado
│   │   ├── __init__.py
│   │   ├── api_client.py        # API cliente asíncrono
│   │   └── data.py              # Funciones de compatibilidad
│   │
│   ├── notifications/           # Notificaciones
│   │   ├── __init__.py
│   │   └── manager.py           # WhatsApp y Email
│   │
│   └── utils/                   # Utilidades
│       ├── __init__.py
│       └── helpers.py           # Funciones auxiliares
│
├── tests/                       # Tests unitarios
│   └── __init__.py
│
├── config/                      # Archivos de configuración
│   └── config.yaml              # Configuración principal
│
├── logs/                        # Logs generados
│   ├── bot.log
│   ├── bot_debug.log
│   ├── bot_trades.log
│   └── bot_errors.log
│
├── whatsapp_session/            # Sesión de WhatsApp
├── state.json                   # Estado del bot
├── metrics.json                 # Métricas históricas
├── requirements.txt             # Dependencias
└── README.md                    # Documentación
```

## 🔧 Cambios Principales

### 1. **Organización Modular**
- El código ahora está organizado por funcionalidad en lugar de tener todos los archivos en la raíz
- Cada módulo tiene responsabilidades claras y separadas

### 2. **Imports Actualizados**
Los imports ahora usan la estructura de paquetes:
```python
# Antes
from config_loader import config
import api_client
import scoring

# Ahora
from src.core.config import config
from src.market.api_client import api_client
from src.trading import scoring
```

### 3. **Nuevos Archivos**
- `src/core/exceptions.py`: Excepciones personalizadas para mejor manejo de errores
- `src/utils/helpers.py`: Funciones utilitarias reutilizables
- `src/main.py`: Punto de entrada refactorizado con imports modulares

### 4. **Compatibilidad**
- Los archivos originales se mantienen en la raíz para compatibilidad
- La nueva estructura convive con el código legacy
- Transición gradual posible

## 🚀 Uso

### Ejecutar desde la nueva estructura:
```bash
cd /workspace/src
python main.py --mode run
```

### Comandos disponibles:
```bash
# Ejecución continua
python src/main.py --mode run

# Un solo ciclo
python src/main.py --mode once

# Configurar estado inicial
python src/main.py --mode setup

# Ver estado actual
python src/main.py --mode show-state

# Inicializar WhatsApp
python src/main.py --mode init-whatsapp
```

## 📦 Beneficios de la Reestructuración

1. **Mejor organización**: Código agrupado por funcionalidad
2. **Más mantenible**: Fácil encontrar y modificar componentes
3. **Testing simplificado**: Tests pueden organizarse por módulo
4. **Escalabilidad**: Fácil añadir nuevas características
5. **Separación de concerns**: Cada módulo tiene una responsabilidad clara

## ⚠️ Notas Importantes

- Los archivos originales en la raíz (`analyzer.py`, `api_client.py`, etc.) se mantienen sin cambios
- La nueva estructura es completamente funcional
- Se recomienda migrar gradualmente a usar `src/main.py`
- Los paths relativos a configuraciones y logs siguen funcionando igual
