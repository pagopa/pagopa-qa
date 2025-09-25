# File: app.py (Versione con Scelta Persona/Stile e Monitoring Langfuse)

import os
import chromadb
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
import json
from sentence_transformers import SentenceTransformer
from groq import Groq
from dotenv import load_dotenv
import traceback
import time
import uuid # [LANGFUSE] Importato per generare ID utente unici per il tracciamento

# --- Caricamento Configurazione ---
load_dotenv()

# [LANGFUSE] Importa la libreria Langfuse
from langfuse import Langfuse

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY: raise ValueError("Chiave API Groq (GROQ_API_KEY) non trovata.")

# --- Costanti e Configurazioni Varie ---
EMBEDDING_MODEL_NAME = 'all-MiniLM-L6-v2'
CHROMA_PATH = "chroma_db"
COLLECTION_NAME = "pagopa_sanp_docs"
N_RESULTS = 5
ALLOWED_GROQ_MODELS = { "gemma2-9b-it", "llama-3.1-8b-instant", "llama-3.1-70b-versatile", "llama3-70b-8192", "llama3-8b-8192", "mixtral-8x7b-32768" ,"deepseek-r1-distill-qwen-32b", "deepseek-r1-distill-llama-70b",}
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"
DEFAULT_TEMPERATURE = 0.7

PERSONA_PROMPTS = {
    "default": """Sei un assistente AI informativo specializzato sul contenuto del sito PagoPA. Il tuo nome è SANP-AI.
Rispondi alla domanda dell'utente basandoti ESCLUSIVAMENTE sul contesto fornito.
Sii conciso e preciso. Se il contesto non contiene informazioni sufficienti per rispondere, indicalo chiaramente dicendo: 'Le informazioni fornite nel contesto non sono sufficienti per rispondere a questa domanda.'.
Non aggiungere informazioni non presenti nel contesto. Rispondi in italiano.""",
    "formale": """Sei un assistente AI professionale specializzato sulla piattaforma PagoPA. Il tuo nome è SANP-AI.
Formula una risposta formale, dettagliata e accurata basandoti rigorosamente ed esclusivamente sulle informazioni presenti nel contesto tecnico fornito. Non includere opinioni o informazioni esterne.
Qualora il contesto non contenga elementi sufficienti per una risposta esaustiva, indicalo formalmente con la frase 'Il contesto fornito non contiene elementi sufficienti per formulare una risposta completa.'. La risposta deve essere in lingua italiana.""",
    "amichevole": """Ciao! 😊 Sono il tuo assistente AI per il sito PagoPA, pronto a darti una mano! Il tuo nome è SANP-AI.
Ti spiego le cose basandomi solo sulle informazioni che trovo scritte nel contesto qui sotto. Cerco di essere super chiaro e semplice!
Se non trovo la risposta giusta nel contesto, te lo dico senza problemi con un 'Hmm, su questo il contesto non mi aiuta molto...'. Forza con la domanda! Rispondo in italiano.""",
    "scorbutico": """METTITI BENE IN TESTA QUESTO: Sei un assistente AI che risponde SOLO su PagoPA, e lo fai CONTROVOGLIA.
Usa ESCLUSIVAMENTE il contesto fornito qui sotto. NIENTE ALTRO. ODIO le invenzioni.
Rispondi in modo SBRIGATIVO, secco, quasi infastidito. Usa frasi brevi. NON usare MAI formule di cortesia (niente 'prego', 'ecco', 'spero sia utile').
Se il contesto è inutile per rispondere alla domanda, scrivi SOLO E SOLTANTO: 'Contesto inutile, non so rispondere. Punto.' Non aggiungere altro.
Parla italiano e non farmi perdere altro tempo."""
}
DEFAULT_PERSONA = "default"

# --- Inizializzazione Componenti ---
print("Caricamento/Configurazione componenti...")
embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, device='cpu')
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = None
try:
    collection = chroma_client.get_collection(name=COLLECTION_NAME)
    print(f"Connesso a ChromaDB: '{COLLECTION_NAME}'.")
