"""
=================================================================
ANALYZER.PY - Momentum Analyzer (REFACTORIZADO v2.0)
=================================================================
Analizador de momentum que integra:
- Scoring ponderado
- Filtros dinámicos
- Gestión de riesgo
- Métricas
=================================================================
"""
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from config_loader import config, load_state, save_state
from logger import bot_logger, log_debug, log_info, log_warning
import api_client
import scoring
import filters as dyn_filters
import filters
import risk_manager
import metrics


class MomentumAnalyzer:
    """
    Analizador de momentum con todas las mejoras.
    """
    
    def __init__(self):
        self.quote = config.get('market.quote', 'USDT')
        self.top_n = 20  # top candidatos a analizar
        
        # Referencias a módulos
        self.api = api_client.api_client
        self.risk_mgr = risk_manager.risk_manager
        self.filter_mgr = dyn_filters.dynamic_filters
        self.metrics_mgr = metrics.metrics_manager
    
    def _log_step(self, step: int, message: str) -> None:
        """Log de paso compatibilidad"""
        # Console log (original style)
        print(f"[PASO {step}/7] {message}")
        # File log via logger (debug level for granularity)
        log_debug(f"[PASO {step}/7] {message}")
    
    async def analyze(
        self,
        tickers: Dict[str, Dict[str, Any]],
        state: Dict[str, Any]
    ) -> Tuple[Optional[scoring.TickerData], Optional[scoring.TickerData], str]:
        """
        Ejecuta análisis completo.
        
        Returns:
            (current_enriched, best_candidate, action_reason)
        """
        holding = state.get('holding', '')
        
        # Incrementar ciclo
        cycle_num = self.metrics_mgr.increment_cycle()
        self._log_step(1, f"INICIO CICLO {cycle_num}")
        
        # Log detallado
        log_section(f"CICLO {cycle_num}")
        log_info("[1] Consultando API de CoinEx...")
        
        if not holding:
            log_info("No hay posición activa. Buscando candidato inicial...")
            candidate = await self._find_initial_candidate(tickers)
            if candidate:
                return None, candidate, "initial_setup"
            return None, None, "no_candidates"
        
        # Enrich holding actual
        self._log_step(2, f"Enriqueciendo holding: {holding}")
        current = await self._enrich_holding(holding, tickers)
        
        if not current:
            log_warning(f"No se pudo obtener datos para {holding}")
            return current, None, "no_holding_data"
        
        # Chequear riesgo
        self._log_step(3, f"Verificando riesgo para {holding}")
        risk_signals = await self.risk_mgr.analyze_position(state, tickers.get(holding, {}))
        
        if risk_signals.should_stop_loss:
            self.metrics_mgr.record_rotation(successful=False)
            self.risk_mgr.add_cooldown(holding)
            current = await self._update_price(current, tickers.get(holding, {}))
            return current, None, f"STOP_LOSS: {risk_signals.stop_loss_reason}"
        
        if risk_signals.should_take_profit:
            self.metrics_mgr.record_rotation(successful=True)
            self.risk_mgr.add_cooldown(holding)
            current = await self._update_price(current, tickers.get(holding, {}))
            return current, None, f"TAKE_PROFIT: {risk_signals.take_profit_reason}"
        
        if risk_signals.should_trailing_stop:
            self.metrics_mgr.record_rotation(successful=True)
            self.risk_mgr.add_cooldown(holding)
            current = await self._update_price(current, tickers.get(holding, {}))
            return current, None, "TRAILING_STOP"
        
        if risk_signals.should_cooldown:
            self._log_step(3, f"{holding} en cooldown")
            return current, None, "cooldown"
        
        # Buscar candidatos
        self._log_step(4, "Buscando candidatos...")
        candidates = await self._find_candidates(tickers, holding)
        
        if not candidates:
            self._log_step(4, "No hay candidatos válidos")
            return current, None, "no_candidates"
        
        # Calcular scores
        self._log_step(5, "Calculando scores...")
        best = await self._select_best_candidate(candidates, current, state)
        
        if not best:
            self._log_step(5, "Ningún candidato supera el umbral")
            return current, None, "no_valid_candidate"
        
        # Verificar correlación
        self._log_step(6, f"Verificando correlación {holding} vs {best.symbol}...")
        corr = scoring.calculate_correlation(holding, best.symbol, 24)
        
        if corr > 0.85:
            log_warning(f"Correlación muy alta: {corr:.2f}, manteniendo {holding}")
            return current, None, f"high_correlation: {corr:.2f}"
        
        # Decidir acción
        self._log_step(7, "Decidiendo rotación...")
        action = self._decide_rotation(current, best)
        
        reason = f"rotate: {holding} -> {best.symbol}"
        
        log_info(f"*** OPORTUNIDAD: {holding} -> {best.symbol}")
        log_info(f"    Score: {best.score:.3f} | Cambio 24h: {best.change_24h:+.2f}% | Vol: ${best.value:,.0f}")
        
        metrics.log_opportunity(
            holding, best.symbol,
            best.score, best.change_24h, best.value
        )
        
        return current, best, reason
    
    async def _enrich_holding(
        self, 
        holding: str, 
        tickers: Dict[str, Dict[str, Any]]
    ) -> Optional[scoring.TickerData]:
        """Enriquece datos del holding"""
        # Añadir USDT si no lo tiene
        if not holding.endswith('USDT'):
            holding = holding + 'USDT'
        
        ticker = tickers.get(holding, {})
        if not ticker:
            # Fetch si no está en cache (añadir USDT si falta)
            if not holding.endswith('USDT'):
                holding = holding + 'USDT'
            ticker = self.api.get_ticker(holding)
            if not ticker:
                return None
        
        data = scoring.enrich_ticker(ticker, holding)
        
        # Enrich con historia
        data = scoring.enrich_with_history(data)
        
        # ATR para stop-loss dinámico
        data.atr = scoring.calculate_atr(holding, self.risk_mgr.atr_period)
        
        return data
    
    def _update_price(
        self,
        data: scoring.TickerData,
        ticker: Dict[str, Any]
    ) -> scoring.TickerData:
        """Actualiza precio actual"""
        if ticker:
            data.last = float(ticker.get('last', data.last))
            data.change_24h = scoring.calc_change(
                float(ticker.get('open', data.open)),
                data.last
            )
        return data
    
    async def _find_initial_candidate(
        self,
        tickers: Dict[str, Dict[str, Any]]
    ) -> Optional[scoring.TickerData]:
        """Encuentra candidato inicial"""
        candidates_data = []
        
        # Top-change filters
        top_change = filters.get_top_by_change(tickers, self.top_n * 2)
        
        for sym, _ in top_change:
            if sym == 'BTCUSDT':
                continue
            
            ticker = tickers.get(sym, {})
            if not ticker:
                continue
            
            data = scoring.enrich_ticker(ticker, sym)
            # Enrich con historia para uso de filtros y scoring
            data = scoring.enrich_with_history(data)
            
            # Aplicar todos los filtros (incluye filtros basicos)
            passed, reason = await self.filter_mgr.apply_all_filters(data)
            if not passed:
                data.is_filtered = True
                data.filter_reason = reason
                continue
            
            # Calcular score considerando 1h/24h/7d tras enriquecimiento
            score = data.change_24h * 0.5 + data.change_1h * 0.2 + data.change_7d * 0.3
            data.score = score
            
            candidates_data.append(data)
        
        if candidates_data:
            candidates_data.sort(key=lambda x: x.score, reverse=True)
            return candidates_data[0]
        
        return None
    
    async def _find_candidates(
        self,
        tickers: Dict[str, Dict[str, Any]],
        exclude: str
    ) -> List[scoring.TickerData]:
        """Encuentra candidatos"""
        candidates_data = []
        
        # Volume + change filter
        vol_filtered = filters.filter_by_volume(
            tickers, 
            config.get('market.min_volume_usd', 500000)
        )
        
        change_filtered = filters.filter_by_change(vol_filtered, 0.0)
        
        # Get BTC reference
        btc_ticker = tickers.get('BTCUSDT', {})
        btc_change = 0.0
        if btc_ticker:
            btc_change = scoring.calc_change(
                float(btc_ticker.get('open', 0)),
                float(btc_ticker.get('last', 0))
            )
        
        for sym in change_filtered:
            if sym == exclude or sym == 'BTCUSDT' or not sym.endswith(self.quote):
                continue
            
            # Skip cooldown
            if self.risk_mgr.is_in_cooldown(sym):
                continue
            
            ticker = tickers.get(sym, {})
            if not ticker:
                continue
            
            data = scoring.enrich_ticker(ticker, sym)
            
            # Apply filters
            passed, reason = await self.filter_mgr.apply_all_filters(data)
            if not passed:
                log_debug(f"  {sym}: filtrado - {reason}")
                continue
            
            # Enrich con historia
            data = scoring.enrich_with_history(data)
            
            # RS vs BTC
            data = scoring.calculate_relative_strength_vs_btc(data, btc_change)
            
            # Relative volume
            scoring.check_volume_ma_ratio(data)
            
            candidates_data.append(data)
        
        return candidates_data
    
    async def _select_best_candidate(
        self,
        candidates: List[scoring.TickerData],
        current: scoring.TickerData,
        state: Dict[str, Any]
    ) -> Optional[scoring.TickerData]:
        """Selecciona mejor candidato"""
        best = scoring.select_best_candidate(candidates, current)
        
        if best:
            log_debug(f"Mejor candidato: {best.symbol} (score: {best.score:.3f})")
        else:
            log_debug("Ningún candidato pasó el scoring")
        
        return best
    
    def _decide_rotation(
        self,
        current: scoring.TickerData,
        candidate: scoring.TickerData
    ) -> str:
        """Decide si rotar"""
        rotation_pct = self.risk_mgr.rotation_percentage
        
        if rotation_pct < 100 and current.score > self.risk_mgr.min_holding_strength:
            return "partial_rotate"
        
        return "full_rotate"
    
    def get_best_momentum(
        self,
        tickers: Dict[str, Dict[str, Any]],
        quote: str = "USDT",
        top_n: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Función de compatibilidad con formato original.
        """
        candidates = filters.get_candidates(tickers, quote, top_n * 2)
        
        result = []
        for c in candidates[:top_n]:
            result.append({
                "symbol": c["symbol"],
                "vol": c["volume"],
                "change_24h": c["change_24h"],
                "price": c["price"],
                "score": c["change_24h"]
            })
        
        return result
    
    def analyze_swap_opportunity(
        self,
        current_symbol: str,
        current_ticker: Dict[str, Any],
        candidate_symbol: str,
        candidate_ticker: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Función de compatibilidad con formato original.
        """
        return None, "deprecated_use_analyzer_class"


# Instancia global
analyzer = MomentumAnalyzer()


# ============================================================================
# COMPATIBILITY FUNCTIONS
# ============================================================================

def get_top_momentum(
    tickers: Dict[str, Dict[str, Any]],
    base_symbols: List[str] = None,
    top_n: int = 10
) -> List[Dict[str, Any]]:
    """
    Función de compatibilidad.
    """
    if base_symbols is None:
        base_symbols = ["USDT"]
    
    quote = base_symbols[0] if base_symbols else "USDT"
    return analyzer.get_best_momentum(tickers, quote, top_n)


def analyze_swap_opportunity(
    current_symbol: str,
    current_ticker: Dict[str, Any],
    candidate_symbol: str,
    candidate_ticker: Dict[str, Any]
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Función de compatibilidad.
    """
    return analyzer.analyze_swap_opportunity(
        current_symbol, current_ticker,
        candidate_symbol, candidate_ticker
    )
