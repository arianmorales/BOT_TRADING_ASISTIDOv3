"""
=================================================================
API_CLIENT.PY - Async API Client with LRU Cache
=================================================================
Cliente API asíncrono para CoinEx con cache LRU y aiohttp.
=================================================================
"""
import time
import json
import hashlib
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from collections import OrderedDict
import aiohttp

from config_loader import config
from logger import log_debug, log_error


class LRUCacheEntry:
    """Entrada de cache LRU con TTL"""
    def __init__(self, data: Any, timestamp: float, ttl: int):
        self.data = data
        self.timestamp = timestamp
        self.ttl = ttl
    
    def is_expired(self) -> bool:
        return (time.time() - self.timestamp) > self.ttl


class LRUCache:
    """Cache LRU con tamaño máximo y TTL"""
    def __init__(self, max_size: int = 1000, tickers_ttl: int = 300, klines_ttl: int = 600):
        self.max_size = max_size
        self.tickers_ttl = tickers_ttl
        self.klines_ttl = klines_ttl
        self._cache: Dict[str, LRUCacheEntry] = {}
        self._ordered_keys: List[str] = []  # Para tracking LRU manual
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            entry = self._cache[key]
            if not entry.is_expired():
                # Move to end (most recently used)
                self._ordered_keys.remove(key)
                self._ordered_keys.append(key)
                self._hits += 1
                return entry.data
            else:
                del self._cache[key]
                if key in self._ordered_keys:
                    self._ordered_keys.remove(key)
        self._misses += 1
        return None
    
    def set(self, key: str, data: Any, ttl: Optional[int] = None) -> None:
        if 'ticker' in key.lower():
            ttl = ttl or self.tickers_ttl
        elif 'kline' in key.lower():
            ttl = ttl or self.klines_ttl
        else:
            ttl = ttl or 300
        
        # Remove oldest if at capacity
        if len(self._cache) >= self.max_size and key not in self._cache:
            oldest_key = self._ordered_keys.pop(0)
            if oldest_key in self._cache:
                del self._cache[oldest_key]
        
        # Update or add
        if key not in self._cache:
            self._ordered_keys.append(key)
        self._cache[key] = LRUCacheEntry(data, time.time(), ttl)
    
    def invalidate_symbol(self, symbol: str) -> None:
        keys_to_remove = [k for k in self._cache.keys() if symbol in k]
        for key in keys_to_remove:
            del self._cache[key]
            if key in self._ordered_keys:
                self._ordered_keys.remove(key)
    
    def clear(self) -> None:
        self._cache.clear()
        self._ordered_keys.clear()
    
    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0
    
    def stats(self) -> Dict[str, Any]:
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self.hit_rate:.2%}"
        }


