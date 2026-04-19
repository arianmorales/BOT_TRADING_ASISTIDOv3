import smtplib
import email.message
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
import os
import urllib.parse

WHATSAPP_SESSION_DIR = "whatsapp_session"

def get_whatsapp_driver(headless=True):
    os.makedirs(WHATSAPP_SESSION_DIR, exist_ok=True)
    
    opts = Options()
    opts.add_argument(f"--user-data-dir={os.path.abspath(WHATSAPP_SESSION_DIR)}")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=800,600")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    
    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-position=-10000,0")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(60)
    return driver

def check_whatsapp_session(headless=False):
    driver = get_whatsapp_driver(headless=headless)
    try:
        driver.get("https://web.whatsapp.com/")
        time.sleep(5)
        
        if driver.find_elements(By.ID, "side"):
            print("[OK] Sesion activa")
            return True
        
        if driver.find_elements(By.CSS_SELECTOR, "div[data-ref]"):
            print("[INFO] Necesita escanear QR")
            return False
            
        print("[INFO] Estado desconocido")
        return False
    finally:
        driver.quit()

def init_whatsapp_session():
    print("[INFO] Iniciando sesion WhatsApp...")
    print("  Se abrira el navegador")
    print("  Escanea el QR con WhatsApp\n")
    
    driver = get_whatsapp_driver(headless=False)
    driver.get("https://web.whatsapp.com/")
    
    print("[*] Esperando escaneo (max 2 min)...")
    
    try:
        WebDriverWait(driver, 120).until(
            EC.presence_of_element_located((By.ID, "side"))
        )
        print("[OK] Sesion iniciada y guardada!")
    except:
        print("[OK] Sesion iniciada!")
    
    driver.quit()

def send_whatsapp_message(driver, phone_number, message):
    phone = phone_number.replace("+", "").replace(" ", "").replace("-", "")
    
    try:
        driver.get("https://web.whatsapp.com/")
        time.sleep(5)
        
        if not driver.find_elements(By.ID, "side"):
            print("[ERROR] Sesion no iniciada. Ejecuta: python main.py --initwhatsapp")
            return False
        
        url = f"https://web.whatsapp.com/send?phone={phone}"
        driver.get(url)
        time.sleep(4)
        
        xpath = '//div[@contenteditable="true" and @data-tab="10"]'
        box = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        
        box.click()
        time.sleep(0.3)
        
        for char in message:
            box.send_keys(char)
            time.sleep(0.03)
        
        time.sleep(0.5)
        
        try:
            btn = driver.find_element(By.XPATH, '//button[@aria-label="Enviar" and @data-tab="11"]')
        except:
            try:
                btn = driver.find_element(By.XPATH, '//button[@aria-label="Send"]')
            except:
                btn = driver.find_element(By.XPATH, '//button[@data-tab="11"]')
        
        btn.click()
        time.sleep(2)
        
        print(f"[OK] WhatsApp enviado a {phone_number}")
        return True
        
    except Exception as e:
        print(f"[ERROR] WhatsApp: {e}")
        return False

def send_email(sender_email, sender_password, to_email, subject, body):
    try:
        msg = email.message.EmailMessage()
        msg["From"] = sender_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body, subtype="plain", charset="utf-8")

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        
        print(f"Email enviado a {to_email}")
        return True
    except Exception as e:
        print(f"Error enviando email: {e}")
        return False

def get_coinex_link(symbol):
    base = symbol.replace("USDT", "-USDT").lower()
    return f"https://www.coinex.com/es/exchange/{base}"

def notify_swapRecommendation(opp, phone, email_cfg):
    symbol_from = opp["from"]
    symbol_to = opp["to"]
    change_24h = opp.get("candidate_change_24h", 0)
    vol = opp.get("candidate_vol", 0)
    price = opp.get("candidate_price", 0)
    
    link_from = get_coinex_link(symbol_from)
    link_to = get_coinex_link(symbol_to)
    
    wa_msg = f"""
Swap recomendado: {symbol_from} → {symbol_to}
Precio: {price}
Cambio 24h: {change_24h:+.2f}%
Volumen: ${vol:,.0f}
{link_from} → {link_to}
¿Lo hiciste?
""".strip()
    
    email_subject = f"Swap Recomendado: {symbol_from} → {symbol_to}"
    email_body = f"""
Swap recomendado por el Bot de Trading

De: {symbol_from} ({link_from})
A: {symbol_to} ({link_to})

Precio actual: {price}
Cambio 24h: {change_24h:+.2f}%
Volumen 24h: ${vol:,.0f}

Por favor responde si ejecutaste el swap.
""".strip()
    
    return wa_msg, email_subject, email_body

def close_whatsapp_driver(driver):
    try:
        if driver:
            driver.quit()
    except:
        pass

def test_whatsapp(phone_number, message):
    try:
        driver = get_whatsapp_driver(headless=True)
        result = send_whatsapp_message(driver, phone_number, message)
        driver.quit()
        return result
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_email(sender_email, sender_password, to_email):
    try:
        msg = email.message.EmailMessage()
        msg["From"] = sender_email
        msg["To"] = to_email
        msg["Subject"] = "Test - Bot Trading Asistido"
        msg.set_content("Este es un mensaje de prueba del Bot de Trading Asistido.\n\nSi recibes este correo, la configuracion esta correcta.", subtype="plain", charset="utf-8")

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        
        print(f"Email de prueba enviado a {to_email}")
        return True
    except Exception as e:
        print(f"Error enviando email: {e}")
        return False