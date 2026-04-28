# pagopa-qa

[![Integration Tests](https://github.com/pagopa/pagopa-qa/actions/workflows/integration_test.yml/badge.svg?branch=main)](https://github.com/pagopa/pagopa-qa/actions/workflows/integration_test.yml)

Questo repository è il **contenitore centralizzato** delle attività di Quality Assurance, automazione, analisi dati e tooling operativo del team **PagoPA**.
Raccoglie in un unico posto test di integrazione, test di performance, script Python, job Spark, notebook Jupyter, esperimenti e infrastruttura as-code.

---

## Indice

- [Struttura del Repository](#struttura-del-repository)
- [Microservizio (Spring Boot)](#microservizio-spring-boot)
- [Integration Test](#integration-test-)
- [Performance Test](#performance-test-)
- [Postman Collection](#postman-collection-)
- [Script Python](#script-python-)
- [CDE Jobs (Spark / PySpark)](#cde-jobs-spark--pyspark-)
- [Data Analysis (Jupyter Notebooks)](#data-analysis-jupyter-notebooks-)
- [Experiments](#experiments-)
- [Infrastruttura](#infrastruttura-)
- [Scripts di Manutenzione / Monitoring](#scripts-di-manutenzione--monitoring-)
- [GitHub Actions Workflows](#github-actions-workflows-)
- [Docker](#docker-)

---

## Struttura del Repository

```
pagopa-qa/
├── .devops/                          # Pipeline Azure DevOps per performance test
├── .github/
│   └── workflows/                    # GitHub Actions CI/CD e job schedulati
├── .identity/                        # Terraform - Workload Identity (GitHub OIDC)
├── .opex/                            # Configurazione Opex/Dashboard
├── cde-jobs/                         # Job PySpark per CDE (Cloudera Data Engineering)
│   ├── psp-kpi/                      #   → Aggregazione KPI PSP in tabelle Gold
│   └── rtp/                          #   → Analisi posizioni debitorie RTP
├── data analysis/                    # Jupyter Notebooks per analisi esplorative
├── docker/                           # Docker Compose e script per ambiente locale
├── experiments/
│   └── chatBOT/                      # Chatbot RAG sulla documentazione SANP
├── helm/                             # Helm chart per deploy su Kubernetes (AKS)
├── infra/                            # Terraform - APIM API
├── integration-test/                 # Integration test BDD (Cucumber.js)
├── openapi/                          # Specifica OpenAPI 3.0
├── performance-test/                 # Performance test con k6
├── postman-collection/               # Collezione Postman + script Newman
├── python/                           # Script Python operativi
│   ├── check-biz-events-differences/ #   → Confronto Business Events
│   ├── cup-config-update/            #   → Aggiornamento config CUP (Azure Table)
│   ├── gpd-dl-recovery/              #   → Recovery dead-letter GPD su EventHub
│   ├── gpd-get-fdr/                  #   → Recupero flussi FDR (rendicontazione)
│   ├── gpd-report/                   #   → Report GPD (debt positions + ACA broker)
│   ├── issuerrangetable-check/       #   → Verifica overlap range issuer (Azure Table)
│   ├── payments-with-agreement-report/ # → Report pagamenti con convenzione (ADX)
│   └── smo-support-cbill-iban/       #   → Caricamento CBILL/IBAN via API
└── src/
    ├── main/
    │   ├── java/                     # Sorgenti Java Spring Boot (microservizio base)
    │   ├── resources/                # Configurazione applicazione
    │   └── scripts/                  # Script Python per manutenzioni/monitoring
    └── test/                         # Unit test Java (JUnit)
```

---

## Microservizio (Spring Boot)

Il repository contiene il template base del microservizio **pagopa-afm-calculator** (Advanced Fee Management), sviluppato in Java 11 con Spring Boot.

### Technology Stack

| Componente | Versione |
|---|---|
| Java | 11 |
| Spring Boot | - |
| Maven | - |
| Helm Chart | `microservice-chart` v5.9.0 |

### Avvio locale 🚀

**Prerequisiti:** `docker`, `az CLI`

```shell
# Da ./docker
sh ./run_docker.sh local
```

> ℹ️ Per PagoPa ACR è necessario il login: `az acr login -n <acr-name>`

### Sviluppo locale 💻

**Prerequisiti:** `git`, `maven`, `jdk-11`

```shell
mvn spring-boot:run -Dspring-boot.run.profiles=local
```

**Spring Profiles:**
- `local` — per sviluppo in locale
- _(default)_ — legge le properties dall'ambiente Azure

### Unit Test

```shell
mvn clean verify
```

### API Documentation 📖

Spec OpenAPI 3.0 disponibile in [`openapi/openapi.json`](openapi/openapi.json).

---

## Integration Test 🧪

Test di integrazione BDD basati su **Cucumber.js** (Node.js).

**Percorso:** `integration-test/`

### Technology Stack

- [Cucumber.js](https://github.com/cucumber/cucumber-js)
- Node.js v14+
- Yarn

### Come eseguire

```shell
# Da integration-test/src/
yarn install
yarn test
```

Per eseguire un singolo feature file o scenario:

```shell
npx cucumber-js -r step_definitions features/<filename>.feature
npx cucumber-js -r step_definitions features/<filename>.feature:46
```

### Eseguire via Docker

```shell
# Da integration-test/
sh ./run_integration_test.sh <local|dev|uat|prod> <subscription-key>
```

Configura le variabili d'ambiente in `integration-test/src/config/.env.<env>`.

---

## Performance Test 🚀

Performance test realizzati con **[k6](https://k6.io/)**.

**Percorso:** `performance-test/`

### Tipi di test disponibili

| Tipo | File |
|---|---|
| Smoke | `test-types/smoke.json` |
| Load | `test-types/load.json` |
| Stress | `test-types/stress.json` |
| Spike | `test-types/spike.json` |
| Soak | `test-types/soak.json` |
| Constant | `test-types/constant.json` |

### Come eseguire

```shell
# Metodo diretto k6
k6 run \
  --env VARS=local.environment.json \
  --env TEST_TYPE=./test-types/load.json \
  --env API_SUBSCRIPTION_KEY=<your-secret> \
  main_scanario.js

# Via script Docker
sh run_performance_test.sh <local|dev|uat|prod> <load|stress|spike|soak> <script> <db-name> <subkey>
```

---

## Postman Collection 📬

**Percorso:** `postman-collection/`

Contiene la collezione Postman con tutti gli ambienti (dev, uat, prod).

### Eseguire con Newman

```shell
sh run_newman.sh
```

### Importare in Postman

Seguire la [guida ufficiale Postman](https://learning.postman.com/docs/getting-started/importing-and-exporting-data/) per importare collezione e ambienti.

---

## Script Python 🐍

**Percorso:** `python/`

Raccolta di script operativi Python per supporto, monitoring e reportistica.

### `gpd-report`

Genera report sulle **posizioni debitorie GPD** e sui **broker ACA**.
- Fonte dati: PostgreSQL (`apd.payment_position`)
- Output: grafici, report su Azure Blob Storage, notifiche Slack
- Eseguito ogni lunedì mattina via GitHub Actions (`gpd_report.yml`)

```shell
# Variabili d'ambiente richieste:
# PG_APD_CONNECTION_STRING, PG_CFG_CONNECTION_STRING
# SA_ACCOUNT_NAME, SA_ACCOUNT_KEY, SA_BLOB_CONTAINER_NAME
# START_DATE, END_DATE
python gpd-report/debt-position-report.py
python gpd-report/broker-aca-report.py
```

### `gpd-dl-recovery`

Script per il **recovery delle dead-letter** del servizio GPD.
- Si connette al database PostgreSQL GPD
- Ripubblica i messaggi falliti su **Azure EventHub**
- Triggerabile via GitHub Actions (`gpd_dl_recovery.yml`)

```shell
# Variabili d'ambiente richieste:
# DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
# + variabili EventHub
python gpd-dl-recovery/gpd-dl-recovery.py
```

### `gpd-get-fdr`

Recupera i **flussi di rendicontazione (FDR)** per gli Enti Creditori e li salva su Azure Blob Storage.
- Legge la lista EC da `config/ec-list_prod.csv`
- Chiama l'API `nodoChiediFlussoRendicontazione` (SOAP)
- Supporta enrollment EC su Creditor Institution

```shell
# Variabili d'ambiente richieste:
# FR_NEW_CONN_SUBKEY_PRD, FR_SA_CONN_STRING_PRD, FR_ENV, FR_DATE, ...
python gpd-get-fdr/get-flows.py
python gpd-get-fdr/enroll-ci.py
```

### `cup-config-update`

Automatizza l'**aggiornamento annuale della tabella CUP** (`pagopapcanoneunicosaecconfigtable`).
- Fonti: OpenData IPA (`enti.xlsx`), Database Nodo (PostgreSQL), API SelfCare
- Genera e carica la configurazione su Azure Table Storage
- Include flowchart del processo

```shell
pip install -r python/cup-config-update/requirements.txt
python python/cup-config-update/cup-config-generator.py
python python/cup-config-update/cup-config-updater.py
```

Consulta [`python/cup-config-update/README.md`](python/cup-config-update/README.md) per i dettagli.

### `issuerrangetable-check`

Verifica la presenza di **overlap tra range issuer** nella tabella Azure `pagopapweuafmsaissuerrangetable`.

```shell
# Variabile d'ambiente richiesta:
# AZ_CONNECTION_STRING
python python/issuerrangetable-check/isuuer-range-check.py
```

### `payments-with-agreement-report`

Genera report sui **pagamenti con convenzione** interrogando **Azure Data Explorer (Kusto)**.
- Interroga il cluster `pagopapdataexplorer.westeurope.kusto.windows.net`
- Analizza eventi di tipo `pspNotifyPaymentV2`

```shell
pip install -r python/payments-with-agreement-report/requirements.txt
python python/payments-with-agreement-report/build-payments-report.py
```

### `smo-support-cbill-iban`

Supporto SMO per il **caricamento bulk di dati CBILL e IBAN** tramite le API di configurazione PagoPA.

```shell
# Variabili d'ambiente richieste:
# UAT_SUBSCRIPTION_KEY, PROD_SUBSCRIPTION_KEY
python python/smo-support-cbill-iban/cbill-iban-upload.py
```

### `check-biz-events-differences`

Confronta i **Business Events** esportati da Cosmos DB con quelli attesi, producendo CSV con le differenze.

```shell
python python/check-biz-events-differences/export-from-cosmos.py
python python/check-biz-events-differences/check-diff-csv.py
```

---

## CDE Jobs (Spark / PySpark) ⚡

**Percorso:** `cde-jobs/`

Job PySpark pensati per girare su **Cloudera Data Engineering (CDE)** con Spark 3.x e Hive.

### `rtp` — Analisi posizioni debitorie RTP

Elabora le tabelle silver GPD per produrre statistiche aggregate sulle posizioni debitorie collegate a RTP.

- Source: `pagopa.silver_gpd_payment_option`, `pagopa.silver_gpd_payment_position`, `pagopa_dev.rtp_pt_report`
- Funzionalità: AQE abilitato, proiezione colonne, broadcast join

```shell
spark-submit cde-jobs/rtp/rtp_analysis_job.py
```

### `psp-kpi` — KPI PSP Gold

Aggrega i KPI dei PSP da tabelle silver verso tabelle **Gold Iceberg**.

- Source: `silver_kpi_psp`, `contracts_crm` (aggregazioni CRM)
- Target: `gold_kpi_pagamenti_psp`
- Configurabile via `spark.conf` (periodo, database, limiti campione)

```shell
spark-submit \
  --conf spark.job.period_start=2025-01-01T00:00:00Z \
  --conf spark.job.period_end=2025-01-31T00:00:00Z \
  cde-jobs/psp-kpi/jobs/process_agregated_kpis.py
```

---

## Data Analysis (Jupyter Notebooks) 📊

**Percorso:** `data analysis/`

Notebook Jupyter per analisi esplorative e sperimentali.

| Notebook | Descrizione |
|---|---|
| `Analisi Dati GoLive RTP.ipynb` | Analisi dati al go-live del servizio RTP |
| `Analisi_Dati_GoLive_RTP_OPTIMIZED.ipynb` | Versione ottimizzata dell'analisi RTP |
| `RTP analisi dati.ipynb` | Analisi dati RTP generale |
| `Anonymize PII Example using MS Presidio.ipynb` | Esempio di anonimizzazione PII con Microsoft Presidio |
| `wisp-station-trx.ipynb` | Analisi transazioni WISP per stazione |

---

## Experiments 🔬

**Percorso:** `experiments/`

### `chatBOT` — Chatbot RAG sulla documentazione SANP

Applicazione **Flask** che implementa un chatbot RAG (Retrieval Augmented Generation) basato sulla documentazione SANP di PagoPA.

**Stack tecnologico:**
- Flask (web server)
- ChromaDB (vector store locale)
- Groq API (LLM)
- Langfuse (monitoraggio e logging LLM)
- BeautifulSoup (web scraping documentazione)

**Setup rapido:**

```shell
cd experiments/chatBOT

# 1. Crea e attiva l'ambiente virtuale
python -m venv venv
source venv/bin/activate   # macOS/Linux

# 2. Installa dipendenze
pip install -r requirements.txt

# 3. Configura le chiavi API nel file .env
echo 'GROQ_API_KEY="gsk_xxxx..."' > .env

# 4. Prepara il database vettoriale (solo prima volta)
python 01_prepare_database.py

# 5. Avvia l'applicazione
python app-with-embeddings-log-and-langfuse-enhanced.py
```

Consulta [`experiments/chatBOT/README.md`](experiments/chatBOT/README.md) per la guida completa.

---

## Infrastruttura 🏗️

### `infra/` — Terraform APIM

Gestisce le API su **Azure API Management** (APIM).

```shell
cd infra
# Deploy su un ambiente specifico
./terraform.sh apply <weu-dev|weu-uat|weu-prod>
```

### `.identity/` — Terraform Workload Identity

Configura le **GitHub Environments** e le **Managed Identity** per l'autenticazione OIDC tra GitHub Actions e Azure.

```shell
cd .identity
./terraform.sh apply <dev|uat|prod>
```

### `helm/` — Helm Chart (AKS)

Chart Helm basata su `microservice-chart` (pagopa Blueprint) per il deploy su AKS.

```shell
helm upgrade --install pagopa-afm-calculator ./helm \
  -f helm/values-<dev|uat|prod>.yaml
```

---

## Scripts di Manutenzione / Monitoring 🔧

**Percorso:** `src/main/scripts/`

Script Python usati dai workflow GitHub Actions schedulati per la gestione delle comunicazioni di stato.

| Script | Descrizione |
|---|---|
| `station-maintenance.py` | Recupera le manutenzioni delle stazioni dall'API backoffice e le pubblica su **BetterStack** (Status Page) |
| `station-maintenance-with-involvedPA.py` | Variante con PA coinvolte nella manutenzione |
| `station-maintenance-aggregated.py` | Report aggregato delle manutenzioni |
| `opsgenie-incidents.py` | Sincronizza gli **incidenti Opsgenie** (tag `toStatusPage`) verso **BetterStack Status Page** |

---

## GitHub Actions Workflows ⚙️

**Percorso:** `.github/workflows/`

| Workflow | Trigger | Descrizione |
|---|---|---|
| `integration_test.yml` | Push / Manual | Esegue gli integration test |
| `release_deploy.yml` | Tag push | Build, release e deploy |
| `deploy_with_github_runner.yml` | Manual | Deploy tramite GitHub runner |
| `gpd_report.yml` | Lunedì 03:00 UTC | Report GPD debt positions |
| `gpd_aca_report.yaml` | Schedulato | Report ACA broker |
| `gpd_dl_recovery.yml` | Manual | Recovery dead-letter GPD |
| `gpd_get_fdr.yaml` | Schedulato | Recupero flussi FDR |
| `scheduled-maintenance_backoffice_pagopa_to_betterstack.yml` | Schedulato | Sync manutenzioni → BetterStack |
| `scheduled-maintenance-backoffice-pagopa-with-PA-to-betterstack.yml` | Schedulato | Sync manutenzioni con PA → BetterStack |
| `statuspage-backoffice-maintenance-aggregated.yml` | Schedulato | Report manutenzioni aggregato |
| `scheduled-opsgenie-incidents-to-statuspage.yml` | Schedulato | Sync incidenti Opsgenie → StatusPage |
| `create_dashboard.yaml` | Manual | Creazione dashboard Opex |
| `code_review.yml` | PR | Code review automatica |
| `check_pr.yml` | PR | Validazione PR |
| `anchore.yml` | Push | Scansione vulnerabilità container |
| `gh-workflow-immortality.yml` | Schedulato | Keep-alive dei workflow schedulati |

---

## Docker 🐳

**Percorso:** `docker/`

Script per avviare il microservizio e le dipendenze in locale tramite Docker Compose.

```shell
# Da ./docker
sh ./run_docker.sh <local|dev|uat|prod>
```

> ℹ️ Per PagoPa ACR è necessario il login: `az acr login -n <acr-name>`
> Se eseguito senza parametro, viene usato `local` come default.

---

## Prerequisiti globali

| Tool | Utilizzo |
|---|---|
| `git` | Version control |
| `docker` / `docker compose` | Ambiente locale e CI |
| `az CLI` | Login Azure / ACR |
| `terraform` (v`$(cat .terraform-version)`) | Infrastruttura |
| `helm` | Deploy Kubernetes |
| `node` / `yarn` | Integration test |
| `k6` | Performance test |
| `python 3.9+` | Script Python e CDE jobs |
| `mvn` / `jdk-11` | Build microservizio Java |

---

## Contributing

Il repo è gestito dal team **@pagopa/pagopa-team-qa**.
Aprire una Pull Request seguendo il template in `.github/PULL_REQUEST_TEMPLATE.md`.

#### Performance testing

install [k6](https://k6.io/) and then from `./performance-test/src`

1. `k6 run --env VARS=local.environment.json --env TEST_TYPE=./test-types/load.json main_scenario.js`

---

## Contributors 👥

Made with ❤️ by PagoPa S.p.A.

### Maintainers

See `CODEOWNERS` file
