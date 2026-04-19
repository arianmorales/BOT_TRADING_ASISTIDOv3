"""
=================================================================
METRICS.PY - Professional Metrics & Logging System
=================================================================
Sistema de métricas:
- JSON estructurado en metrics.json
- Métricas detalladas por ciclo
- Tracking de PnL, drawdown, tiempo de hold
- Separación de logs por nivel
=================================================================
"""
import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from collections import defaultdict

from config_loader import config
from logger import bot_logger, log_info, log_debug, log_warning, log_error, log_trade


@dataclass
class CycleMetrics:
    """Métricas de un ciclo"""
    ciclo: int
    timestamp: str
    holding: str
    holding_score: float
    holding_change_24h: float
    best_candidate: str
    candidate_score: float
    candidate_change_24h: float
    action: str  # hold, rotate, stop_loss, take_profit, cooldown
    pnl_acumulado_pct: float
    max_drawdown_pct: float
    rotaciones_exitosas: int
    falsas_senales: int
    tiempo_hold_promedio_h: float
    volumen_holding: float
    volumen_candidato: int
    precio_entrada: float
    precio_actual: float
    reason: str


@dataclass
class TradeMetrics:
    """Métricas de una operación"""
    timestamp: str
    action: str  # buy, sell, rotate, stop_loss, take_profit
    symbol_from: str
    symbol_to: str
    amount: float
    price_from: float
    price_to: float
    pnl_pct: float
    hold_time_h: float
    reason: str