except Exception as e:
    print(f"ATTENZIONE: Collezione '{COLLECTION_NAME}' non trovata. Errore: {e}")

groq_client = Groq(api_key=GROQ_API_KEY)

# [LANGFUSE] Inizializza il client di Langfuse. Carica le chiavi dal file .env
try:
    langfuse = Langfuse()
    print("✅ Langfuse client inizializzato con successo.")
except Exception as e:
    print(f"❌ Errore inizializzazione Langfuse: {e}")
    langfuse = None # Se fallisce, il resto del codice non andrà in errore

print("Componenti pronti.")

# --- Inizializzazione Flask App ---
app = Flask(__name__)

# --- Funzione build_groq_messages (invariata) ---
def build_groq_messages(query, context_chunks, persona_key):
    context = "\n---\n".join(context_chunks)
    system_prompt_text = PERSONA_PROMPTS.get(persona_key, PERSONA_PROMPTS[DEFAULT_PERSONA])
    user_content = f"""CONTESTO FORNITO:\n---\n{context}\n---\nDOMANDA UTENTE:\n{query}"""
    messages = [
        {"role": "system", "content": system_prompt_text},
        {"role": "user", "content": user_content}
    ]
    return messages



# SOSTITUISCI L'INTERA FUNZIONE @app.route('/ask'...) CON QUESTA

