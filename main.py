"""
=================================================================
MAIN.PY - Quantum Momentum Bot v2.0
=================================================================
Bot de Trading Asistido refactorizado con:
- Sistema de Scoring Ponderado
- Gestión de Riesgo Completa
- Filtros Dinámicos
- Métricas Profesionales
- API Async con Cache
=================================================================
"""
import json
import os
import sys
import time
import asyncio
import argparse
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

# ============================================================================
# IMPORTS
# ============================================================================

from config_loader import config, load_state, save_state
from logger import bot_logger, log_info, log_debug, log_warning, log_error, log_trade, log_section
import api_client
import scoring
import analyzer
import filters as dyn_filters
import risk_manager
import metrics
import notifications


# ============================================================================
# CONFIGURATION
# ============================================================================

STATE_FILE = "state.json"
CHECK_INTERVAL = config.get('bot.check_interval', 300)
DEBUG_INTERVAL = config.get('bot.debug_interval', 15)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def write_log(msg: str) -> None:
    """Función de compatibilidad con logs"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line)
    with open("logs.txt", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def log_subsection(title: str = "") -> None:
    """Log de subsección"""
    log_debug("")
    if title:
        log_debug(f"--- {title} ---")


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
    summary = metrics.get_summary()
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
    """Simplified check before sending message"""
    try:
        driver = notifications.get_whatsapp_driver(headless=True)
        result = notifications.check_whatsapp_session(driver)
        if driver:
            driver.quit()
        return result
    except:
        return False


# ============================================================================
# ANALYSIS LOOP
# ============================================================================

async def run_once() -> None:
    """Ejecuta un solo ciclo"""
    log_section("EJECUTAR UN CICLO")
    state = load_state()
    show_state(state)
    
    # WhatsApp se verificará solo cuando necesite enviar notificationsicación
    #check_and_init_whatsapp(skip_on_error=True)
    
    # Obtener datos
    log_debug("[1] Consultando API de CoinEx...")
    tickers = api_client.get_all_tickers()
    
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
        
        await notificationsy_opportunity(state, current, candidate, "rotate")
        
        log_info("[5] Esperando confirmación...")
        confirm_swap(state)
    else:
        log_info(f"[!] {reason}")
    
    # Cerrar sesión
    try:
        api_client.api_client.close()
    except:
        pass


async def analyze_market(
    tickers: Dict[str, Dict[str, Any]],
    state: Dict[str, Any]
) -> Tuple[Optional[scoring.TickerData], Optional[scoring.TickerData], str]:
    """Ejecuta análisis de mercado"""
    return await analyzer.analyzer.analyze(tickers, state)


def main() -> None:
    """CLI principal para controlar el bot.

    Comandos disponibles (modo):
      run            - Ejecuta el bucle continuo (predeterminado)
      once           - Ejecuta un solo ciclo
      init-whatsapp  - Inicializa la sesión de WhatsApp
      show-state     - Muestra el estado actual
      setup          - Configura el estado interactivo
    """
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


async def notificationsy_opportunity(
    state: Dict[str, Any],
    current: Optional[scoring.TickerData],
    candidate: Optional[scoring.TickerData],
    action: str
) -> None:
    """Envia notificationsicaciones"""
    phone = state.get("phone", "")
    email_cfg = (state.get("email", ""), state.get("email_password", ""))
    
    if not candidate and action != "stop_loss" and action != "take_profit":
        return
    
    ticker_data = candidate if candidate else current
    
    if not ticker_data:
        return
    
    # Build message
    symbol_from = state.get("holding", "")
    if candidate:
        symbol_to = candidate.symbol
    else:
        symbol_to = ""
    
    opp = {
        "from": symbol_from,
        "to": symbol_to,
        "candidate_change_24h": ticker_data.change_24h if ticker_data else 0,
        "candidate_vol": ticker_data.value if ticker_data else 0,
        "candidate_price": ticker_data.last if ticker_data else 0
    }
    
    wa_msg, email_subject, email_body = notifications.notificationsy_swapRecommendation(opp, phone, email_cfg)
    
    # Send WhatsApp
    if phone:
        try:
            driver = notifications.get_whatsapp_driver(headless=True)
            if notifications.send_whatsapp_message(driver, phone, wa_msg):
                log_info("WhatsApp enviado")
        except Exception as e:
            log_error(f"Error WhatsApp: {e}")
    
    # Send Email
    if email_cfg[0] and email_cfg[1]:
        try:
            if notifications.send_email(email_cfg[0], email_cfg[1], email_cfg[0], email_subject, email_body):
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
    # (puede inicializar manualmente con --initwhatsapp)
    log_info("WhatsApp: usa --initwhatsapp para configurar")
    
    # Ciclo principal
    cycle_count = 0
    last_save = datetime.now()
    
    while True:
        cycle_count += 1
        log_section(f"CICLO {cycle_count}")
        
        # 1. Obtener datos del mercado
        log_debug("[1] Consultando API de CoinEx...")
        tickers = api_client.get_all_tickers()
        
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
            await notificationsy_opportunity(state, current, None, reason.split(":")[0].lower())
            
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
            await notificationsy_opportunity(state, current, candidate, "rotate")
            
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


async def run_once() -> None:
    """Ejecuta un solo ciclo"""
    log_section("EJECUTAR UN CICLO")
    state = load_state()
    show_state(state)
    
    # WhatsApp se verificará solo cuando necesite enviar notificationsicación
    #check_and_init_whatsapp(skip_on_error=True)
    
    # Obtener datos
    log_debug("[1] Consultando API de CoinEx...")
    tickers = api_client.get_all_tickers()
    
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
        
        await notificationsy_opportunity(state, current, candidate, "rotate")
        
        log_info("[5] Esperando confirmación...")
        confirm_swap(state)
    else:
        log_info(f"[!] {reason}")
    
    # Cerrar sesión
    try:
        api_client.api_client.close()
    except:
        pass


# ============================================================================
# CLI FUNCTIONS
# ============================================================================

def init_whatsapp() -> None:
    """Inicializa sesión WhatsApp"""
    print("\n=== INICIALIZAR SESIÓN WHATSAPP ===")
    print("Se abrirá el navegador con WhatsApp Web")
    print("Escanea el QR con tu teléfono")
    print("El navegador se cerrará automáticamente en 60 segundos...\n")
    
    notifications.init_whatsapp_session()


def check_whatsapp() -> None:
    """Verifica sesión WhatsApp"""
    print("\n=== VERIFICAR SESIÓN WHATSAPP ===")
    is_active = check_and_init_whatsapp()
    
    if is_active:
        print("[OK] Sesión activa")
    else:
        print("[!] Sesión no activa")


def test_whatsapp_message(message: str = "") -> None:
    """Envía mensaje de prueba WhatsApp"""
    print("\n=== ENVIAR MENSAJE WHATSAPP ===")
    
    state = load_state()
    phone = state.get("phone", "")
    
    if not phone:
        print("Error: No hay número de teléfono configurado")
        return
    
    if not message:
        message = "Hola! Test desde Quantum Momentum Bot"
    
    print(f"Enviando a {phone}: {message}")
    
    try:
        driver = notifications.get_whatsapp_driver(headless=True)
        if notifications.send_whatsapp_message(driver, phone, message):
            print(f"[OK] Mensaje enviado")
        else:
            print("[!] Error al enviar")
    except Exception as e:
        print(f"[!] Error: {e}")


def test_email() -> None:
    """Envía email de prueba"""
    print("\n=== ENVIAR EMAIL DE PRUEBA ===")
    
    state = load_state()
    email = state.get("email", "")
    email_password = state.get("email_password", "")
    
    if not email or not email_password:
        print("Error: No hay email/password configurado")
        return
    
    subject = "Test - Quantum Momentum Bot"
    body = f"""Este es un mensaje de prueba del Bot de Trading Asistido v2.0.

Si recibes este correo, la configuración de email está correcta.

Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    if notifications.send_email(email, email_password, email, subject, body):
        print(f"[OK] Email de prueba enviado a {email}")
    else:
        print("[!] Error al enviar email")


def show_metrics() -> None:
    """Muestra métricas"""
    summary = metrics.get_summary()
    
    print("\n=== MÉTRICAS ===")
    print(f"Ciclos: {summary.get('cycle_count', 0)}")
    print(f"Rotaciones totales: {summary.get('total_rotations', 0)}")
    print(f"Rotaciones exitosas: {summary.get('successful_rotations', 0)}")
    print(f"Tasa de éxito: {summary.get('success_rate', 0):.1f}%")
    print(f"PnL promedio: {summary.get('pnl_promedio', 0):+.2f}%")
    print(f"Max drawdown: {summary.get('max_drawdown', 0):.2f}%")
    print(f"Tiempo hold promedio: {summary.get('tiempo_hold_promedio_h', 0):.1f}h")
    print("================\n")


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    # Punto de entrada simplificado: invoca la CLI principal definida en main()
    main()
