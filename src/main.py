"""
=================================================================
MAIN.PY - Quantum Momentum Bot v2.0 (RESTRUCTURED)
=================================================================
Bot de Trading Asistido refactorizado con arquitectura modular.
=================================================================
"""
import sys
import os

# Añadir src al path para imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import json
import time
import asyncio
import argparse
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

# ============================================================================
# IMPORTS MODULARES
# ============================================================================

from src.core.config import config, load_state, save_state
from src.core.logger import bot_logger, log_info, log_debug, log_warning, log_error, log_trade, log_section
from src.market.api_client import api_client, get_all_tickers
from src.trading.analyzer import analyzer
from src.trading import scoring, filters, risk_manager, metrics
from src.notifications.manager import (
    build_swap_notification, send_whatsapp_message, 
    send_email, get_whatsapp_driver, check_whatsapp_session
)


# ============================================================================
# CONFIGURATION
# ============================================================================

STATE_FILE = "state.json"
CHECK_INTERVAL = config.get('bot.check_interval', 300)
DEBUG_INTERVAL = config.get('bot.debug_interval', 15)


# ============================================================================
# STATE MANAGEMENT
# ============================================================================

def ask_new_value(key: str, current_value: Any, prompt_text: str) -> str:
    """Pide nuevo valor al usuario"""
    if current_value:
        user_input = input(f"{prompt_text} [{current_value}]: ").strip()
        if user_input == "":
            return str(current_value)
        return user_input
    else:
        return input(f"{prompt_text}: ").strip()


