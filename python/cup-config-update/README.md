# Aggiornamento tabella `pagopapcanoneunicosaecconfigtable`

## 📌 Obiettivo

Questo script Python automatizza il processo di aggiornamento annuale della tabella:

**`pagopapcanoneunicosaecconfigtable`**

La tabella contiene le informazioni degli Enti Creditori (EC) utilizzate dalla componente GPD per la generazione delle posizioni debitorie relative al **Canone Unico Patrimoniale (CUP)**.

---

## 🗂️ Sorgenti dati utilizzate

### 1. OpenData IPA (`enti.xlsx`)
Da questo dataset vengono estratti:

- `RowKey` — Codice fiscale dell’ente  
- `CompanyName` — Denominazione  
- `PaIdIstat` — Codice ISTAT  
- `PaIdCatasto` — Codice catastale  
- `PaPecEmail` — PEC  

Sono considerate solo le categorie:

- **L5 – Province**
- **L6 – Comuni**

---

### 2. Database di configurazione Nodo Dei Pagamenti (PostgreSQL)

Lo script esegue una query che recupera:

- IBAN prioritario dell’ente oppure l’ultimo inserito
- Etichetta dell’IBAN
- Codice CBILL
- Nome ente

Filtri applicati:
- `ID_INTERMEDIARIO_PA` = '15376371009'
- `ID_STAZIONE` = '15376371009_01'
- `segregazione` = '47'
- `p.enabled` = 'Y'

---

### 3. API SelfCare

Utilizzate per recuperare:

- Email referente
- Nome e cognome referente

Workflow:

1. `/institutions?taxCode=<EC_CF>`
2. Recupero `institutionId`
3. `/users/{institutionId}/users`
4. Recupero referente

Se i dati non sono disponibili → fallback dal CSV storico.

---

### 4. CSV storico EC config table

Utilizzato per recuperare:

- Referente email  
- Referente nome  

in caso di valori non ottenibili dalle API.

---

## ⚙️ Variabili di ambiente richieste

| Variabile | Descrizione |
|----------|-------------|
| `PG-DB-NAME` | Nome database PostgreSQL |
| `PG-USER-NAME` | Username |
| `PG-USER-PASSWORD` | Password |
| `PG-HOST` | Host database |
| `PG-PORT` | Porta database |
| `API-INSTITUTION-URL` | Endpoint SelfCare istituzioni |
| `API-USERS-URL` | Endpoint SelfCare utenti |
| `API-KEY` | Subscription key |
| `EC-CONFIG-TABLE` | File CSV storico |
| `IPA-FILE` | Nome del file IPA (default: `enti.xlsx`) |

Percorsi utilizzati:

- `input/<IPA-FILE>`
- `input/<EC-CONFIG-TABLE>`
- `output/pagopaucanoneunicosaecconfigtable.csv`

---

## 🧠 Logica del processo

### **Fase 1 — Preparazione dati**

- Caricamento file IPA
- Filtraggio su categorie L5/L6
- Ridenominazione colonne
- Rimozione record inconsistenti
- Caricamento CSV storico
- Caricamento dati da SQL

---

### **Fase 2 — Arricchimento dati per ogni ente**

Per ciascun EC:

1. Recupero referente tramite API SelfCare  
2. Fallback su CSV storico in caso di valori mancanti  
3. Recupero IBAN / CBILL da SQL  
4. Creazione entità nel formato Azure Table Storage:

```json
{
  "PartitionKey": "org",
  "RowKey": "...",
  "CompanyName": "...",
  "CompanyName@type": "String",
  "Iban": "...",
  "Iban@type": "String",
  "PaIdCatasto": "...",
  "PaIdCatasto@type": "String",
  "PaIdCbill": "...",
  "PaIdCbill@type": "String",
  "PaIdIstat": "...",
  "PaIdIstat@type": "String",
  "PaPecEmail": "...",
  "PaPecEmail@type": "String",
  "PaReferentEmail": "...",
  "PaReferentEmail@type": "String",
  "PaReferentName": "...",
  "PaReferentName@type": "String"
}
```
---
## 🧾 Struttura del CSV generarto

- PartitionKey
- RowKey
- CompanyName
- CompanyName@type
- Iban
- Iban@type
- PaIdCatasto
- PaIdCatasto@type
- PaIdCbill
- PaIdCbill@type
- PaIdIstat
- PaIdIstat@type
- PaPecEmail
- PaPecEmail@type
- PaReferentEmail
- PaReferentEmail@type
- PaReferentName
- PaReferentName@type
---
## ▶️ Installazione ed esecuzione
Installazione dipendenze
```
pip install azure-data-tables pandas psycopg2 requests openpyxl
```
Avvio dello script
```
python3 script.py
```
Il file risultante verrà salvato in
```
output/pagopaucanoneunicosaecconfigtable.csv
```
---
## 🔄 Backup
Prima di sovrascrivere la tabella:
- Salvare il CSV precedente
- Registrare eventuali EC mancanti o con dati incompleti
- Validare la correttezza degli IBAN
