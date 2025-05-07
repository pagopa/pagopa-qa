# File: app.py (Versione con SSE)

import os
import chromadb
# Importa Response, stream_with_context e json per SSE
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
import json # Importa json
from sentence_transformers import SentenceTransformer
from groq import Groq
from dotenv import load_dotenv
import traceback
import time # Importa time per eventuali pause nel flusso SSE

# --- Caricamento Configurazione ---
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("Chiave API Groq non trovata.")

# Modello di embedding
EMBEDDING_MODEL_NAME = 'all-MiniLM-L6-v2'
# Percorso ChromaDB
CHROMA_PATH = "chroma_db"
# Nome collezione ChromaDB
COLLECTION_NAME = "pagopa_sanp_docs"
# Numero di risultati da recuperare da ChromaDB
N_RESULTS = 5
# Modelli Groq Permessi e Default
ALLOWED_GROQ_MODELS = {
    "llama3-8b-8192", "llama3-70b-8192", "mixtral-8x7b-32768",
    "gemma-7b-it", "llama-3.1-8b-instant", "llama-3.3-70b-versatile",
    "gemma2-9b-it", "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct", "qwen-qwq-32b",
    "mistral-saba-24b", "qwen-2.5-coder-32b", "qwen-2.5-32b",
    "deepseek-r1-distill-qwen-32b", "deepseek-r1-distill-llama-70b",
    "llama-3.3-70b-specdec", "llama-3.2-1b-preview", "llama-3.2-3b-preview"
}
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"

# --- Inizializzazione Componenti ---
print("Caricamento/Configurazione componenti...")
embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, device='cpu')
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = None
try:
    collection = chroma_client.get_collection(name=COLLECTION_NAME)
    print(f"Connesso a ChromaDB, collezione '{COLLECTION_NAME}'.")
except Exception as e:
    print(f"ATTENZIONE: Impossibile accedere alla collezione '{COLLECTION_NAME}'. Errore: {e}")
groq_client = Groq(api_key=GROQ_API_KEY)
print("Client pronti.")

app = Flask(__name__)

# --- Funzione per costruire messaggi Groq (invariata) ---
def build_groq_messages(query, context_chunks):
    context = "\n---\n".join(context_chunks)
    system_prompt = """Sei un assistente AI informativo specializzato sul contenuto del sito PagoPA.
Rispondi alla domanda dell'utente basandoti ESCLUSIVAMENTE sul contesto fornito.
Sii conciso e preciso. Se il contesto non contiene informazioni sufficienti per rispondere,
indicalo chiaramente dicendo: 'Le informazioni fornite nel contesto non sono sufficienti per rispondere a questa domanda.'.
Non aggiungere informazioni non presenti nel contesto. Rispondi in italiano."""
    user_content = f"""CONTESTO FORNITO:
---
{context}
---
DOMANDA UTENTE:
{query}"""
    messages = [ {"role": "system", "content": system_prompt}, {"role": "user", "content": user_content} ]
    return messages

# --- Route /ask che ora genera eventi SSE ---
@app.route('/ask', methods=['POST'])
def ask_question_sse():
    # Ottieni dati dalla richiesta POST JSON
    data = request.get_json()
    if not data: return Response("Richiesta non JSON", status=400)

    query = data.get('query')
    requested_model = data.get('model', DEFAULT_GROQ_MODEL)

    if not query: return Response("Query mancante", status=400)
    if not collection:
        def error_stream_db():
            yield f"data: {json.dumps({'type': 'error', 'message': 'Database non disponibile.'})}\n\n"
        return Response(stream_with_context(error_stream_db()), mimetype='text/event-stream')

    # Validazione modello
    selected_model = DEFAULT_GROQ_MODEL
    if requested_model in ALLOWED_GROQ_MODELS:
        selected_model = requested_model
    else:
        print(f"Warning: Modello '{requested_model}' non valido, uso default.")
        # Potremmo inviare un log SSE anche qui

    # --- Funzione Generatore per lo stream SSE ---
    def generate_events():
        log_prefix = "  " # Prefisso per log nel terminale server
        try:
            # Helper per inviare eventi SSE formattati E loggare sul server
            def send_event(type, data):
                log_message = f"{type.upper()}: {data}" if type != "result" else f"RESULT: (dati inviati)"
                print(log_prefix + log_message) # Log sul server
                payload = json.dumps({"type": type, "data": data})
                yield f"data: {payload}\n\n" # Invia al client
                # time.sleep(0.01) # Pausa minuscola se si vogliono rallentare gli eventi

            yield from send_event("log", f"Richiesta ricevuta. Elaborazione con modello: '{selected_model}'")

            # 1. Embedding Query
            yield from send_event("log", "Fase 1: Generazione embedding query...")
            query_embedding = embedding_model.encode(query).tolist()
            yield from send_event("log", "Embedding query generato.")

            # 2. Query ChromaDB
            yield from send_event("log", f"Fase 2: Interrogazione ChromaDB (top {N_RESULTS})...")
            results = collection.query(query_embeddings=[query_embedding], n_results=N_RESULTS, include=['documents', 'metadatas'])
            context_chunks = results.get('documents', [[]])[0]
            retrieved_metadatas = results.get('metadatas', [[]])[0]

            source_urls = set()
            if retrieved_metadatas:
                for meta in retrieved_metadatas:
                    if meta and 'source' in meta: source_urls.add(meta['source'])
            unique_sources = sorted(list(source_urls))

            if not context_chunks:
                 yield from send_event("log", "Nessun chunk rilevante trovato.")
                 context_chunks = ["Nessun contesto specifico trovato."]
            else:
                 yield from send_event("log", f"Recuperati {len(context_chunks)} chunk da {len(unique_sources)} fonti.")

            # 3. Costruzione Prompt
            yield from send_event("log", "Fase 3: Costruzione prompt per LLM...")
            messages = build_groq_messages(query, context_chunks)
            yield from send_event("log", f"Prompt costruito con {len(context_chunks)} chunk.")

            # 4. Chiamata API Groq
            yield from send_event("log", f"Fase 4: Chiamata API Groq ({selected_model})...")
            answer = ""
            try:
                chat_completion = groq_client.chat.completions.create(
                    messages=messages, model=selected_model, temperature=0.7, max_tokens=1500
                )
                answer = chat_completion.choices[0].message.content
                yield from send_event("log", "Risposta ricevuta da Groq.")
            except Exception as api_err:
                error_message = f"Errore API Groq: {api_err}"
                yield from send_event("log", f"! {error_message}")
                traceback.print_exc()
                yield from send_event("error", error_message) # Invia errore specifico al client
                return # Termina

            # 5. Invio Risultato Finale
            yield from send_event("log", "Fase 5: Invio risultato finale al frontend.")
            final_data = {"answer": answer, "sources": unique_sources}
            yield from send_event("result", final_data) # Evento finale con i dati utili

        except Exception as e:
            error_message = f"Errore interno durante elaborazione: {e}"
            print(f"! Errore grave: {e}")
            traceback.print_exc()
            # Invia un evento di errore generico al client
            try:
                yield f"data: {json.dumps({'type': 'error', 'message': error_message})}\n\n"
            except Exception as yield_err:
                 print(f"Errore invio messaggio di errore SSE: {yield_err}")

    # Ritorna la Response Flask con il generatore e il mimetype corretto per SSE
    return Response(stream_with_context(generate_events()), mimetype='text/event-stream')


# --- Route per servire il Frontend (invariata) ---
@app.route('/')
def index():
    return render_template('index.html')

# --- Avvio Server (invariato)---
if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)