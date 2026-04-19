"""
=================================================================
RISK_MANAGER.PY - Risk Management System
=================================================================
Sistema completo de gestión de riesgo:
- Stop-Loss (fijo o ATR)
- Take-Profit + Trailing Stop
- Cooldown por par
- Drawdown máximo global
- Validación de spread
=================================================================
"""
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict

from config_loader import config, load_state, save_state
from logger import log_debug, log_warning, log_error, log_trade
import api_client
import scoring


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class RiskSignals:
    """Señales de riesgo para una posición"""
    should_stop_loss: bool = False
    should_take_profit: bool = False
    should_trailing_stop: bool = False
    should_rotate: bool = False
    should_cooldown: bool = False
    spread_too_high: bool = False
    
    # Razones
    stop_loss_reason: str = ""
    take_profit_reason: str = ""
    cooldown_symbol: str = ""


@dataclass
class Position:
    """posición activa"""
    symbol: str
    amount: float
    entry_price: float
    entry_time: str
    current_price: float = 0.0
    pnl_pct: float = 0.0
    highest_price: float = 0.0  # para trailing
    trailing_activated: bool = False


# ============================================================================
# RISK MANAGER
# ============================================================================

class RiskManager:
    """
    Gestor de riesgo con todas las funcionalidades.
    """
    
    def __init__(self):
        # Cargar configuración
        risk_cfg = config.risk
        
        # Stop-Loss
        self.stop_loss_pct = risk_cfg.get('stop_loss_pct', -5.0)
        self.use_atr_stop = risk_cfg.get('use_atr_stop', False)
        self.atr_period = risk_cfg.get('atr_period', 14)
        self.atr_multiplier = risk_cfg.get('atr_multiplier', 2.0)
        
        # Take-Profit
        self.take_profit_pct = risk_cfg.get('take_profit_pct', 10.0)
        self.use_trailing_stop = risk_cfg.get('use_trailing_stop', True)
        self.trailing_trigger_pct = risk_cfg.get('trailing_trigger_pct', 3.0)
        self.trailing_distance_pct = risk_cfg.get('trailing_distance_pct', 2.0)
        
        # Cooldown
        self.cooldown_hours = risk_cfg.get('cooldown_hours', 12)
        self.cooldown_tracked_by = risk_cfg.get('cooldown_tracked_by', 'symbol')
        
        # Drawdown
        self.max_drawdown_pct = risk_cfg.get('max_drawdown_pct', 15.0)
        self.reset_on_manual_confirm = risk_cfg.get('reset_on_manual_confirm', True)
        
        # Spread
        self.max_spread_pct = risk_cfg.get('max_spread_pct', 0.0015)
        
        # Rotación Parcial
        self.rotation_percentage = risk_cfg.get('rotation_percentage', 100)
        self.min_holding_strength = risk_cfg.get('min_holding_strength_to_partially_keep', 0.3)
        
        # Estado interno
        self._cooldowns: Dict[str, datetime] = {}
        self._peak_equity: float = 0.0
        self._current_position: Optional[Position] = None
    
    def load_cooldowns(self, state: Dict[str, Any]) -> None:
        """Carga cooldowns desde el estado"""
        cooldowns = state.get('cooldowns', {})
        self._cooldowns = {
            sym: datetime.fromisoformat(ts) 
            for sym, ts in cooldowns.items()
        }
        self._peak_equity = state.get('peak_equity', 0.0)
    
    def save_cooldowns(self, state: Dict[str, Any]) -> None:
        """Guarda cooldowns al estado"""
        # Limpiar cooldowns expirados
        now = datetime.now()
        active = {
            sym: ts.isoformat()
            for sym, ts in self._cooldowns.items()
            if ts > now
        }
        state['cooldowns'] = active
        state['peak_equity'] = self._peak_equity
    
    def is_in_cooldown(self, symbol: str) -> bool:
        """Verifica si un símbolo está en cooldown"""
        if symbol in self._cooldowns:
            if self._cooldowns[symbol] > datetime.now():
                return True
            else:
                del self._cooldowns[symbol]
        return False
    
    def add_cooldown(self, symbol: str) -> None:
        """Añade un símbolo al cooldown"""
        self._cooldowns[symbol] = datetime.now() + timedelta(hours=self.cooldown_hours)
        log_debug(f"Cooldown added for {symbol}: {self.cooldown_hours}h")
    
    async def check_stop_loss(self, position: Position) -> Tuple[bool, str]:
        """
        Verifica si debe ejecutarse stop-loss.
        """
        if position.current_price <= 0:
            return False, ""
        
        pnl = ((position.current_price - position.entry_price) / position.entry_price) * 100
        
        # Stop-loss fijo
        if pnl <= self.stop_loss_pct:
            return True, f"stop_loss: {pnl:.2f}% <= {self.stop_loss_pct}%"
        
        # Stop-loss ATR
        if self.use_atr_stop:
            atr = scoring.calculate_atr(position.symbol, self.atr_period)
            if atr > 0:
                atr_stop = position.entry_price - (atr * self.atr_multiplier)
                if position.current_price <= atr_stop:
                    return True, f"atr_stop: price {position.current_price} <= atr_stop {atr_stop:.6f}"
        
        return False, ""
    
    async def check_take_profit(self, position: Position) -> Tuple[bool, str]:
        """
        Verifica si debe ejecutarse take-profit.
        """
        if position.current_price <= 0:
            return False, ""
        
        pnl = ((position.current_price - position.entry_price) / position.entry_price) * 100
        
        if pnl >= self.take_profit_pct:
            return True, f"take_profit: {pnl:.2f}% >= {self.take_profit_pct}%"
        
        return False, ""
    
    async def check_trailing_stop(self, position: Position) -> Tuple[bool, str]:
        """
        Verifica si debe ejecutarse trailing stop.
        """
        if not self.use_trailing_stop:
            return False, ""
        
        if position.current_price <= 0:
            return False, ""
        
        pnl = ((position.current_price - position.entry_price) / position.entry_price) * 100
        
        # Verificar si se alcanzó el trigger
        if not position.trailing_activated:
            if pnl >= self.trailing_trigger_pct:
                position.trailing_activated = True
                position.highest_price = position.current_price
                log_debug(f"Trailing stop activated for {position.symbol}")
            return False, ""
        
        # Calcular trailing
        if position.current_price > position.highest_price:
            position.highest_price = position.current_price
        
        trailing_distance = ((position.highest_price - position.current_price) / position.highest_price) * 100
        
        if trailing_distance >= self.trailing_distance_pct:
            return True, f"trailing_stop: {trailing_distance:.2f}% >= {self.trailing_distance_pct}%"
        
        return False, ""
    
    async def check_spread(self, symbol: str, last_price: float) -> Tuple[bool, str]:
        """
        Verifica si el spread es aceptable.
        """
        if last_price <= 0:
            return True, ""
        
        try:
            depth = await api_client.get_depth(symbol, limit=5)
            bids = depth.get('bids', [])
            asks = depth.get('asks', [])
            
            if bids and asks:
                bid = float(bids[0].get('price', 0))
                ask = float(asks[0].get('price', 0))
                spread = (ask - bid) / last_price
                
                if spread > self.max_spread_pct:
                    return False, f"spread: {spread:.4f} > {self.max_spread_pct}"
        except Exception as e:
            log_warning(f"Error checking spread for {symbol}: {e}")
        
        return True, ""
    
    def check_drawdown(self, current_equity: float) -> Tuple[bool, str]:
        """
        Verifica drawdown máximo global.
        """
        if self._peak_equity <= 0:
            self._peak_equity = current_equity
            return False, ""
        
        drawdown = ((self._peak_equity - current_equity) / self._peak_equity) * 100
        
        if drawdown >= self.max_drawdown_pct:
            return True, f"drawdown: {drawdown:.2f}% >= {self.max_drawdown_pct}%"
        
        if current_equity > self._peak_equity:
            self._peak_equity = current_equity
        
        return False, ""
    
    def should_partially_keep(self, current_score: float) -> bool:
        """
        Decide si mantener exposición parcial.
        """
        return current_score > self.min_holding_strength
    
    def calculate_rotation_amount(self, total_amount: float, rotate_full: bool = False) -> float:
        """
        Calcula cantidad a rotar basándose en configuración.
        """
        if rotate_full or self.rotation_percentage >= 100:
            return total_amount
        
        return total_amount * (self.rotation_percentage / 100)
    
    async def analyze_position(self, state: Dict[str, Any], 
                        ticker: Dict[str, Any]) -> RiskSignals:
        """
        Analiza una posición y retorna señales de riesgo.
        """
        signals = RiskSignals()
        
        if not state.get('holding') or not state.get('amount', 0) > 0:
            return signals
        
        symbol = state['holding']
        entry_price = state.get('entry_price', 0)
        amount = state.get('amount', 0)
        
        current_price = float(ticker.get('last', 0))
        
        position = Position(
            symbol=symbol,
            amount=amount,
            entry_price=entry_price,
            entry_time=state.get('entry_time', ''),
            current_price=current_price,
            highest_price=max(entry_price, current_price)
        )
        
        # Check Stop-Loss
        sl_triggered, reason = await self.check_stop_loss(position)
        signals.should_stop_loss = sl_triggered
        signals.stop_loss_reason = reason
        
        # Check Take-Profit
        tp_triggered, reason = await self.check_take_profit(position)
        signals.should_take_profit = tp_triggered
        signals.take_profit_reason = reason
        
        # Check Trailing
        ts_triggered, reason = await self.check_trailing_stop(position)
        signals.should_trailing_stop = ts_triggered
        
        # Check Spread
        spread_ok, reason = await self.check_spread(symbol, current_price)
        signals.spread_too_high = not spread_ok
        
        # Check Cooldown
        signals.should_cooldown = self.is_in_cooldown(symbol)
        
        # Check Drawdown
        equity = amount * current_price
        dd_triggered, reason = self.check_drawdown(equity)
        
        # Decisión final
        if signals.should_stop_loss:
            signals.should_rotate = True
            log_trade(f"STOP LOSS triggered for {symbol}: {reason}")
        elif signals.should_take_profit:
            signals.should_rotate = True
            log_trade(f"TAKE PROFIT triggered for {symbol}: {reason}")
        elif signals.should_trailing_stop:
            signals.should_rotate = True
            log_trade(f"TRAILING STOP triggered for {symbol}: {reason}")
        
        return signals
    
    def get_risk_summary(self, state: Dict[str, Any], 
                        current_price: float) -> Dict[str, Any]:
        """
        Retorna resumen de riesgo para la posición actual.
        """
        if not state.get('holding'):
            return {"has_position": False}
        
        entry = state.get('entry_price', 0)
        pnl = ((current_price - entry) / entry * 100) if entry > 0 else 0
        
        return {
            "has_position": True,
            "symbol": state['holding'],
            "entry": entry,
            "current": current_price,
            "pnl_pct": pnl,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "trailing_active": self.use_trailing_stop,
            "in_cooldown": self.is_in_cooldown(state['holding']),
            "peak_equity": self._peak_equity,
            "current_equity": state.get('equity', 0)
        }


# Instancia global
risk_manager = RiskManager()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def calculate_pnl(entry_price: float, current_price: float) -> float:
    """Calcula PnL porcentual"""
    if entry_price <= 0:
        return 0.0
    return ((current_price - entry_price) / entry_price) * 100


def format_pnl(pnl: float) -> str:
    """Formatea PnL para display"""
    sign = "+" if pnl >= 0 else ""
    return f"{sign}{pnl:.2f}%"


def get_stop_price(entry_price: float) -> float:
    """Calcula precio de stop-loss"""
    return entry_price * (1 + risk_manager.stop_loss_pct / 100)


def get_take_profit_price(entry_price: float) -> float:
    """Calcula precio de take-profit"""
    return entry_price * (1 + risk_manager.take_profit_pct / 100)