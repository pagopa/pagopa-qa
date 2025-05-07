import os
import time
import requests
from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
import chromadb
import scraped_pagopa_it_urls # Importa le URL generate

# --- Configurazione ---
URLS_FILE = scraped_pagopa_it_urls.URLS_TO_SCRAPE
# Modello di embedding (assicurati sia lo stesso usato nell'app Flask)
EMBEDDING_MODEL_NAME = 'all-MiniLM-L6-v2'
# Percorso per il database ChromaDB persistente
CHROMA_PATH = "chroma_db"
# Nome della collezione in ChromaDB
COLLECTION_NAME = "pagopa_sanp_docs"

# Configurazione Text Splitter (puoi aggiustare chunk_size e overlap)
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,  # Dimensione dei chunk (caratteri)
    chunk_overlap=200, # Sovrapposizione tra chunk
    length_function=len,
    add_start_index=True, # Aggiunge l'indice di inizio del chunk nel metadata
)

# Headers per requests
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- Funzione per estrarre testo (semplificata) ---
def extract_text_from_html(html_content):
    """Estrae testo significativo dall'HTML (implementazione base)."""
    soup = BeautifulSoup(html_content, 'html.parser')
    # Prova a estrarre dal tag <main>, o dal body se non c'è <main>
    main_content = soup.find('main')
    if not main_content:
        main_content = soup.body # Fallback al body
    if not main_content:
        return None

    # Rimuovi elementi non testuali comuni (script, style, nav, footer, header)
    for element in main_content(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form']):
        element.decompose()

    # Ottieni il testo, separando i paragrafi con newline e pulendo spazi extra
    text = main_content.get_text(separator='\n', strip=True)
    return text

# --- Inizializzazione ChromaDB e Modello Embedding ---
print(f"Inizializzazione modello embedding: {EMBEDDING_MODEL_NAME}...")
# Usa 'cpu' esplicitamente se non hai GPU configurata, altrimenti rileva automaticamente
model = SentenceTransformer(EMBEDDING_MODEL_NAME, device='cpu')
print("Modello caricato.")

print(f"Inizializzazione ChromaDB in '{CHROMA_PATH}'...")
# Crea un client persistente (salva su disco)
client = chromadb.PersistentClient(path=CHROMA_PATH)

print(f"Creazione/accesso collezione: {COLLECTION_NAME}")
# Crea o ottiene la collezione. Nota: L'embedding function qui è solo metadata,
# calcoliamo gli embeddings esternamente per controllo.
collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"} # Usa cosine similarity
)
print("ChromaDB pronto.")

# --- Ciclo di Processamento URL ---
total_urls = len(URLS_FILE)
print(f"Inizio processamento di {total_urls} URL...")

processed_urls = 0
failed_urls = 0
total_chunks_added = 0

for i, url in enumerate(URLS_FILE):
    print(f"[{i+1}/{total_urls}] Processo URL: {url}")
    try:
        time.sleep(0.1) # Pausa
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # --- MODIFICA QUI: Forziamo l'encoding a UTF-8 ---
        response.encoding = 'utf-8' # Dice a requests di interpretare i byte come UTF-8
        html_content = response.text # Ora .text userà UTF-8
        # ------------------------------------------------

        content_type = response.headers.get('Content-Type', '')
        if 'text/html' not in content_type:
            print("  > Ignorato (non HTML).")
            continue

        print("  Estraggo testo...")
        # Passiamo l'html_content (ora sicuramente UTF-8) a BeautifulSoup
        text_content = extract_text_from_html(html_content)

        if not text_content or len(text_content.strip()) < 50: # Ignora pagine con poco testo
             print("  > Ignorato (testo troppo corto o non trovato).")
             continue

        print("  Divido in chunk...")
        chunks = text_splitter.split_text(text_content)
        print(f"    > Creati {len(chunks)} chunk.")

        if not chunks:
            continue

        print("  Genero embeddings...")
        # Nota: model.encode può processare una lista di testi
        embeddings = model.encode(chunks, show_progress_bar=False).tolist() # Converti in lista per Chroma

        # Prepara dati per ChromaDB
        ids = [f"{url}_{j}" for j in range(len(chunks))] # ID univoci per chunk
        metadatas = [{"source": url, "start_index": chunk.metadata['start_index']} for chunk, j in zip(text_splitter.create_documents(chunks), range(len(chunks)))] # Usa create_documents per accedere ai metadata
        documents = [chunk.page_content for chunk in text_splitter.create_documents(chunks)] # Estrai solo il testo per Chroma

        print(f"  Aggiungo {len(ids)} chunk a ChromaDB...")
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        total_chunks_added += len(ids)
        processed_urls += 1

    except requests.exceptions.RequestException as e:
        print(f"  ! Errore di rete: {e}")
        failed_urls += 1
    except Exception as e:
        print(f"  ! Errore generico: {e}")
        failed_urls += 1

print("\n--- Processamento Terminato ---")
print(f"URL processati con successo: {processed_urls}")
print(f"URL falliti: {failed_urls}")
print(f"Chunk totali aggiunti a ChromaDB: {total_chunks_added}")
print(f"Database ChromaDB salvato in: {CHROMA_PATH}")