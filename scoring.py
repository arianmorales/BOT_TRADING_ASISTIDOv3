"""
=================================================================
SCORING.PY - Weighted Scoring System (OPTIMIZADO)
=================================================================
Sistema de scoring ponderado para momentum:
- Fórmula: score = Σ max(0, cand_change_tf - curr_change_tf) * peso_tf
- Pesos configurables
- Soporte para fuerza relativa vs BTC
- Umbral mínimo configurable
- Enriquecimiento paralelo con asyncio.gather()
=================================================================
"""
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from config_loader import config
from logger import log_debug
import api_client


@dataclass
class TickerData:
    """Datos enriquecidos de un ticker"""
    symbol: str
    last: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    volume: float = 0.0
    value: float = 0.0  # volumen en USDT
    change_1h: float = 0.0
    change_24h: float = 0.0
    change_7d: float = 0.0
    
    # Enrichments
    rs_24h: float = 0.0  # Relative Strength vs BTC
    vol_ma_ratio: float = 1.0  # volumen vs media 7d
    vol_mcap_ratio: float = 0.0  # volumen / market cap estimado
    spread: float = 999.0  # (ask - bid) / last
    atr: float = 0.0
    
    # Metadatos
    is_filtered: bool = False
    filter_reason: str = ""
    score: float = 0.0
    passed: bool = False


def calc_change(open_price: float, close_price: float) -> float:
    """Calcula porcentaje de cambio"""
    if open_price <= 0:
        return 0.0
    return ((close_price - open_price) / open_price) * 100


async def enrich_ticker_async(ticker: Dict[str, Any], symbol: str) -> TickerData:
    """
    Enriquece un ticker con datos calculados (versión async).
    """
    try:
        data = TickerData(
            symbol=symbol,
            last=float(ticker.get('last', 0)),
            open=float(ticker.get('open', 0)),
            high=float(ticker.get('high', 0)),
            low=float(ticker.get('low', 0)),
            volume=float(ticker.get('volume', 0)),
            value=float(ticker.get('value', 0))
        )
        
        # Calcular change_24h desde el ticker
        data.change_24h = calc_change(data.open, data.last)
        
        return data
    except Exception as e:
        log_debug(f"Error enriching {symbol}: {e}")
        return TickerData(symbol=symbol)


def enrich_ticker(ticker: Dict[str, Any], symbol: str = "") -> TickerData:
    """
    Enriquece un ticker con datos calculados.
    """
    try:
        data = TickerData(
            symbol=symbol,
            last=float(ticker.get('last', 0)),
            open=float(ticker.get('open', 0)),
            high=float(ticker.get('high', 0)),
            low=float(ticker.get('low', 0)),
            volume=float(ticker.get('volume', 0)),
            value=float(ticker.get('value', 0))
        )
        
        # Calcular change_24h desde el ticker
        data.change_24h = calc_change(data.open, data.last)
        
        return data
    except Exception as e:
        log_debug(f"Error enriching {symbol}: {e}")
        return TickerData(symbol=symbol)


async def enrich_with_history_async(ticker_data: TickerData) -> TickerData:
    """
    Enriquece ticker con datos históricos (change_1h, change_7d) - async.
    """
    try:
        change_1h, change_7d = await api_client.api_client.get_historical_changes(ticker_data.symbol)
        ticker_data.change_1h = change_1h
        ticker_data.change_7d = change_7d
        return ticker_data
    except Exception as e:
        log_debug(f"Error enrich_with_history {ticker_data.symbol}: {e}")
        return ticker_data


def enrich_with_history(ticker_data: TickerData) -> TickerData:
    """
    Enriquece ticker con datos históricos (change_1h, change_7d).
    """
    try:
        change_1h, change_7d = api_client.get_historical_changes(ticker_data.symbol)
        ticker_data.change_1h = change_1h
        ticker_data.change_7d = change_7d
        return ticker_data
    except Exception as e:
        log_debug(f"Error enrich_with_history {ticker_data.symbol}: {e}")
        return ticker_data


async def enrich_multiple_async(tickers_data: List[TickerData]) -> List[TickerData]:
    """
    Enriquece múltiples tickers en paralelo con sus datos históricos.
    Optimización clave: usa asyncio.gather para llamadas concurrentes.
    """
    if not tickers_data:
        return []
    
    tasks = [enrich_with_history_async(td) for td in tickers_data]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    enriched = []
    for i, result in enumerate(results):
        if isinstance(result, TickerData):
            enriched.append(result)
        else:
            # Mantener original si hubo error
            enriched.append(tickers_data[i])
    
    return enriched


def calculate_relative_strength_vs_btc(
    candidate_ticker: TickerData,
    btc_change_24h: float
) -> TickerData:
    """
    Calcula fuerza relativa vs BTC.
    RS_24h = cand_change_24h - btc_change_24h
    """
    candidate_ticker.rs_24h = candidate_ticker.change_24h - btc_change_24h
    return candidate_ticker