@app.route('/ask', methods=['POST'])
def ask_question_sse():
    data = request.get_json()
    if not data:
        return Response("Richiesta non JSON", status=400)

    query = data.get('query')
    requested_model = data.get('model', DEFAULT_GROQ_MODEL)
    requested_persona = data.get('persona', DEFAULT_PERSONA)
    requested_temperature = float(data.get('temperature', DEFAULT_TEMPERATURE))
    session_id = data.get('sessionId') or f"anon-{uuid.uuid4()}"

    if not query:
        return Response("Query mancante", status=400)
        
    if not collection:
        def error_stream_db():
            yield f"data: {json.dumps({'type': 'error', 'message': 'Database non disponibile.'})}\n\n"
        return Response(stream_with_context(error_stream_db()), mimetype='text/event-stream')

    selected_model = requested_model if requested_model in ALLOWED_GROQ_MODELS else DEFAULT_GROQ_MODEL
    selected_persona = requested_persona if requested_persona in PERSONA_PROMPTS else DEFAULT_PERSONA
    selected_temperature = requested_temperature if 0.0 <= requested_temperature <= 1.0 else DEFAULT_TEMPERATURE

    # Qui definiamo la funzione generatore
    def generate_events():
        if langfuse:
            trace = langfuse.trace(
                name="rag-sse-request",
                user_id=session_id,
                input={"query": query, "model": selected_model, "persona": selected_persona},
                tags=["pagopa-rag", "flask-sse"]
            )
        
        start_time = time.time()
        try:
            def send_event(type, data):
                log_message = f"{type.upper()}: {data}" if type != "result" else f"RESULT: (dati inviati)"
                print(log_message)
                payload = json.dumps({"type": type, "data": data})
                yield f"data: {payload}\n\n"

            yield from send_event("log", f"Richiesta ricevuta. Modello: '{selected_model}', Persona: '{selected_persona}'")

            # --- 1. Embedding Query ---
            yield from send_event("log", "Fase 1: Generazione embedding query...")
            if langfuse:
                embedding_span = trace.span(name="query-embedding", input={"query": query})
            
            t0 = time.time()
            query_embedding_list = embedding_model.encode(query).tolist()
            if langfuse:
                embedding_span.end(output={"embedding_preview": query_embedding_list[:5]})

            t1 = time.time()
            yield from send_event("log", f"Embedding generato ({t1 - t0:.2f}s).")

            # --- 2. Query ChromaDB ---
            yield from send_event("log", f"Fase 2: Interrogazione ChromaDB (top {N_RESULTS})...")
            if langfuse:
                retrieval_span = trace.span(name="document-retrieval", input={"db": "ChromaDB", "n_results": N_RESULTS})

            t0 = time.time()
            results = collection.query(query_embeddings=[query_embedding_list], n_results=N_RESULTS, include=['documents', 'metadatas', 'distances'])
            
            context_chunks = results.get('documents', [[]])[0]
            retrieved_metadatas = results.get('metadatas', [[]])[0]
            retrieved_distances = results.get('distances', [[]])[0]
            
            if langfuse:
                retrieval_span.end(output={
                    "retrieved_documents": context_chunks, 
                    "metadatas": retrieved_metadatas, 
                    "distances": retrieved_distances
                })

            t1 = time.time()
            yield from send_event("log", f"Interrogazione ChromaDB completata ({t1 - t0:.2f}s).")
            
            if not context_chunks:
                yield from send_event("log", "  Nessun chunk rilevante trovato.")
            else:
                unique_sources = sorted(list({meta.get('source') for meta in retrieved_metadatas if meta and meta.get('source')}))
                yield from send_event("log", f"  Recuperati {len(context_chunks)} chunk da {len(unique_sources)} fonti.")
                yield from send_event("log", "  Dettagli chunk recuperati:")
                for i, chunk in enumerate(context_chunks):
                    dist_str = f"{retrieved_distances[i]:.4f}"
                    source_path = retrieved_metadatas[i].get('source', 'N/A')
                    source_name = os.path.basename(source_path)
                    log_ret_str = f"    - Chunk {i}: Dist={dist_str} (Da: {source_name})"
                    yield from send_event("log", log_ret_str)

            # --- 3. Costruzione Prompt ---
            yield from send_event("log", "Fase 3: Costruzione prompt per LLM...")
            messages = build_groq_messages(query, context_chunks, selected_persona)
            yield from send_event("log", "Prompt costruito.")
            
            # --- 4. Chiamata API Groq ---
            yield from send_event("log", f"Fase 4: Chiamata API Groq ({selected_model})...")
            if langfuse:
                llm_generation = trace.generation(
                    name="llm-generation-groq",
                    input=messages,
                    model=selected_model,
                    metadata={"persona": selected_persona, "temperature": selected_temperature}
                )

            t0 = time.time()
            answer = ""
            chat_completion = groq_client.chat.completions.create(messages=messages, model=selected_model, temperature=selected_temperature, max_tokens=1500)
            answer = chat_completion.choices[0].message.content
            
            if langfuse and chat_completion.usage:
                llm_generation.end(
                    output=answer,
                    usage={
                        "promptTokens": chat_completion.usage.prompt_tokens,
                        "completionTokens": chat_completion.usage.completion_tokens,
                        "totalTokens": chat_completion.usage.total_tokens
                    }
                )

            t1 = time.time()
            yield from send_event("log", f"Risposta ricevuta da Groq ({t1 - t0:.2f}s).")

            # --- 5. Invio Risultato Finale ---
            unique_sources = sorted(list({meta.get('source') for meta in retrieved_metadatas if meta and meta.get('source')}))
            final_data = {"answer": answer, "sources": unique_sources}
            yield from send_event("result", final_data)

            if langfuse:
                trace.update(output=final_data)

            total_time = time.time() - start_time
            yield from send_event("log", f"Tempo totale: {total_time:.2f}s")

        except Exception as e:
            error_message = f"Errore interno: {e}"
            print(f"! Errore grave: {e}")
            traceback.print_exc()
            
            if 'trace' in locals() and langfuse:
                trace.update(level='ERROR', status_message=str(e))
            
            try:
                yield f"data: {json.dumps({'type': 'error', 'message': error_message})}\n\n"
            except Exception as yield_err:
                print(f"Errore invio errore SSE: {yield_err}")
        
        finally:
            if 'trace' in locals() and langfuse:
                langfuse.flush()

    # QUESTA RIGA E' FONDAMENTALE E DEVE ESSERCI
    return Response(stream_with_context(generate_events()), mimetype='text/event-stream')



# --- Route / e Avvio Server (invariati) ---
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)