class MetricsManager:
    """
    Gestor de métricas profesional.
    """
    
    def __init__(self):
        self.metrics_cfg = config.metrics
        
        self.metrics_file = self.metrics_cfg.get('metrics_file', 'metrics.json')
        self.save_interval = self.metrics_cfg.get('save_interval', 1)
        self.track_pnl = self.metrics_cfg.get('track_pnl', True)
        self.track_drawdown = self.metrics_cfg.get('track_drawdown', True)
        self.track_hold_time = self.metrics_cfg.get('track_hold_time', True)
        self.track_false_signals = self.metrics_cfg.get('track_false_signals', True)
        
        # Estado interno
        self._cycle_count = 0
        self._total_rotations = 0
        self._successful_rotations = 0
        self._false_signals = 0
        self._pnl_history: List[float] = []
        self._hold_times: List[float] = []
        self._entry_time: Optional[datetime] = None
        
        # Carga inicial
        self._load()
    
    def _load(self) -> None:
        """Carga métricas desde archivo"""
        try:
            if self.metrics_cfg.get('save_to_json', True):
                if self.metrics_file:
                    with open(self.metrics_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self._cycle_count = data.get('cycle_count', 0)
                        self._total_rotations = data.get('total_rotations', 0)
                        self._successful_rotations = data.get('successful_rotations', 0)
                        self._false_signals = data.get('false_signals', 0)
                        self._pnl_history = data.get('pnl_history', [])
        except Exception as e:
            log_warning(f"Could not load metrics: {e}")
    
    def _save(self) -> None:
        """Guarda métricas a archivo"""
        if not self.metrics_cfg.get('save_to_json', True):
            return
        
        state = {
            "cycle_count": self._cycle_count,
            "total_rotations": self._total_rotations,
            "successful_rotations": self._successful_rotations,
            "false_signals": self._false_signals,
            "pnl_history": self._pnl_history[-100:],  # últimos 100
            "last_update": datetime.now().isoformat()
        }
        
        try:
            with open(self.metrics_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log_error(f"Error saving metrics: {e}")
    
    def increment_cycle(self) -> int:
        """Incrementa contador de ciclos"""
        self._cycle_count += 1
        return self._cycle_count
    
    def record_rotation(self, successful: bool = True) -> None:
        """Registra una rotación"""
        self._total_rotations += 1
        if successful:
            self._successful_rotations += 1
    
    def record_false_signal(self) -> None:
        """Registra una falsa señal"""
        self._false_signals += 1
    
    def record_pnl(self, pnl_pct: float) -> None:
        """Registra PnL"""
        self._pnl_history.append(pnl_pct)
        if len(self._pnl_history) > 100:
            self._pnl_history = self._pnl_history[-100:]
    
    def record_hold_time(self, hours: float) -> None:
        """Registra tiempo de hold"""
        self._hold_times.append(hours)
        if len(self._hold_times) > 100:
            self._hold_times = self._hold_times[-100:]
    
    def set_entry_time(self, timestamp: Optional[str] = None) -> None:
        """Marca tiempo de entrada"""
        if timestamp:
            self._entry_time = datetime.fromisoformat(timestamp)
        else:
            self._entry_time = datetime.now()
    
    def calculate_pnl_acumulado(self) -> float:
        """Calcula PnL acumulado"""
        if not self._pnl_history:
            return 0.0
        total = sum(self._pnl_history)
        return total / len(self._pnl_history)
    
    def calculate_max_drawdown(self) -> float:
        """Calcula drawdown máximo"""
        if not self._pnl_history:
            return 0.0
        
        peak = self._pnl_history[0]
        max_dd = 0.0
        
        for pnl in self._pnl_history:
            if pnl > peak:
                peak = pnl
            dd = (peak - pnl) / abs(peak) * 100 if peak != 0 else 0
            if dd > max_dd:
                max_dd = dd
        
        return max_dd
    
    def calculate_avg_hold_time(self) -> float:
        """Calcula tiempo promedio de hold"""
        if not self._hold_times:
            return 0.0
        return sum(self._hold_times) / len(self._hold_times)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Retorna resumen de métricas"""
        return {
            "cycle_count": self._cycle_count,
            "total_rotations": self._total_rotations,
            "successful_rotations": self._successful_rotations,
            "false_signals": self._false_signals,
            "success_rate": (self._successful_rotations / self._total_rotations * 100) 
                          if self._total_rotations > 0 else 0,
            "pnl_promedio": self.calculate_pnl_acumulado(),
            "max_drawdown": self.calculate_max_drawdown(),
            "tiempo_hold_promedio_h": self.calculate_avg_hold_time()
        }
    
    def build_cycle_metrics(
        self,
        holding: str,
        holding_score: float,
        holding_change_24h: float,
        best_candidate: str,
        candidate_score: float,
        candidate_change_24h: float,
        action: str,
        reason: str,
        volumen_holding: float = 0,
        volumen_candidato: int = 0,
        precio_entrada: float = 0,
        precio_actual: float = 0
    ) -> CycleMetrics:
        """Construye métricas del ciclo"""
        hold_time_h = 0.0
        if self._entry_time:
            hold_time_h = (datetime.now() - self._entry_time).total_seconds() / 3600
        
        return CycleMetrics(
            ciclo=self._cycle_count,
            timestamp=datetime.now().isoformat(),
            holding=holding,
            holding_score=holding_score,
            holding_change_24h=holding_change_24h,
            best_candidate=best_candidate,
            candidate_score=candidate_score,
            candidate_change_24h=candidate_change_24h,
            action=action,
            pnl_acumulado_pct=self.calculate_pnl_acumulado(),
            max_drawdown_pct=self.calculate_max_drawdown(),
            rotaciones_exitosas=self._successful_rotations,
            falsas_senales=self._false_signals,
            tiempo_hold_promedio_h=self.calculate_avg_hold_time(),
            volumen_holding=volumen_holding,
            volumen_candidato=volumen_candidato,
            precio_entrada=precio_entrada,
            precio_actual=precio_actual,
            reason=reason
        )
    
    def log_cycle(self, metrics: CycleMetrics) -> None:
        """Loggea métricas del ciclo"""
        log_info(f"=== CICLO {metrics.ciclo} ===")
        log_info(f"Holding: {metrics.holding} | Score: {metrics.holding_score:.3f} | 24h: {metrics.holding_change_24h:+.2f}%")
        
        if metrics.best_candidate:
            log_info(f"Candidato: {metrics.best_candidate} | Score: {metrics.candidate_score:.3f} | 24h: {metrics.candidate_change_24h:+.2f}%")
        
        log_info(f"Acción: {metrics.action} | Razón: {metrics.reason}")
        log_info(f"PnL Acumulado: {metrics.pnl_acumulado_pct:+.2f}% | Drawdown: {metrics.max_drawdown_pct:.2f}%")
        
        log_info(f"Rotaciones: {metrics.rotaciones_exitosas}/{self._total_rotations} | "
                f"Falsas señales: {metrics.falsas_senales}")
        
        # También al log de trades para debugging
        log_debug(f"CYCLE|{metrics.ciclo}|{metrics.holding}|{metrics.best_candidate}|"
                  f"{metrics.action}|{metrics.reason}")
    
    def save_metrics(self) -> None:
        """Guarda métricas periódicamente"""
        if self._cycle_count % self.save_interval == 0:
            self._save()


# Instancia global
metrics_manager = MetricsManager()


# ============================================================================
# LOGGING STRUCTURED
# ============================================================================

def log_market_data(tickers: Dict[str, Any], count: int = 10) -> None:
    """Loggea datos de mercado"""
    log_debug(f"=== MERCADO: {len(tickers)} tickers ===")
    
    # Top volumen
    sorted_by_vol = sorted(
        [(s, float(t.get('value', 0))) for s, t in tickers.items()],
        key=lambda x: x[1], reverse=True
    )[:count]
    
    for sym, vol in sorted_by_vol:
        ticker = tickers[sym]
        last = float(ticker.get('last', 0))
        open_p = float(ticker.get('open', 0))
        change = ((last - open_p) / open_p * 100) if open_p > 0 else 0
        log_debug(f"  {sym}: ${vol:,.0f} | {last:.6f} | {change:+.2f}%")


def log_opportunity(from_sym: str, to_sym: str, score: float, 
                   change_24h: float, volume: float) -> None:
    """Loggea oportunidad encontrada"""
    log_trade(f"OPORTUNIDAD: {from_sym} -> {to_sym}")
    log_trade(f"  Score: {score:.3f} | Cambio 24h: {change_24h:+.2f}% | Volumen: ${volume:,.0f}")


def log_rotation(action: str, from_sym: str, to_sym: str, 
                amount: float, price_from: float, price_to: float) -> None:
    """Loggea operación de rotación"""
    pnl = ((price_to - price_from) / price_from * 100) if price_from > 0 else 0
    log_trade(f"ROTATION: {action}")
    log_trade(f"  {from_sym} -> {to_sym}")
    log_trade(f"  Cantidad: {amount} | Precio: {price_from} -> {price_to}")
    log_trade(f"  PnL: {pnl:+.2f}%")


def log_risk_check(risk_type: str, triggered: bool, details: str) -> None:
    """Loggea chequeo de riesgo"""
    status = "TRIGGERED" if triggered else "OK"
    log_debug(f"RISK|{risk_type}|{status}|{details}")


def log_error_detailed(error_type: str, details: str, exc: Exception = None) -> None:
    """Loggea error detallado"""
    log_error(f"ERROR|{error_type}|{details}", exc_info=True)
    if exc:
        log_debug(f"EXCEPTION: {type(exc).__name__}: {str(exc)}")


def format_metrics_json(metrics: CycleMetrics) -> str:
    """Formatea métricas como JSON para logging"""
    return json.dumps(asdict(metrics), ensure_ascii=False)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_cycle_count() -> int:
    """Obtiene contador de ciclos"""
    return metrics_manager._cycle_count


def increment_cycle() -> int:
    """Incrementa ciclo"""
    return metrics_manager.increment_cycle()


def record_rotation(successful: bool = True) -> None:
    """Registra rotación"""
    metrics_manager.record_rotation(successful)


def record_false_signal() -> None:
    """Registra falsa señal"""
    metrics_manager.record_false_signal()


def get_summary() -> Dict[str, Any]:
    """Obtiene resumen"""
    return metrics_manager.get_metrics_summary()