def calculate_atr(ticker_symbol: str, period: int = 14) -> float:
    """
    Calcula ATR (Average True Range) para stop-loss dinámico.
    """
    try:
        klines = api_client.get_klines(ticker_symbol, "1hour", period + 1)
        
        if len(klines) < period:
            return 0.0
        
        true_ranges = []
        for i in range(1, len(klines)):
            high = float(klines[i].get('high', 0))
            low = float(klines[i].get('low', 0))
            prev_close = float(klines[i-1].get('close', 0))
            
            tr = max(
                high - low,
                abs(high - prev_close) if prev_close else 0,
                abs(low - prev_close) if prev_close else 0
            )
            true_ranges.append(tr)
        
        if true_ranges:
            return sum(true_ranges) / len(true_ranges)
        
        return 0.0
    except Exception as e:
        log_debug(f"Error calculating ATR for {ticker_symbol}: {e}")
        return 0.0


async def check_volume_ma_ratio_async(ticker_data: TickerData) -> TickerData:
    """
    Compara volumen actual vs media móvil 7 días - async.
    """
    try:
        klines = await api_client.api_client.get_klines(ticker_data.symbol, "1day", 7)
        
        if len(klines) < 7:
            return ticker_data
        
        volumes = [float(k.get('volume', 0)) for k in klines[:-1]]  # sin el actual
        avg_volume = sum(volumes) / len(volumes) if volumes else 0
        
        if avg_volume > 0:
            ticker_data.vol_ma_ratio = (ticker_data.volume / avg_volume) * 100
        
        return ticker_data
    except Exception as e:
        log_debug(f"Error checking volume MA ratio for {ticker_data.symbol}: {e}")
        return ticker_data


def check_volume_ma_ratio(ticker_data: TickerData) -> TickerData:
    """
    Compara volumen actual vs media móvil 7 días.
    """
    try:
        import asyncio
        klines = api_client.get_klines(ticker_data.symbol, "1day", 7)
        
        if len(klines) < 7:
            return ticker_data
        
        volumes = [float(k.get('volume', 0)) for k in klines[:-1]]  # sin el actual
        avg_volume = sum(volumes) / len(volumes) if volumes else 0
        
        if avg_volume > 0:
            ticker_data.vol_ma_ratio = (ticker_data.volume / avg_volume) * 100
        
        return ticker_data
    except Exception as e:
        log_debug(f"Error checking volume MA ratio for {ticker_data.symbol}: {e}")
        return ticker_data


async def check_spread_async(ticker_data: TickerData) -> TickerData:
    """
    Verifica spread (ask - bid) / last - async.
    """
    try:
        depth = await api_client.api_client.get_depth(ticker_data.symbol, limit=5)
        
        bids = depth.get('bids', [])
        asks = depth.get('asks', [])
        
        if bids and asks:
            bid = float(bids[0].get('price', 0))
            ask = float(asks[0].get('price', 0))
            
            if ticker_data.last > 0:
                ticker_data.spread = (ask - bid) / ticker_data.last
        
        return ticker_data
    except Exception as e:
        log_debug(f"Error checking spread for {ticker_data.symbol}: {e}")
        return ticker_data


def check_spread(ticker_data: TickerData) -> TickerData:
    """
    Verifica spread (ask - bid) / last.
    """
    try:
        depth = api_client.get_depth(ticker_data.symbol, limit=5)
        
        bids = depth.get('bids', [])
        asks = depth.get('asks', [])
        
        if bids and asks:
            bid = float(bids[0].get('price', 0))
            ask = float(asks[0].get('price', 0))
            
            if ticker_data.last > 0:
                ticker_data.spread = (ask - bid) / ticker_data.last
        
        return ticker_data
    except Exception as e:
        log_debug(f"Error checking spread for {ticker_data.symbol}: {e}")
        return ticker_data


async def enrich_all_async(tickers_data: List[TickerData], include_spread: bool = False, include_volume_ma: bool = True) -> List[TickerData]:
    """
    Enriquece múltiples tickers con todos los datos en paralelo.
    Optimización: todas las llamadas API se hacen concurrentemente.
    """
    if not tickers_data:
        return []
    
    # Primero enriquecer con historia
    enriched = await enrich_multiple_async(tickers_data)
    
    # Preparar tareas para volumen y spread
    tasks = []
    for td in enriched:
        task_list = []
        if include_volume_ma:
            task_list.append(check_volume_ma_ratio_async(td))
        if include_spread:
            task_list.append(check_spread_async(td))
        if task_list:
            tasks.append((td, task_list))
    
    # Ejecutar en paralelo por ticker
    if tasks:
        results = await asyncio.gather(*[asyncio.gather(*tl) for _, tl in tasks], return_exceptions=True)
        
        for i, (td, _) in enumerate(tasks):
            if i < len(results):
                res = results[i]
                if isinstance(res, (list, tuple)):
                    for r in res:
                        if isinstance(r, TickerData):
                            # Actualizar campos
                            if hasattr(r, 'vol_ma_ratio'):
                                td.vol_ma_ratio = r.vol_ma_ratio
                            if hasattr(r, 'spread'):
                                td.spread = r.spread
    
    return enriched


