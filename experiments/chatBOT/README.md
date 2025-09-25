Chatbot RAG per la documentazione SANP di PagoPA
Questo file è la guida completa per configurare ed eseguire il chatbot. Segui attentamente i passaggi per assicurarti che tutto funzioni correttamente.

📁 Struttura del Progetto
Prima di iniziare, assicurati di organizzare i file e le cartelle del tuo progetto esattamente in questo modo. L'applicazione Flask richiede che i file index.html e style.css si trovino in cartelle specifiche.

.
├── 📁 static/
│   └── style.css
├── 📁 templates/
│   └── index.html
├── .env
├── 01_prepare_database.py
├── app-with-embeddings-log-and-langfuse-enhanced.py
├── README.md
├── requirements.txt
├── scraped_pagopa_it_urls.py
└── scraper-pagopa.py
🛠️ Istruzioni di Configurazione
Segui questi passaggi per preparare l'ambiente di lavoro.

Passo 1: Crea l'Ambiente Virtuale e Installa le Dipendenze
È fondamentale usare un ambiente virtuale per non installare pacchetti a livello di sistema.


# 1. Apri un terminale nella cartella principale del progetto
# 2. Crea l'ambiente virtuale
python -m venv venv

# 3. Attiva l'ambiente
#    Su Windows:
venv\Scripts\activate
#    Su macOS/Linux:
source venv/bin/activate

# 4. Installa tutte le librerie necessarie dal file requirements.txt
pip install -r requirements.txt
Passo 2: Configura le Chiavi API nel file .env
L'applicazione ha bisogno di una chiave API per comunicare con il modello linguistico.

Nella cartella principale del progetto, crea un nuovo file e chiamalo esattamente .env.

Apri il file .env con un editor di testo.

Copia e incolla il testo seguente nel file:


# Incolla qui la tua chiave API di Groq
GROQ_API_KEY="gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
Sostituisci "gsk_xxxxxxxx..." con la tua vera chiave API che puoi ottenere gratuitamente dalla console di Groq.

Salva e chiudi il file.

🚀 Istruzioni di Esecuzione
Ora che tutto è configurato, segui questa sequenza per avviare l'applicazione. L'ordine è importante.

Azione 1: Esegui lo script per preparare il Database (01_prepare_database.py)
Questo script legge tutti gli URL, scarica il testo e lo salva in un database locale. Va eseguito solo una volta (o ogni volta che vuoi aggiornare i dati).


# Assicurati che il tuo ambiente virtuale sia attivo
python 01_prepare_database.py
Attendi il completamento. Vedrai una nuova cartella chiamata chroma_db apparire nel tuo progetto.

Azione 2: Esegui lo script dell'Applicazione Web (app-with-embeddings-log-and-langfuse-enhanced.py)
Questo comando avvia il server web locale che ospita il chatbot.


# Assicurati che il tuo ambiente virtuale sia attivo
python app-with-embeddings-log-and-langfuse-enhanced.py
Azione 3: Apri il Browser
Dopo aver eseguito il comando precedente, il terminale mostrerà un messaggio simile a:
* Running on http://127.0.0.1:5000

Copia l'indirizzo http://127.0.0.1:5000.

Incollalo nella barra degli indirizzi del tuo browser web (Chrome, Firefox, etc.).

Premi Invio.

Ora dovresti vedere l'interfaccia del chatbot, pronto per essere utilizzato.