def setup_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Configura el estado inicial"""
    print("\n=== CONFIGURACIÓN INICIAL ===")
    
    holding = ask_new_value("holding", state.get("holding", ""), "Cripto actual (ej. ADA)")
    amount = ask_new_value("amount", str(state.get("amount", 0)), "Cantidad de tokens")
    email = ask_new_value("email", state.get("email", ""), "Correo Gmail")
    email_password = ask_new_value("email_password", state.get("email_password", ""), "Password Gmail (App Password)")
    phone = ask_new_value("phone", state.get("phone", ""), "WhatsApp (ej. +5352593370)")
    
    state["holding"] = holding.upper()
    state["amount"] = float(amount) if amount else 0
    state["email"] = email
    state["email_password"] = email_password
    state["phone"] = phone
    
    save_state(state)
    print("Estado guardado en state.json\n")
    return state


def show_state(state: Dict[str, Any]) -> None:
    """Muestra estado actual"""
    print("\n=== ESTADO ACTUAL ===")
    print(f"Cripto: {state.get('holding', 'N/A')}")
    print(f"Cantidad: {state.get('amount', 0)}")
    print(f"Email: {state.get('email', 'N/A')}")
    print(f"Phone: {state.get('phone', 'N/A')}")
    
    # Métricas
    summary = metrics.metrics_manager.get_metrics_summary()
    if summary:
        print(f"Ciclos: {summary.get('cycle_count', 0)}")
        print(f"Rotaciones: {summary.get('successful_rotations', 0)}/{summary.get('total_rotations', 0)}")
        print(f"PnL Promedio: {summary.get('pnl_promedio', 0):+.2f}%")
        print(f"Max Drawdown: {summary.get('max_drawdown', 0):.2f}%")
    
    print("========================\n")


# ============================================================================
# WHATSAPP CHECK
# ============================================================================

def check_and_init_whatsapp() -> bool:
    """Verifica sesión antes de enviar mensaje"""
    try:
        driver = get_whatsapp_driver(headless=True)
        result = check_whatsapp_session(headless=True)
        if driver:
            driver.quit()
        return result
    except:
        return False


# ============================================================================
# NOTIFICATIONS
# ============================================================================

async def notify_opportunity(
    state: Dict[str, Any],
    current: Optional[scoring.TickerData],
    candidate: Optional[scoring.TickerData],
    action: str
) -> None:
    """Envía notificaciones"""
    phone = state.get("phone", "")
    email_cfg = (state.get("email", ""), state.get("email_password", ""))
    
    if not candidate and action != "stop_loss" and action != "take_profit":
        return
    
    ticker_data = candidate if candidate else current
    
    if not ticker_data:
        return
    
    # Build message
    symbol_from = state.get("holding", "")
    symbol_to = candidate.symbol if candidate else ""
    
    opp = {
        "from": symbol_from,
        "to": symbol_to,
        "candidate_change_24h": ticker_data.change_24h if ticker_data else 0,
        "candidate_vol": ticker_data.value if ticker_data else 0,
        "candidate_price": ticker_data.last if ticker_data else 0
    }
    
    wa_msg, email_subject, email_body = build_swap_notification(opp)
    
    # Send WhatsApp
    if phone:
        try:
            driver = get_whatsapp_driver(headless=True)
            if send_whatsapp_message(driver, phone, wa_msg):
                log_info("WhatsApp enviado")
        except Exception as e:
            log_error(f"Error WhatsApp: {e}")
    
    # Send Email
    if email_cfg[0] and email_cfg[1]:
        try:
            if send_email(email_cfg[0], email_cfg[1], email_cfg[0], email_subject, email_body):
                log_info("Email enviado")
        except Exception as e:
            log_error(f"Error Email: {e}")


def confirm_swap(state: Dict[str, Any]) -> bool:
    """Confirma si se ejecutó el swap"""
    if not state.get("holding"):
        return True
    
    print(f"\n¿Hiciste el swap {state.get('holding')} -> ? (si/no): ", end="")
    resp = input().strip().lower()
    
    if resp == "si":
        print("Ingresa la nueva cripto (ej. SOL): ", end="")
        new_holding = input().strip().upper()
        
        print("Ingresa la cantidad recibida: ", end="")
        try:
            new_amount = float(input().strip())
        except:
            new_amount = state.get("amount", 0)
        
        state["holding"] = new_holding
        state["amount"] = new_amount
        state["entry_time"] = datetime.now().isoformat()
        save_state(state)
        
        print(f"Estado actualizado: {new_holding}, cantidad: {new_amount}")
        return True
    
    return False


# ============================================================================
# ANALYSIS LOOP
# ============================================================================

async def analyze_market(
    tickers: Dict[str, Dict[str, Any]],
    state: Dict[str, Any]
) -> Tuple[Optional[scoring.TickerData], Optional[scoring.TickerData], str]:
    """Ejecuta análisis de mercado"""
    return await analyzer.analyze(tickers, state)


async def run_once() -> None:
    """Ejecuta un solo ciclo"""
    log_section("EJECUTAR UN CICLO")
    state = load_state()
    show_state(state)
    
    # Obtener datos
    log_debug("[1] Consultando API de CoinEx...")
    tickers = get_all_tickers()
    
    if not tickers:
        log_error("[!] No se pudieron obtener datos del mercado")
        return
    
    log_info(f"[OK] Mercados obtenidos: {len(tickers)}")
    
    # Analizar
    log_debug("[2] Analizando mercado...")
    current, candidate, reason = await analyze_market(tickers, state)
    
    holding = state.get("holding", "")
    
    if current:
        log_info(f"Holding: {current.symbol} | Precio: {current.last} | "
                f"24h: {current.change_24h:+.2f}%")
    
    if candidate:
        log_info(f"*** OPORTUNIDAD: {holding} -> {candidate.symbol}")
        log_info(f"    Score: {candidate.score:.3f}")
        log_info(f"    Cambio 24h: {candidate.change_24h:+.2f}%")
        
        await notify_opportunity(state, current, candidate, "rotate")
        
        log_info("[5] Esperando confirmación...")
        confirm_swap(state)
    else:
        log_info(f"[!] {reason}")
    
    # Cerrar sesión
    try:
        await api_client.close()
    except:
        pass


# ============================================================================
# MAIN LOOP
# ============================================================================

async def main_loop() -> None:
    """Loop principal del bot"""
    log_section("QUANTUM MOMENTUM BOT v2.0")
    log_info("Iniciando...")
    
    # Cargar estado
    state = load_state()
    
    if not state.get("holding"):
        state = setup_state(state)
    else:
        show_state(state)
        print("Desea cambiar configuración? (s/n): ", end="")
        if input().strip().lower() == "s":
            state = setup_state(state)
        else:
            save_state(state)
    
    # Omitir verificación automática de WhatsApp al inicio
    log_info("WhatsApp: usa --initwhatsapp para configurar")
    
    # Ciclo principal
    cycle_count = 0
    last_save = datetime.now()
    
    while True:
        cycle_count += 1
        log_section(f"CICLO {cycle_count}")
        
        # 1. Obtener datos del mercado
        log_debug("[1] Consultando API de CoinEx...")
        tickers = get_all_tickers()
        
        if not tickers:
            log_error("[!] No se pudieron obtener datos del mercado")
            log_info(f"    Esperando {CHECK_INTERVAL} segundos...")
            time.sleep(CHECK_INTERVAL)
            continue
        
        log_info(f"[OK] Mercados obtenidos: {len(tickers)}")
        
        # 2. Análisis
        log_debug("[2] Analizando mercado...")
        current, candidate, reason = await analyze_market(tickers, state)
        
        holding = state.get("holding", "N/A")
        
        if current:
            log_info(f"Holding: {current.symbol} | Precio: {current.last} | "
                    f"24h: {current.change_24h:+.2f}%")
        
        # 3. Verificar cooldown
        if reason == "cooldown":
            log_info("[!] Holding en cooldown, manteniendo posición")
        elif reason.startswith("STOP_LOSS") or reason.startswith("TAKE_PROFIT") or reason == "TRAILING_STOP":
            # Notificar
            log_info(f"[!] {reason}")
            await notify_opportunity(state, current, None, reason.split(":")[0].lower())
            
            metrics.record_rotation(reason.startswith("TAKE_PROFIT"))
            
            # Confirmar
            if confirm_swap(state):
                risk_manager.risk_manager.add_cooldown(holding)
        elif candidate:
            log_info(f"*** OPORTUNIDAD: {holding} -> {candidate.symbol}")
            log_info(f"    Score: {candidate.score:.3f}")
            log_info(f"    Cambio 24h: {candidate.change_24h:+.2f}%")
            log_info(f"    Volumen: ${candidate.value:,.0f}")
            
            # Notificar
            await notify_opportunity(state, current, candidate, "rotate")
            
            # Confirmar
            if confirm_swap(state):
                risk_manager.risk_manager.add_cooldown(holding)
                metrics.record_rotation(True)
                
                # Actualizar entry
                state["entry_time"] = datetime.now().isoformat()
                metrics.metrics_manager.set_entry_time(state["entry_time"])
        else:
            log_info(f"[!] {reason}")
            if reason == "no_valid_candidate":
                metrics.record_false_signal()
        
        # 4. Guardar estado
        save_state(state)
        risk_manager.risk_manager.save_cooldowns(state)
        
        # 5. Guardar métricas periódicamente
        if (datetime.now() - last_save).total_seconds() > 300:
            metrics.metrics_manager.save_metrics()
            last_save = datetime.now()
        
        # 6. Esperar
        log_info(f"Esperando {CHECK_INTERVAL} segundos...")
        time.sleep(CHECK_INTERVAL)


# ============================================================================
# CLI
# ============================================================================

def init_whatsapp():
    """Inicializa WhatsApp"""
    from src.notifications.manager import init_whatsapp_session
    init_whatsapp_session()


def main() -> None:
    """CLI principal para controlar el bot."""
    global STATE_FILE
    parser = argparse.ArgumentParser(description="Quantum Momentum Bot CLI")
    parser.add_argument(
        "--mode",
        choices=["run", "once", "init-whatsapp", "show-state", "setup"],
        default="run",
        help="Modo de operación",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Ejecutar un solo ciclo (compatibilidad legacy)",
    )
    parser.add_argument(
        "--state",
        default=STATE_FILE,
        help="Ruta al archivo de estado (default: state.json)",
    )

    args = parser.parse_args()
    # Compat: permitir --once sin --mode
    if getattr(args, 'once', False):
        args.mode = 'once'

    if args.mode == "init-whatsapp":
        init_whatsapp()
    elif args.mode == "show-state":
        s = load_state()
        show_state(s)
    elif args.mode == "setup":
        s = load_state()
        setup_state(s)
    elif args.mode == "once":
        asyncio.run(run_once())
    else:
        # run (bucle continuo)
        try:
            asyncio.run(main_loop())
        except KeyboardInterrupt:
            log_info("Interrumpido por el usuario.")
            print()


if __name__ == "__main__":
    main()
