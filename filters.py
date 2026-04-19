"""
=================================================================
FILTERS.PY - Dynamic Liquidity & Volatility Filters
=================================================================
Sistema de filtros dinámicos:
- Ratio volumen/capitalización
- Volatilidad extrema
- Volumen relativo (vs media 7 días)
- Todos configurables
=================================================================
"""
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from config_loader import config
from logger import log_debug
import api_client
import scoring


@dataclass
class FilterResult:
    """Resultado de filtrado"""
    passed: bool
    reason: str
    details: Dict[str, Any]


class DynamicFilters:
    """
    Filtros dinámicos configurables.
    """
    
    def __init__(self):
        filters_cfg = config.filters
        
        # Volumen mínimo
        self.min_volume_usd = config.get('market.min_volume_usd', 500000)
        
        # Volumen vs Capitalización
        self.min_vol_mcap_ratio = filters_cfg.get('min_vol_mcap_ratio', 0.0001)
        
        # Volatilidad
        self.max_volatility_24h = filters_cfg.get('max_volatility_24h', 20.0)
        self.allow_high_vol = filters_cfg.get('allow_high_volatility_mode', False)
        
        # Volumen Relativo
        self.min_relative_volume_pct = filters_cfg.get('min_relative_volume_pct', 60.0)
        self.use_volume_ma = filters_cfg.get('use_volume_ma', True)
        
        # Spread
        self.max_spread_pct = config.get('risk.max_spread_pct', 0.0015)
        
        # Mínimos
        self.min_price = filters_cfg.get('min_price', 0.0001)
        self.min_trades_24h = filters_cfg.get('min_trades_24h', 100)
    
    async def check_basic_filters(self, ticker_data: scoring.TickerData) -> FilterResult:
        """
        Filtros básicos: volumen y precio.
        """
        if ticker_data.value < self.min_volume_usd:
            return FilterResult(
                passed=False,
                reason=f"volumen bajo: ${ticker_data.value:,.0f} < ${self.min_volume_usd:,}",
                details={"volume": ticker_data.value}
            )
        
        if ticker_data.last < self.min_price:
            return FilterResult(
                passed=False,
                reason=f"precio muy bajo: {ticker_data.last}",
                details={"price": ticker_data.last}
            )
        
        return FilterResult(passed=True, reason="ok", details={})
    
    async def check_vol_mcap_ratio(self, ticker_data: scoring.TickerData) -> FilterResult:
        """
        Filtro: volumen / market cap estimado.
        """
        market_cap = ticker_data.last * ticker_data.volume
        
        if market_cap > 0:
            ratio = ticker_data.value / market_cap
            
            if ratio < self.min_vol_mcap_ratio:
                return FilterResult(
                    passed=False,
                    reason=f"vol/mcap bajo: {ratio:.6f} < {self.min_vol_mcap_ratio}",
                    details={"vol_mcap_ratio": ratio}
                )
        
        return FilterResult(passed=True, reason="ok", details={})
    
    async def check_volatility(self, ticker_data: scoring.TickerData) -> FilterResult:
        """
        Filtro: volatilidad extrema.
        """
        abs_change = abs(ticker_data.change_24h)
        
        if abs_change > self.max_volatility_24h:
            if not self.allow_high_vol:
                return FilterResult(
                    passed=False,
                    reason=f"volatilidad extrema: {abs_change:.2f}% > {self.max_volatility_24h}%",
                    details={"change_24h": ticker_data.change_24h}
                )
            else:
                log_debug(f"High volatility allowed for {ticker_data.symbol}: {abs_change:.2f}%")
        
        return FilterResult(passed=True, reason="ok", details={})
    
    async def check_relative_volume(self, ticker_data: scoring.TickerData) -> FilterResult:
        """
        Filtro: volumen vs media 7 días.
        """
        if not self.use_volume_ma:
            return FilterResult(passed=True, reason="ok", details={})
        
        # Ya calculado en scoring
        if ticker_data.vol_ma_ratio < self.min_relative_volume_pct:
            return FilterResult(
                passed=False,
                reason=f"volumen bajo vs media 7d: {ticker_data.vol_ma_ratio:.1f}% < {self.min_relative_volume_pct}%",
                details={"vol_ma_ratio": ticker_data.vol_ma_ratio}
            )
        
        return FilterResult(passed=True, reason="ok", details={})
    
    async def check_spread_filter(self, ticker_data: scoring.TickerData) -> FilterResult:
        """
        Filtro: spread (ask - bid) / last.
        """
        if ticker_data.spread >= 999:  # No calculado
            try:
                scoring.check_spread(ticker_data)
            except:
                pass
        
        if ticker_data.spread < 999 and ticker_data.spread > self.max_spread_pct:
            return FilterResult(
                passed=False,
                reason=f"spread alto: {ticker_data.spread:.4f} > {self.max_spread_pct}",
                details={"spread": ticker_data.spread}
            )
        
        return FilterResult(passed=True, reason="ok", details={})
    
    async def apply_all_filters(self, ticker_data: scoring.TickerData) -> Tuple[bool, str]:
        """
        Aplica todos los filtros.
        """
        # Basic filters
        result = await self.check_basic_filters(ticker_data)
        if not result.passed:
            ticker_data.is_filtered = True
            ticker_data.filter_reason = result.reason
            return False, result.reason
        
        # Vol/MCap ratio
        result = await self.check_vol_mcap_ratio(ticker_data)
        if not result.passed:
            ticker_data.is_filtered = True
            ticker_data.filter_reason = result.reason
            return False, result.reason
        
        # Volatility
        result = await self.check_volatility(ticker_data)
        if not result.passed:
            ticker_data.is_filtered = True
            ticker_data.filter_reason = result.reason
            return False, result.reason
        
        # Relative volume
        result = await self.check_relative_volume(ticker_data)
        if not result.passed:
            ticker_data.is_filtered = True
            ticker_data.filter_reason = result.reason
            return False, result.reason
        
        # Spread
        result = await self.check_spread_filter(ticker_data)
        if not result.passed:
            ticker_data.is_filtered = True
            ticker_data.filter_reason = result.reason
            return False, result.reason
        
        return True, "passed"