class AsyncAPIClient:
    """Cliente API asíncrono para CoinEx con aiohttp"""
    
    _instance: Optional['AsyncAPIClient'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self.base_url = config.get('market.base_api', 'https://api.coinex.com/v2')
            self.cache = LRUCache(
                max_size=config.get('cache.max_size', 1000),
                tickers_ttl=config.get('cache.tickers_ttl', 300),
                klines_ttl=config.get('cache.klines_ttl', 600)
            )
            
            self._session: Optional[aiohttp.ClientSession] = None
            self._initialized = True
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Obtiene o crea sesión aiohttp"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            connector = aiohttp.TCPConnector(limit=50, ttl_dns_cache=300)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={'User-Agent': 'QuantumMomentumBot/2.0'}
            )
        return self._session
    
    async def get_markets(self) -> List[str]:
        """Obtiene lista de mercados"""
        cache_key = "markets_list"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/spot/market") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('code') == 0:
                        markets = [m.get('market') for m in data.get('data', [])]
                        self.cache.set(cache_key, markets)
                        return markets
        except Exception as e:
            log_error(f"Error getting markets: {e}")
        
        return []
    
    async def get_tickers_batch(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Obtiene tickers en lotes de forma asíncrona"""
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
        
        # Procesar en lotes de 10 concurrentemente
        batch_size = 10
        tasks = []
        
        for i in range(0, len(uncached), batch_size):
            batch = uncached[i:i+batch_size]
            market_param = ",".join(batch)
            tasks.append(self._fetch_ticker_batch(market_param))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for res in results:
            if isinstance(res, dict):
                for sym, item in res.items():
                    result[sym] = item
                    self.cache.set(f"ticker_{sym}", item)
        
        return result
    
    async def _fetch_ticker_batch(self, market_param: str) -> Dict[str, Dict[str, Any]]:
        """Fetch interno para lote de tickers"""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/spot/ticker",
                params={"market": market_param}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('code') == 0:
                        return {
                            item.get('market'): item 
                            for item in data.get('data', []) 
                            if item.get('market')
                        }
        except Exception as e:
            log_error(f"Error fetching ticker batch {market_param}: {e}")
        return {}
    
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Obtiene ticker para un símbolo"""
        cache_key = f"ticker_{symbol}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/spot/ticker",
                params={"market": symbol}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('code') == 0:
                        items = data.get('data', [])
                        if items:
                            ticker = items[0]
                            self.cache.set(cache_key, ticker)
                            return ticker
        except Exception as e:
            log_error(f"Error getting ticker {symbol}: {e}")
        
        return {}
    
    async def get_depth(self, symbol: str, limit: int = 10) -> Dict[str, Any]:
        """Obtiene profundidad"""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/spot/market/depth",
                params={"market": symbol, "limit": limit}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('code') == 0:
                        return data.get('data', {})
        except Exception as e:
            log_error(f"Error getting depth {symbol}: {e}")
        
        return {}
    
    async def get_klines(self, symbol: str, period: str = "1hour", limit: int = 168) -> List[Dict[str, Any]]:
        """Obtiene klines"""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/spot/kline",
                params={"market": symbol, "period": period, "limit": limit}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('code') == 0:
                        return data.get('data', [])
        except Exception as e:
            log_error(f"Error getting klines {symbol}: {e}")
        
        return []
    
    async def get_historical_changes(self, symbol: str) -> Tuple[float, float]:
        """Obtiene cambios históricos 1h y 7d"""
        try:
            klines_1h, klines_7d = await asyncio.gather(
                self.get_klines(symbol, "1hour", 5),
                self.get_klines(symbol, "1day", 5)
            )
            
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
    
    async def get_all_usdt_tickers(self) -> Dict[str, Dict[str, Any]]:
        """Obtiene todos los tickers USDT"""
        markets = await self.get_markets()
        usdt_markets = [m for m in markets if m.endswith('USDT')]
        return await self.get_tickers_batch(usdt_markets)
    
    async def close(self) -> None:
        """Cierra sesión aiohttp"""
        if self._session and not self._session.closed:
            await self._session.close()


# Instancia global
api_client = AsyncAPIClient()


# Funciones de conveniencia (compatibilidad) - ahora async
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


# Wrapper sync para compatibilidad con código legacy
def _run_async(coro):
    """Ejecuta una coroutine de forma síncrona para compatibilidad"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        # Ya hay un loop corriendo (ej. en Jupyter)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return loop.run_until_complete(coro)


# Funciones wrapper sincrónicas para compatibilidad
def get_all_tickers_sync() -> Dict[str, Dict[str, Any]]:
    return _run_async(api_client.get_all_usdt_tickers())

def get_ticker_sync(symbol: str) -> Dict[str, Any]:
    return _run_async(api_client.get_ticker(symbol))

def get_markets_sync() -> List[str]:
    return _run_async(api_client.get_markets())

def get_klines_sync(symbol: str, period: str = "1hour", limit: int = 168) -> List[Dict[str, Any]]:
    return _run_async(api_client.get_klines(symbol, period, limit))

def get_historical_changes_sync(symbol: str) -> Tuple[float, float]:
    return _run_async(api_client.get_historical_changes(symbol))

def get_depth_sync(symbol: str, limit: int = 10) -> Dict[str, Any]:
    return _run_async(api_client.get_depth(symbol, limit))