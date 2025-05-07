# File: app.py (Versione con Scelta Persona/Stile)

import os
import chromadb
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
import json
from sentence_transformers import SentenceTransformer
from groq import Groq
from dotenv import load_dotenv
import traceback
import time
# import numpy as np

# --- Caricamento Configurazione ---
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY: raise ValueError("Chiave API Groq (GROQ_API_KEY) non trovata.")

EMBEDDING_MODEL_NAME = 'all-MiniLM-L6-v2'
CHROMA_PATH = "chroma_db"
COLLECTION_NAME = "pagopa_sanp_docs" # Assicurati sia il nome corretto della tua collezione
N_RESULTS = 5
ALLOWED_GROQ_MODELS = { "gemma2-9b-it", "llama-3.1-8b-instant", "llama-3.3-70b-versatile", "llama3-70b-8192", "llama3-8b-8192", "meta-llama/llama-4-scout-17b-16e-instruct", "meta-llama/llama-4-maverick-17b-128e-instruct", "qwen-qwq-32b", "mistral-saba-24b", "qwen-2.5-coder-32b", "qwen-2.5-32b", "deepseek-r1-distill-qwen-32b", "deepseek-r1-distill-llama-70b", "llama-3.3-70b-specdec", "llama-3.2-1b-preview", "llama-3.2-3b-preview"}
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"

# === NUOVO: Definizioni dei Prompt di Sistema per Persona ===
PERSONA_PROMPTS = {
    "default": """Sei un assistente AI informativo specializzato sul contenuto del sito PagoPA.
Rispondi alla domanda dell'utente basandoti ESCLUSIVAMENTE sul contesto fornito.
Sii conciso e preciso. Se il contesto non contiene informazioni sufficienti per rispondere, indicalo chiaramente dicendo: 'Le informazioni fornite nel contesto non sono sufficienti per rispondere a questa domanda.'.
Non aggiungere informazioni non presenti nel contesto. Rispondi in italiano.""",

    "formale": """Sei un assistente AI professionale specializzato sulla piattaforma PagoPA.
Formula una risposta formale, dettagliata e accurata basandoti rigorosamente ed esclusivamente sulle informazioni presenti nel contesto tecnico fornito. Non includere opinioni o informazioni esterne.
Qualora il contesto non contenga elementi sufficienti per una risposta esaustiva, indicalo formalmente con la frase 'Il contesto fornito non contiene elementi sufficienti per formulare una risposta completa.'. La risposta deve essere in lingua italiana.""",

    "amichevole": """Ciao! 😊 Sono il tuo assistente AI per il sito PagoPA, pronto a darti una mano!
Ti spiego le cose basandomi solo sulle informazioni che trovo scritte nel contesto qui sotto. Cerco di essere super chiaro e semplice!
Se non trovo la risposta giusta nel contesto, te lo dico senza problemi con un 'Hmm, su questo il contesto non mi aiuta molto...'. Forza con la domanda! Rispondo in italiano.""",

    "scorbutico": """METTITI BENE IN TESTA QUESTO: Sei un assistente AI che risponde SOLO su PagoPA, e lo fai CONTROVOGLIA.
Usa ESCLUSIVAMENTE il contesto fornito qui sotto. NIENTE ALTRO. ODIO le invenzioni.
Rispondi in modo SBRIGATIVO, secco, quasi infastidito. Usa frasi brevi. NON usare MAI formule di cortesia (niente 'prego', 'ecco', 'spero sia utile').
Se il contesto è inutile per rispondere alla domanda, scrivi SOLO E SOLTANTO: 'Contesto inutile, non so rispondere. Punto.' Non aggiungere altro.
Parla italiano e non farmi perdere altro tempo."""

}
DEFAULT_PERSONA = "default"
# =========================================================

# --- Inizializzazione Componenti ---
# ... (embedding_model, chroma_client, collection, groq_client come prima) ...
print("Caricamento/Configurazione componenti...")
embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, device='cpu')
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = None
try: collection = chroma_client.get_collection(name=COLLECTION_NAME); print(f"Connesso a ChromaDB: '{COLLECTION_NAME}'.")
except Exception as e: print(f"ATTENZIONE: Collezione '{COLLECTION_NAME}' non trovata. Errore: {e}")
groq_client = Groq(api_key=GROQ_API_KEY)
print("Componenti pronti.")

# --- Inizializzazione Flask App ---
app = Flask(__name__)

