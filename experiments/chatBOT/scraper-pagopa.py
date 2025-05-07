# --- Imports ---
import time
import sys
import collections
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# Import Selenium specifici
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC # Import necessario per le condizioni di attesa
from selenium.common.exceptions import WebDriverException, TimeoutException

# Import webdriver-manager per gestione automatica driver
from webdriver_manager.chrome import ChromeDriverManager

# --- Configurazione ---
START_URL = "https://developer.pagopa.it/pago-pa/guides/sanp"
BASE_PREFIX = "https://developer.pagopa.it/pago-pa/guides/sanp"
# Tempo massimo di attesa per il caricamento di elementi dinamici (secondi)
WAIT_TIMEOUT = 15
# Aspetta il primo link (a) con le classi MUI tipiche del menu laterale
WAIT_SELECTOR_CSS = "a.MuiTypography-root.MuiTypography-sidenav"

# --- Strutture Dati ---
urls_to_visit = collections.deque([START_URL])
visited_urls = set()
discovered_urls = set([START_URL])

# --- Setup Selenium ---
print("Configurazione WebDriver (potrebbe richiedere il download di ChromeDriver)...")
chrome_options = Options()
chrome_options.add_argument("--headless")  # Esegui senza aprire finestra browser
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--log-level=3") # Riduci output console di Selenium
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

driver = None  # Inizializza variabile driver

try:
    # Usa webdriver-manager per installare/trovare automaticamente ChromeDriver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    print("WebDriver configurato.")

    # --- Ciclo Principale di Crawling ---
    print(f"--- Inizio Scraper ---")
    print(f"URL di partenza: {START_URL}")
    print(f"Limita scraping a URL che iniziano con: {BASE_PREFIX}")

    while urls_to_visit:
        current_url = urls_to_visit.popleft()

        if current_url in visited_urls:
            continue

        print(f"\nAnalizzo: {current_url}")
        # Marcalo visitato *prima* di iniziare a processarlo per evitare loop se fallisce
        visited_urls.add(current_url)

        try:
            # Naviga alla pagina con Selenium
            driver.get(current_url)
            print(f"  Pagina caricata. In attesa dell'elemento '{WAIT_SELECTOR_CSS}' (max {WAIT_TIMEOUT}s)...")

            # --- ATTESA MODIFICATA ---
            # Attendi esplicitamente che l'elemento sia PRESENTE nel DOM
            try:
                wait = WebDriverWait(driver, WAIT_TIMEOUT)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, WAIT_SELECTOR_CSS)))
                print(f"  Elemento '{WAIT_SELECTOR_CSS}' PRESENTE nel DOM.")
                # Aggiungiamo una piccola pausa extra per sicurezza dopo che l'elemento è presente
                time.sleep(1)
            except TimeoutException:
                print(f"  ! TIMEOUT: Elemento '{WAIT_SELECTOR_CSS}' NON TROVATO nel DOM entro {WAIT_TIMEOUT}s.")
                # DEBUG: Salva sorgente e screenshot in caso di timeout
                try:
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    filename_base = f"debug_timeout_{timestamp}"
                    with open(f"{filename_base}.html", "w", encoding="utf-8") as f:
                        f.write(driver.page_source)
                    driver.save_screenshot(f"{filename_base}.png")
                    print(f"  Debug HTML source e screenshot salvati come '{filename_base}.*'")
                except Exception as save_err:
                    print(f"  Errore nel salvataggio del debug: {save_err}")
                continue # Salta l'analisi di questa pagina se l'elemento non è stato trovato

            # --- FINE ATTESA MODIFICATA ---

            print("  Estraggo HTML renderizzato...")
            html_content = driver.page_source

            # Analizza l'HTML renderizzato con BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')

            # DEBUG: Controlla di nuovo il link di test (ora dovrebbe trovarlo)
            test_link_href = "/pago-pa/guides/sanp/flusso-sanp" # Usa un link che ora sappiamo esistere (o quello che vedi tu)
            test_link = soup.find('a', href=test_link_href)
            print(f"  DEBUG (post-Selenium): Trovato link di test '{test_link_href}'? {'Sì' if test_link else 'No'}")

            print(f"  --- Inizio analisi link (post-Selenium) per {current_url} ---")
            link_found_in_scope_count = 0

            for link_tag in soup.find_all('a', href=True):
                href = link_tag['href'].strip()
                if not href or href.startswith('#') or href.startswith('mailto:') or href.startswith('javascript:'):
                    continue

                absolute_url = urljoin(current_url, href)
                parsed_url = urlparse(absolute_url)
                clean_url = parsed_url._replace(fragment="").geturl()

                is_in_scope = clean_url.startswith(BASE_PREFIX)
                if is_in_scope:
                     # Controlla di nuovo 'visited' perché potremmo averlo aggiunto nel frattempo
                    is_already_known = clean_url in discovered_urls or clean_url in visited_urls
                    if not is_already_known:
                        print(f"      >>> OK! Aggiungo alla coda: {clean_url}")
                        discovered_urls.add(clean_url)
                        urls_to_visit.append(clean_url)
                        link_found_in_scope_count += 1

            print(f"  --- Fine analisi link per {current_url} ---")
            print(f"  Trovati {link_found_in_scope_count} nuovi link validi in questo ciclo.")

        except WebDriverException as e:
            print(f"  ! Errore WebDriver per {current_url}: {e}")
        except Exception as e:
            print(f"  ! Errore generico processando {current_url}: {e}")

    # --- Fine Ciclo ---

except Exception as e:
    print(f"Errore critico durante setup o scraping: {e}")
finally:
    # --- Pulizia ---
    if driver:
        print("\nChiusura WebDriver...")
        driver.quit()

# --- Formattazione Output ---
print(f"\n--- Scraper Terminato ---")
print(f"Trovati {len(discovered_urls)} URL unici nello scope (esclusa sezione Lavora con Noi).") # Aggiornata descrizione
sorted_urls = sorted(list(discovered_urls))
output_string = "URLS_TO_SCRAPE = [\n"
for url in sorted_urls:
    output_string += f'    "{url}",\n'
if sorted_urls:
    output_string = output_string.rstrip(',\n') + "\n"
output_string += "]"
# print("\n--- Output Formattato (Pronto per il file) ---")
# print(output_string)

# --- SALVATAGGIO SU FILE ---
output_filename = "scraped_pagopa_it_urls.py"
try:
    with open(output_filename, "w", encoding='utf-8') as f:
        f.write(output_string)
    print(f"\nOutput salvato con successo nel file: {output_filename}")
except IOError as e:
    print(f"\n! Errore nel salvataggio del file '{output_filename}': {e}")