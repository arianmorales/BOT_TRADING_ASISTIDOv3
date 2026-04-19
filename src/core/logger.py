"""
=================================================================
LOGGER.PY - Professional Logging System
=================================================================
Sistema de logging estructurado separado por niveles
Compatible con el formato de consola existente
=================================================================
"""
import os
import logging
import json
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any


class BotLogger:
    """
    Sistema de logging profesional con múltiples archivos:
    - bot.log: Logs principales
    - bot_debug.log: Detalle paso a paso
    - bot_trades.log: Órdenes y PnL
    - bot_errors.log: Excepciones y errores
    """
    
    _instance: Optional['BotLogger'] = None
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not BotLogger._initialized:
            self._setup_loggers()
            BotLogger._initialized = True
    
    def _setup_loggers(self) -> None:
        """
        Configura los loggers separados por función.
        """
        from config_loader import config as cfg
        cfg._config = cfg.load()
        
        log_config = cfg.logging
        log_dir = log_config.get('log_dir', 'logs')
        level = getattr(logging, log_config.get('level', 'INFO'))
        
        # Crear directorio de logs
        os.makedirs(log_dir, exist_ok=True)
        
        # Formateadores
        console_format = logging.Formatter(
            '%(levelname)s: %(message)s'
        )
        
        file_format = logging.Formatter(
            '%(asctime)s | %(name)s | %(levelname)s | %(message)s'
        )
        
        # Configuración de rotación
        max_bytes = log_config.get('rotate_max_bytes', 10 * 1024 * 1024)
        backup_count = log_config.get('rotate_backup_count', 5)
        
        # ========== LOGGER PRINCIPAL ==========
        self.logger = logging.getLogger('Bot')
        self.logger.setLevel(level)
        self.logger.handlers.clear()
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_format)
        self.logger.addHandler(console_handler)
        
        # File handler - main log
        main_log = os.path.join(log_dir, log_config.get('main_log', 'bot.log'))
        main_handler = RotatingFileHandler(
            main_log, maxBytes=max_bytes, backupCount=backup_count
        )
        main_handler.setFormatter(file_format)
        self.logger.addHandler(main_handler)
        
        # ========== LOGGER DEBUG ==========
        self.debug_logger = logging.getLogger('BotDebug')
        self.debug_logger.setLevel(logging.DEBUG)
        self.debug_logger.handlers.clear()
        
        debug_log = os.path.join(log_dir, log_config.get('debug_log', 'bot_debug.log'))
        debug_handler = RotatingFileHandler(
            debug_log, maxBytes=max_bytes, backupCount=backup_count
        )
        debug_handler.setFormatter(file_format)
        self.debug_logger.addHandler(debug_handler)
        
        # ========== LOGGER TRADES ==========
        self.trades_logger = logging.getLogger('BotTrades')
        self.trades_logger.setLevel(logging.INFO)
        self.trades_logger.handlers.clear()
        
        trades_log = os.path.join(log_dir, log_config.get('trades_log', 'bot_trades.log'))
        trades_handler = RotatingFileHandler(
            trades_log, maxBytes=max_bytes, backupCount=backup_count
        )
        trades_handler.setFormatter(file_format)
        self.trades_logger.addHandler(trades_handler)
        
        # ========== LOGGER ERRORS ==========
        self.errors_logger = logging.getLogger('BotErrors')
        self.errors_logger.setLevel(logging.ERROR)
        self.errors_logger.handlers.clear()
        
        errors_log = os.path.join(log_dir, log_config.get('errors_log', 'bot_errors.log'))
        errors_handler = RotatingFileHandler(
            errors_log, maxBytes=max_bytes, backupCount=backup_count
        )
        errors_handler.setFormatter(file_format)
        self.errors_logger.addHandler(errors_handler)
    
    def info(self, msg: str) -> None:
        """Log nivel INFO"""
        self.logger.info(msg)
    
    def debug(self, msg: str) -> None:
        """Log nivel DEBUG"""
        self.debug_logger.debug(msg)
    
    def warning(self, msg: str) -> None:
        """Log nivel WARNING"""
        self.logger.warning(msg)
    
    def error(self, msg: str, exc_info: bool = False) -> None:
        """Log nivel ERROR"""
        self.errors_logger.error(msg, exc_info=exc_info)
        self.logger.error(msg)
    
    def trade(self, msg: str) -> None:
        """Log específico para trades"""
        self.trades_logger.info(msg)
    
    def critical(self, msg: str, exc_info: bool = True) -> None:
        """Log nivel CRITICAL"""
        self.errors_logger.critical(msg, exc_info=exc_info)
        self.logger.critical(msg)
    
    def step(self, step_num: int, total: int, message: str) -> None:
        """Log formato compatibilidad: [PASO X/Y] mensaje"""
        self.debug(f"[PASO {step_num}/{total}] {message}")
        print(f"[PASO {step_num}/{total}] {message}")
    
    def section(self, title: str = "") -> None:
        """Log de sección compatibility"""
        self.logger.info("")
        self.logger.info("=" * 50)
        if title:
            self.logger.info(f"  {title}")
        self.logger.info("=" * 50)
        self.logger.info("")
        
        # También a console para compatibilidad
        print("")
        print("=" * 50)
        if title:
            print(f"  {title}")
        print("=" * 50)
        print("")


# Instancia global
bot_logger = BotLogger()


# Funciones de conveniencia
def log_info(msg: str) -> None:
    bot_logger.info(msg)


def log_debug(msg: str) -> None:
    bot_logger.debug(msg)


def log_warning(msg: str) -> None:
    bot_logger.warning(msg)


def log_error(msg: str, exc_info: bool = False) -> None:
    bot_logger.error(msg, exc_info=exc_info)


def log_trade(msg: str) -> None:
    bot_logger.trade(msg)


def log_step(step_num: int, total: int, message: str) -> None:
    bot_logger.step(step_num, total, message)


def log_section(title: str = "") -> None:
    bot_logger.section(title)