def filter_by_volume(tickers: Dict[str, Dict[str, Any]], 
                   min_volume: float = 500000) -> Dict[str, Dict[str, Any]]:
    """
    Filtro simple por volumen.
    """
    return {
        sym: ticker 
        for sym, ticker in tickers.items()
        if float(ticker.get('value', 0)) >= min_volume
    }


def filter_by_change(tickers: Dict[str, Dict[str, Any]], 
                   min_change: float = 0.0) -> Dict[str, Dict[str, Any]]:
    """
    Filtro simple por cambio positivo.
    """
    result = {}
    for sym, ticker in tickers.items():
        open_p = float(ticker.get('open', 0))
        last = float(ticker.get('last', 0))
        if open_p > 0:
            change = ((last - open_p) / open_p) * 100
            if change >= min_change:
                result[sym] = ticker
    
    return result


def filter_by_price(tickers: Dict[str, Dict[str, Any]], 
                   min_price: float = 0.0001) -> Dict[str, Dict[str, Any]]:
    """
    Filtro simple por precio mínimo.
    """
    return {
        sym: ticker 
        for sym, ticker in tickers.items()
        if float(ticker.get('last', 0)) >= min_price
    }


def get_top_by_volume(tickers: Dict[str, Dict[str, Any]], 
                   top_n: int = 100) -> List[Tuple[str, float]]:
    """
    Obtiene top N pares por volumen.
    """
    volume_list = [
        (sym, float(ticker.get('value', 0)))
        for sym, ticker in tickers.items()
    ]
    
    volume_list.sort(key=lambda x: x[1], reverse=True)
    return volume_list[:top_n]


def get_top_by_change(tickers: Dict[str, Dict[str, Any]], 
                   top_n: int = 50) -> List[Tuple[str, float]]:
    """
    Obtiene top N pares por cambio 24h.
    """
    change_list = []
    for sym, ticker in tickers.items():
        open_p = float(ticker.get('open', 0))
        last = float(ticker.get('last', 0))
        if open_p > 0:
            change = ((last - open_p) / open_p) * 100
            change_list.append((sym, change))
    
    change_list.sort(key=lambda x: x[1], reverse=True)
    return change_list[:top_n]


def get_candidates(tickers: Dict[str, Dict[str, Any]], 
                 quote: str = "USDT",
                 min_volume: float = 500000,
                 min_change: float = 0.0) -> List[Dict[str, Any]]:
    """
    Generador de candidatos base.
    """
    candidates = []
    
    for symbol, ticker in tickers.items():
        if not symbol.endswith(quote) or symbol == quote:
            continue
        
        value = float(ticker.get('value', 0))
        if value < min_volume:
            continue
        
        open_p = float(ticker.get('open', 0))
        last = float(ticker.get('last', 0))
        
        if open_p <= 0 or last <= 0:
            continue
        
        change = ((last - open_p) / open_p) * 100
        
        if change < min_change:
            continue
        
        candidates.append({
            "symbol": symbol,
            "volume": value,
            "change_24h": change,
            "price": last
        })
    
    candidates.sort(key=lambda x: x["change_24h"], reverse=True)
    return candidates


# Instancia global
dynamic_filters = DynamicFilters()


# Alias para compatibilidad
def apply_filters(ticker_data: scoring.TickerData) -> Tuple[bool, str]:
    """Wrapper de compatibilidad"""
    return asyncio.run(dynamic_filters.apply_all_filters(ticker_data))