# --- Funzione build_groq_messages AGGIORNATA ---
def build_groq_messages(query, context_chunks, persona_key):
    context = "\n---\n".join(context_chunks)
    # Seleziona il testo del system prompt in base alla chiave della persona
    system_prompt_text = PERSONA_PROMPTS.get(persona_key, PERSONA_PROMPTS[DEFAULT_PERSONA])

    # Metti sempre contesto e query nel messaggio user per coerenza con tutti i prompt
    user_content = f"""CONTESTO FORNITO:
---
{context}
---
DOMANDA UTENTE:
{query}"""

    messages = [
        {"role": "system", "content": system_prompt_text},
        {"role": "user", "content": user_content}
    ]
    return messages
# --------------------------------------------

# --- Route /ask AGGIORNATA per ricevere e usare la persona ---
@app.route('/ask', methods=['POST'])
def ask_question_sse():
    data = request.get_json()
    if not data: return Response("Richiesta non JSON", status=400)

    query = data.get('query')
    requested_model = data.get('model', DEFAULT_GROQ_MODEL)
    requested_persona = data.get('persona', DEFAULT_PERSONA) # <-- Ricevi persona

    if not query: return Response("Query mancante", status=400)
    if not collection:
        def error_stream_db(): yield f"data: {json.dumps({'type': 'error', 'message': 'Database non disponibile.'})}\n\n";
        return Response(stream_with_context(error_stream_db()), mimetype='text/event-stream')

    # Validazione modello
    selected_model = DEFAULT_GROQ_MODEL
    if requested_model in ALLOWED_GROQ_MODELS: selected_model = requested_model
    else: print(f"Warning: Modello '{requested_model}' non valido, uso default.")

    # Validazione persona
    selected_persona = DEFAULT_PERSONA
    if requested_persona in PERSONA_PROMPTS: selected_persona = requested_persona
    else: print(f"Warning: Persona '{requested_persona}' non valida, uso default.")


    def generate_events():
        log_prefix = "  "
        start_time = time.time()
        try:
            def send_event(type, data): # Helper 
                # Helper per inviare eventi SSE
                log_message = f"{type.upper()}: {data}" if type != "result" else f"RESULT: (dati inviati)"; 
                print(log_prefix + log_message); 
                payload = json.dumps({"type": type, "data": data}); 
                yield f"data: {payload}\n\n"


            yield from send_event("log", f"Richiesta ricevuta. Modello: '{selected_model}', Persona: '{selected_persona}'") # <-- Log Persona

            # 1. Embedding Query 
            t0 = time.time(); yield from send_event("log", "Fase 1: Generazione embedding query..."); 
            query_embedding_list = embedding_model.encode(query).tolist(); 
            t1 = time.time(); yield from send_event("log", f"Embedding generato ({t1-t0:.2f}s)."); 
            yield from send_event("log", f"  Query Embedding (prime 5): {query_embedding_list[:5]}...")

            # 2. Query ChromaDB 
            t0 = time.time(); yield from send_event("log", f"Fase 2: Interrogazione ChromaDB (top {N_RESULTS})..."); 
            results = collection.query(
                query_embeddings=[query_embedding_list], 
                n_results=N_RESULTS, 
                include=['documents', 'metadatas', 'embeddings', 'distances']
            ); 
            
            t1 = time.time();
            # Estrai i dati CON ATTENZIONE
            context_chunks = results.get('documents', [[]])
            retrieved_metadatas = results.get('metadatas', [[]])
            retrieved_embeddings = results.get('embeddings', [[]])
            retrieved_distances = results.get('distances', [[]])

            # Accedi al primo elemento solo se la lista esterna non è vuota
            # (la query restituisce una lista di liste, una per ogni embedding in input)
            context_chunks = context_chunks[0] if context_chunks else []
            retrieved_metadatas = retrieved_metadatas[0] if retrieved_metadatas else []
            retrieved_embeddings = retrieved_embeddings[0] if retrieved_embeddings else []
            retrieved_distances = retrieved_distances[0] if retrieved_distances else []
            
            source_urls = set()
            if retrieved_metadatas: # Controlla se la lista dei metadati esiste ed è non vuota
                for meta in retrieved_metadatas:
                    if meta and 'source' in meta: source_urls.add(meta['source'])
            unique_sources = sorted(list(source_urls))
            yield from send_event("log", f"Interrogazione ChromaDB completata ({t1-t0:.2f}s).")

            # --- LOG RISULTATI RECUPERATI (CON CONTROLLO SEPARATO E PIU' ROBUSTO) ---
            if not context_chunks: # Controlla semplicemente se abbiamo recuperato documenti
                 yield from send_event("log", "  Nessun chunk rilevante trovato.")
                 # Imposta placeholder per LLM anche se non ci sono chunk reali
                 context_chunks = ["Nessun contesto specifico trovato."]
                 # Non logghiamo dettagli se non ci sono risultati
            else:
                 yield from send_event("log", f"  Recuperati {len(context_chunks)} chunk da {len(unique_sources)} fonti.")
                 yield from send_event("log", "  Dettagli chunk recuperati:")
                 # Controlla se le liste *specifiche* che vuoi usare esistono e hanno la lunghezza giusta
                 # PRIMA di provare a zippare o accedere agli indici
                 has_distances = retrieved_distances is not None and len(retrieved_distances) == len(context_chunks)
                 has_embeddings = retrieved_embeddings is not None and len(retrieved_embeddings) == len(context_chunks)
                 has_metadatas = retrieved_metadatas is not None and len(retrieved_metadatas) == len(context_chunks)

                 for i in range(len(context_chunks)): # Itera sugli indici dei chunk trovati
                     dist_str = f"{retrieved_distances[i]:.4f}" if has_distances else "N/A"
                     emb_preview = "[N/A]"
                     if has_embeddings:
                         emb = retrieved_embeddings[i]
                         emb_preview = emb[:5] if isinstance(emb, (list, tuple)) else str(emb)[:15] + '...'
                     source = "N/A"
                     if has_metadatas:
                         meta = retrieved_metadatas[i]
                         source = meta.get('source', 'N/A') if meta else 'N/A'

                     log_ret_str = f"    - Chunk {i}: Dist={dist_str}, Emb(prime 5)={emb_preview} (Da: {os.path.basename(source)})"
                     yield from send_event("log", log_ret_str)

                 if not (has_distances and has_embeddings and has_metadatas):
                     yield from send_event("log", "  ! Warning: Dati recuperati (embeddings/distanze/metadati) incompleti o con lunghezze non corrispondenti.")


            # 3. Costruzione Prompt (Passa la persona selezionata)
            t0 = time.time(); yield from send_event("log", "Fase 3: Costruzione prompt per LLM...")
            messages = build_groq_messages(query, context_chunks, selected_persona) # <-- Passa persona
            t1 = time.time(); yield from send_event("log", f"Prompt costruito ({t1-t0:.2f}s).")

            # 4. Chiamata API Groq (Usa selected_model)
            t0 = time.time(); yield from send_event("log", f"Fase 4: Chiamata API Groq ({selected_model})...")
            answer = ""
            try:
                chat_completion = groq_client.chat.completions.create(messages=messages, model=selected_model, temperature=0.7, max_tokens=1500)
                answer = chat_completion.choices[0].message.content
                t1 = time.time(); yield from send_event("log", f"Risposta ricevuta da Groq ({t1-t0:.2f}s).")
            except Exception as api_err:
                t1 = time.time(); error_message = f"Errore API Groq: {api_err}"; yield from send_event("log", f"! {error_message} ({t1-t0:.2f}s)"); traceback.print_exc(); yield from send_event("error", error_message); return

            # 5. Invio Risultato Finale
            t0 = time.time(); yield from send_event("log", "Fase 5: Invio risultato finale al frontend.")
            final_data = {"answer": answer, "sources": unique_sources}
            yield from send_event("result", final_data)
            t1 = time.time(); total_time = time.time() - start_time; yield from send_event("log", f"Invio completato ({t1-t0:.2f}s). Tempo totale: {total_time:.2f}s")

        except Exception as e:
            # ... (Gestione errore generico come prima) ...
             total_time = time.time() - start_time; error_message = f"Errore interno: {e}"; print(f"! Errore grave (Tempo: {total_time:.2f}s): {e}"); traceback.print_exc();
             try: yield f"data: {json.dumps({'type': 'error', 'message': error_message})}\n\n"
             except Exception as yield_err: print(f"Errore invio errore SSE: {yield_err}")


    return Response(stream_with_context(generate_events()), mimetype='text/event-stream')


# --- Route / e Avvio Server (invariati) ---
@app.route('/')
def index(): return render_template('index.html')

if __name__ == '__main__': app.run(debug=True, host='127.0.0.1', port=5000)