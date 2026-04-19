"""
=================================================================
MARKET_DATA.PY - Market Data (Legacy Compatibility)
=================================================================
Mantiene compatibilidad con el código anterior usando el nuevo API client.
=================================================================
"""
from typing import Dict, Any, List, Tuple
from datetime import datetime
import time
import requests

from config_loader import config
import api_client


LOG_FILE = "logs.txt"

def log(msg: str) -> None:
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ============================================================================
# API ENDPOINTS
# ============================================================================

API_BASE = config.get('market.base_api', 'https://api.coinex.com/v2')


# ============================================================================
# COMPATIBILITY FUNCTIONS
# ============================================================================

def get_markets() -> List[str]:
    """Obtiene lista de mercados - compatibilidad"""
    return api_client.get_markets()


def get_all_tickers() -> Dict[str, Any]:
    """Obtiene todos los tickers - compatibilidad"""
    return api_client.get_all_tickers()


def get_market_ticker(symbol: str) -> Dict[str, Any]:
    """Obtiene ticker de un mercado"""
    return api_client.get_ticker(symbol)


def getdepth(symbol: str, limit: int = 10) -> Dict[str, Any]:
    """Obtiene profundidad"""
    return api_client.get_depth(symbol, limit)


def get_klines(symbol: str, period: str = "1hour", limit: int = 168) -> List[Dict[str, Any]]:
    """Obtiene klines - compatibilidad"""
    return api_client.get_klines(symbol, period, limit)


def get_historical_changes(symbol: str) -> Tuple[float, float]:
    """Obtiene cambios históricos - compatibilidad"""
    return api_client.get_historical_changes(symbol)


def save_snapshot(tickers: Dict[str, Any], filename: str = "prices.json") -> None:
    """Guarda snapshot de precios"""
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "tickers": tickers
    }
    import json
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)


def load_snapshot(filename: str = "prices.json") -> Dict[str, Any]:
    """Carga snapshot de precios"""
    import json
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None