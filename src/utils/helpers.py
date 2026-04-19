"""
=================================================================
HELPERS.PY - Utility Functions
=================================================================
Funciones utilitarias para el bot de trading.
=================================================================
"""
import os
import json
from datetime import datetime
from typing import Any, Dict, Optional


def ensure_dir(directory: str) -> None:
    """Asegura que un directorio existe"""
    os.makedirs(directory, exist_ok=True)


def load_json_file(filepath: str, default: Optional[Dict] = None) -> Dict[str, Any]:
    """Carga un archivo JSON con valor por defecto"""
    if default is None:
        default = {}
    
    if not os.path.exists(filepath):
        return default
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def save_json_file(filepath: str, data: Dict[str, Any]) -> None:
    """Guarda un archivo JSON"""
    ensure_dir(os.path.dirname(filepath) or '.')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def format_timestamp(dt: Optional[datetime] = None) -> str:
    """Formatea timestamp para logs"""
    if dt is None:
        dt = datetime.now()
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def format_currency(value: float, symbol: str = '$') -> str:
    """Formatea valor como moneda"""
    return f"{symbol}{value:,.2f}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """Formatea valor como porcentaje"""
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.{decimals}f}%"


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """División segura"""
    if denominator == 0:
        return default
    return numerator / denominator
