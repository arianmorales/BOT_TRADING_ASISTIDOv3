"""
=================================================================
API_CLIENT.PY - Sync API Client with Cache
=================================================================
Cliente API síncrono para CoinEx con cache.
=================================================================
"""
import time
import json
import hashlib
import requests
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from config_loader import config
from logger import log_debug, log_error


class CacheEntry:
    """Entrada de cache con TTL"""
    def __init__(self, data: Any, timestamp: float, ttl: int):
        self.data = data
        self.timestamp = timestamp
        self.ttl = ttl
    
    def is_expired(self) -> bool:
        return (time.time() - self.timestamp) > self.ttl


class APICache:
    """Cache simple con TTL"""
    def __init__(self, tickers_ttl: int = 300, klines_ttl: int = 600):
        self.tickers_ttl = tickers_ttl
        self.klines_ttl = klines_ttl
        self._cache: Dict[str, CacheEntry] = {}
    
    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            entry = self._cache[key]
            if not entry.is_expired():
                return entry.data
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, data: Any, ttl: Optional[int] = None) -> None:
        if 'ticker' in key.lower():
            ttl = ttl or self.tickers_ttl
        elif 'kline' in key.lower():
            ttl = ttl or self.klines_ttl
        else:
            ttl = ttl or 300
        self._cache[key] = CacheEntry(data, time.time(), ttl)
    
    def invalidate_symbol(self, symbol: str) -> None:
        keys_to_remove = [k for k in self._cache.keys() if symbol in k]
        for key in keys_to_remove:
            del self._cache[key]


class AsyncAPIClient:
    """Cliente API síncrono para CoinEx"""
    
    _instance: Optional['AsyncAPIClient'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self.base_url = config.get('market.base_api', 'https://api.coinex.com/v2')
            self.cache = APICache(
                tickers_ttl=config.get('cache.tickers_ttl', 300),
                klines_ttl=config.get('cache.klines_ttl', 600)
            )
            
            self._session = requests.Session()
            self._session.headers.update({'User-Agent': 'QuantumMomentumBot/2.0'})
            self._initialized = True
    
    def get_markets(self) -> List[str]:
        """Obtiene lista de mercados"""
        cache_key = "markets_list"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        try:
            resp = self._session.get(f"{self.base_url}/spot/market", timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 0:
                    markets = [m.get('market') for m in data.get('data', [])]
                    self.cache.set(cache_key, markets)
                    return markets
        except Exception as e:
            log_error(f"Error getting markets: {e}")
        
        return []
    
    def get_tickers_batch(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Obtiene tickers en lotes"""
        result = {}
        
        uncached = []
        for sym in symbols:
            cached = self.cache.get(f"ticker_{sym}")
            if cached is not None:
                result[sym] = cached
            else:
                uncached.append(sym)
        
        if not uncached:
            return result
        
        for i in range(0, len(uncached), 10):
            batch = uncached[i:i+10]
            market_param = ",".join(batch)
            
            try:
                resp = self._session.get(
                    f"{self.base_url}/spot/ticker",
                    params={"market": market_param},
                    timeout=30
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('code') == 0:
                        for item in data.get('data', []):
                            sym = item.get('market')
                            if sym:
                                result[sym] = item
                                self.cache.set(f"ticker_{sym}", item)
            except Exception as e:
                log_error(f"Error getting tickers batch: {e}")
        
        return result
    
    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Obtiene ticker para un símbolo"""
        cache_key = f"ticker_{symbol}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        try:
            resp = self._session.get(
                f"{self.base_url}/spot/ticker",
                params={"market": symbol},
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 0:
                    items = data.get('data', [])
                    if items:
                        ticker = items[0]
                        self.cache.set(cache_key, ticker)
                        return ticker
        except Exception as e:
            log_error(f"Error getting ticker {symbol}: {e}")
        
        return {}
    
    def get_depth(self, symbol: str, limit: int = 10) -> Dict[str, Any]:
        """Obtiene profundidad"""
        try:
            resp = self._session.get(
                f"{self.base_url}/spot/market/depth",
                params={"market": symbol, "limit": limit},
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 0:
                    return data.get('data', {})
        except Exception as e:
            log_error(f"Error getting depth {symbol}: {e}")
        
        return {}
    
    def get_klines(self, symbol: str, period: str = "1hour", limit: int = 168) -> List[Dict[str, Any]]:
        """Obtiene klines"""
        try:
            resp = self._session.get(
                f"{self.base_url}/spot/kline",
                params={"market": symbol, "period": period, "limit": limit},
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 0:
                    return data.get('data', [])
        except Exception as e:
            log_error(f"Error getting klines {symbol}: {e}")
        
        return []
    
    def get_historical_changes(self, symbol: str) -> Tuple[float, float]:
        """Obtiene cambios históricos 1h y 7d"""
        try:
            klines_1h = self.get_klines(symbol, "1hour", 5)
            klines_7d = self.get_klines(symbol, "1day", 5)
            
            change_1h = 0.0
            change_7d = 0.0
            
            if klines_1h and len(klines_1h) >= 2:
                k = klines_1h[-1]
                price_1h_ago = float(k.get('open', 0))
                price_current = float(k.get('close', 0))
                if price_1h_ago > 0:
                    change_1h = ((price_current - price_1h_ago) / price_1h_ago) * 100
            
            if klines_7d and len(klines_7d) >= 2:
                k = klines_7d[-1]
                price_7d_ago = float(k.get('open', 0))
                price_current = float(k.get('close', 0))
                if price_7d_ago > 0:
                    change_7d = ((price_current - price_7d_ago) / price_7d_ago) * 100
            
            return change_1h, change_7d
        except Exception as e:
            log_error(f"Error getting historical changes for {symbol}: {e}")
            return 0.0, 0.0
    
    def get_all_usdt_tickers(self) -> Dict[str, Dict[str, Any]]:
        """Obtiene todos los tickers USDT"""
        markets = self.get_markets()
        usdt_markets = [m for m in markets if m.endswith('USDT')]
        return self.get_tickers_batch(usdt_markets)
    
    def close(self) -> None:
        """Cierra sesión"""
        try:
            self._session.close()
        except:
            pass


# Instancia global
api_client = AsyncAPIClient()


# Funciones de conveniencia (compatibilidad)
def get_all_tickers() -> Dict[str, Dict[str, Any]]:
    return api_client.get_all_usdt_tickers()

def get_ticker(symbol: str) -> Dict[str, Any]:
    return api_client.get_ticker(symbol)

def get_markets() -> List[str]:
    return api_client.get_markets()

def get_klines(symbol: str, period: str = "1hour", limit: int = 168) -> List[Dict[str, Any]]:
    return api_client.get_klines(symbol, period, limit)

def get_historical_changes(symbol: str) -> Tuple[float, float]:
    return api_client.get_historical_changes(symbol)

def get_depth(symbol: str, limit: int = 10) -> Dict[str, Any]:
    return api_client.get_depth(symbol, limit)