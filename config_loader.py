"""
=================================================================
CONFIG_LOADER.PY - Configuration Manager
=================================================================
Carga y gestiona la configuración desde config.yaml
Mantiene compatibilidad con el formato existente de state.json
=================================================================
"""
import os
import json
import yaml
from typing import Any, Dict, Optional
from pathlib import Path


class ConfigLoader:
    """
    Administrador centralizado de configuración.
    Carga config.yaml y provee acceso tipado a todos los parámetros.
    """
    
    _instance: Optional['ConfigLoader'] = None
    _config: Optional[Dict[str, Any]] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._config is None:
            self.load()
    
    def load(self, config_path: str = "config.yaml") -> Dict[str, Any]:
        """
        Carga la configuración desde el archivo YAML.
        """
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)
        
        return self._config
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Obtiene un valor de configuración usando notación de punto.
        Ej: config.get('scoring.weights.1h')
        """
        if self._config is None:
            self.load()
        
        keys = key_path.split('.')
        value = self._config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """
        Obtiene una sección completa de configuración.
        """
        return self.get(section, {})
    
    @property
    def bot(self) -> Dict[str, Any]:
        return self.get_section('bot')
    
    @property
    def market(self) -> Dict[str, Any]:
        return self.get_section('market')
    
    @property
    def scoring(self) -> Dict[str, Any]:
        return self.get_section('scoring')
    
    @property
    def risk(self) -> Dict[str, Any]:
        return self.get_section('risk')
    
    @property
    def filters(self) -> Dict[str, Any]:
        return self.get_section('filters')
    
    @property
    def cache(self) -> Dict[str, Any]:
        return self.get_section('cache')
    
    @property
    def async_cfg(self) -> Dict[str, Any]:
        return self.get_section('async')
    
    @property
    def websocket(self) -> Dict[str, Any]:
        return self.get_section('websocket')
    
    @property
    def metrics(self) -> Dict[str, Any]:
        return self.get_section('metrics')
    
    @property
    def logging(self) -> Dict[str, Any]:
        return self.get_section('logging')
    
    @property
    def notifications(self) -> Dict[str, Any]:
        return self.get_section('notifications')
    
    def reload(self) -> None:
        """
        Recarga la configuración desde el archivo.
        """
        self._config = None
        self.load()


# Instancia global
config = ConfigLoader()


def load_state(state_file: str = "state.json") -> Dict[str, Any]:
    """
    Carga el estado del bot desde el archivo JSON existente.
    Mantiene compatibilidad con el formato actual.
    """
    default_state = {
        "holding": "",
        "amount": 0.0,
        "holding_price": 0.0,
        "entry_price": 0.0,
        "entry_time": "",
        "email": "",
        "email_password": "",
        "phone": "",
        "whatsapp_session_active": False,
        "equity": 0.0,
        "peak_equity": 0.0,
        "total_rotations": 0,
        "successful_rotations": 0,
        "false_signals": 0,
        "cooldowns": {},
        "last_cycle_time": "",
        "atr": 0.0,
        "is_paused": False,
        "pause_reason": ""
    }
    
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            # Merge con defaults para nuevos campos
            return {**default_state, **state}
        except Exception as e:
            print(f"Error loading state: {e}")
            return default_state
    
    return default_state


def save_state(state: Dict[str, Any], state_file: str = "state.json") -> None:
    """
    Guarda el estado del bot preservando el formato actual.
    """
    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def get_state_value(state: Dict[str, Any], key: str, default: Any = None) -> Any:
    """
    Obtiene un valor del estado con valor por defecto.
    """
    return state.get(key, default)


def update_state_entry(state: Dict[str, Any], symbol: str, amount: float, price: float) -> Dict[str, Any]:
    """
    Actualiza el estado cuando se entra en una posición.
    """
    from datetime import datetime
    
    state["holding"] = symbol
    state["amount"] = amount
    state["entry_price"] = price
    state["holding_price"] = price
    state["entry_time"] = datetime.now().isoformat()
    state["last_cycle_time"] = datetime.now().isoformat()
    
    return state


def update_state_exit(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Actualiza el estado cuando se sale de una posición.
    """
    state["holding"] = ""
    state["amount"] = 0.0
    state["entry_price"] = 0.0
    state["holding_price"] = 0.0
    state["entry_time"] = ""
    
    return state