def calculate_momentum_score(
    current: TickerData,
    candidate: TickerData,
    weights: Optional[Dict[str, float]] = None,
    use_rs_btc: bool = False,
    min_threshold: float = 0.4
) -> Tuple[float, bool, str]:
    """
    Calcula score de momentum ponderado.
    
    Fórmula:
    score = Σ max(0, cand_change_tf - curr_change_tf) * peso_tf
    
    Args:
        current: Datos del activo actual
        candidate: Datos del candidato
        weights: Pesos {1h, 24h, 7d}
        use_rs_btc: Usar fuerza relativa vs BTC
        min_threshold: Umbral mínimo para ser válido
    
    Returns:
        (score, is_valid, reason)
    """
    # Cargar configuración por defecto
    if weights is None:
        weights = config.get('scoring.weights', {
            '1h': 0.2,
            '24h': 0.5,
            '7d': 0.3
        })
    
    if use_rs_btc:
        use_rs_btc = config.get('scoring.use_relative_strength_btc', True)
    
    min_threshold = config.get('scoring.min_score_threshold', min_threshold)
    
    log_debug(f"Calculating score: {current.symbol} -> {candidate.symbol}")
    log_debug(f"  Current: 1h={current.change_1h:+.2f}%, 24h={current.change_24h:+.2f}%, 7d={current.change_7d:+.2f}%")
    log_debug(f"  Candidate: 1h={candidate.change_1h:+.2f}%, 24h={candidate.change_24h:+.2f}%, 7d={candidate.change_7d:+.2f}%")
    
    # Calcular componentes
    score = 0.0
    components = []
    
    # 1h
    delta_1h = candidate.change_1h - current.change_1h
    if delta_1h > 0:
        score += delta_1h * weights.get('1h', 0.2)
        components.append(f"1h: {delta_1h:+.2f}*0.2={delta_1h * weights.get('1h', 0.2):+.2f}")
    
    # 24h
    delta_24h = candidate.change_24h - current.change_24h
    if delta_24h > 0:
        score += delta_24h * weights.get('24h', 0.5)
        components.append(f"24h: {delta_24h:+.2f}*0.5={delta_24h * weights.get('24h', 0.5):+.2f}")
    
    # 7d
    delta_7d = candidate.change_7d - current.change_7d
    if delta_7d > 0:
        score += delta_7d * weights.get('7d', 0.3)
        components.append(f"7d: {delta_7d:+.2f}*0.3={delta_7d * weights.get('7d', 0.3):+.2f}")
    
    # Fuerza relativa vs BTC
    if use_rs_btc and candidate.rs_24h > 0:
        rs_bonus = candidate.rs_24h * 0.1  # 10% bonus por RS positiva
        score += rs_bonus
        components.append(f"RS_BTC: +{rs_bonus:.2f}")
    
    log_debug(f"  Components: {', '.join(components)}")
    log_debug(f"  Final score: {score:.4f} (threshold: {min_threshold})")
    
    # Validar threshold
    is_valid = score >= min_threshold
    reason = f"score={score:.2f} >= {min_threshold}" if is_valid else f"score={score:.2f} < {min_threshold}"
    
    return score, is_valid, reason


async def calculate_correlation(
    symbol1: str,
    symbol2: str,
    periods: int = 24
) -> float:
    """
    Calcula correlación entre dos símbolos usando cierres de 24h.
    Retorna coeficiente de correlación (-1 a 1).
    """
    try:
        import numpy as np
        
        klines1 = api_client.get_klines(symbol1, "1day", periods)
        klines2 = api_client.get_klines(symbol2, "1day", periods)
        
        if len(klines1) < periods or len(klines2) < periods:
            return 0.0
        
        closes1 = np.array([float(k.get('close', 0)) for k in klines1])
        closes2 = np.array([float(k.get('close', 0)) for k in klines2])
        
        if np.std(closes1) == 0 or np.std(closes2) == 0:
            return 0.0
        
        corr = np.corrcoef(closes1, closes2)[0, 1]
        return corr if not np.isnan(corr) else 0.0
    except ImportError:
        log_debug("numpy not available, skipping correlation")
        return 0.0
    except Exception as e:
        log_debug(f"Error calculating correlation: {e}")
        return 0.0


def rank_candidates(
    candidates: List[TickerData],
    current: TickerData
) -> List[TickerData]:
    """
    Ordena candidatos por score descendente.
    """
    for cand in candidates:
        score, is_valid, reason = calculate_momentum_score(current, cand)
        cand.score = score
        cand.passed = is_valid
        cand.filter_reason = reason
    
    # Solo retornar los que pasaron
    passed = [c for c in candidates if c.passed]
    passed.sort(key=lambda x: x.score, reverse=True)
    
    return passed


def select_best_candidate(
    candidates: List[TickerData],
    current: TickerData
) -> Optional[TickerData]:
    """
    Selecciona el mejor candidato basándose en score.
    """
    ranked = rank_candidates(candidates, current)
    
    if ranked:
        return ranked[0]
    
    return None