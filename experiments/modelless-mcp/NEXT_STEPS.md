# NEXT_STEPS — prima l'MVP locale, poi Azure

> Documento **didattico** in italiano. Ti dice cosa è stato prodotto qui, **come
> testare tutto in locale** (anche via Docker) **prima** di pensare al cloud, e
> **solo dopo** cosa chiedere all'IT per Azure.
> Ricorda: questo è un MCP **catalogo senza modelli** (à la awesome-copilot). Il server
> **distribuisce** asset AI in tre modi — **load effimero**, **hard install** e
> **notifiche/drift** — ma **non esegue nulla** e **non ospita modelli**: non serve
> alcun accesso a provider di inferenza (niente Azure OpenAI).

> **Principio di questo documento**: si costruisce e si **valida end-to-end un MCP
> funzionante in locale** (eseguibile e testabile senza cloud). Azure arriva **solo
> alla fine**, come porting di qualcosa già dimostrato. Allineato al
> [piano](plan/implementation_plan.md): M0→M3 locali, M4 unica milestone Azure.

## 1. Cosa hai già in mano (qui, in questo repo)

Tutto sotto `mcp_blueprint/modelless-mcp/`. Nulla del codice di produzione esistente
è stato modificato (solo analisi in sola lettura).

```text
mcp_blueprint/modelless-mcp/
├── README.md                        # indice del blueprint
├── NEXT_STEPS.md                    # questo file
├── analysis/
│   ├── inventory.md                 # inventario stack AI (IT)
│   └── mapping.md                   # mappatura asset → MCP (IT)
├── docs/learn/                      # documentazione DIDATTICA (IT)
│   ├── MCP-overview.md
│   ├── architettura.md
│   ├── flusso_prima_e_dopo_mcp.md
│   ├── security_and_runtime.md
│   └── governance_multi_team.md
├── specs/                           # specifiche tecniche (EN)
│   ├── architecture.md
│   ├── openapi.yml
│   └── manifests.md
├── plan/
│   └── implementation_plan.md       # roadmap e milestone (IT)
├── infra/azure/
│   └── README.md                    # guida deployment Azure (EN) — solo per M4
├── mcp-server-scaffold/             # FastAPI MVP funzionante + test (senza modelli)
│   ├── manifests/                   # manifest reali (skill/agent/prompt/policy) + template
│   └── ci/                          # GitHub Actions build/test/deploy
└── examples/
    ├── azure/                       # esempi di config Azure (solo per M4)
    ├── terraform-skeleton/          # IaC Azure Container Apps (solo per M4)
    └── helm-skeleton/                # chart AKS (solo per M4)
```

Lo scaffold è **eseguibile e testato** in locale (vedi
[mcp-server-scaffold/README.md](mcp-server-scaffold/README.md)) e
**non contiene alcun model router, adapter di provider, né motore di esecuzione degli
asset**: espone il catalogo (ricerca/lettura/descrittori di install) e lascia
l'esecuzione al modello **locale** del client.

## 2. FASE 1 — MVP locale (fai questo per primo)

L'obiettivo è avere il catalogo **funzionante e testabile sul tuo PC**, senza cloud e
senza nuovo repo. Bastano Python (e opzionalmente Docker).

### 2.1 Opzione A — Python diretto (giro più rapido)

```powershell
cd mcp_blueprint/modelless-mcp/mcp-server-scaffold
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
$env:MCP_AUTH_DISABLED = "1"     # DEV ONLY
uvicorn app.main:app --reload --port 8080
```

Poi verifica le operazioni del catalogo:

```powershell
curl http://127.0.0.1:8080/v1/health
curl http://127.0.0.1:8080/v1/assets                        # browse
curl "http://127.0.0.1:8080/v1/assets?q=mermaid&kind=skill" # search/filter
curl http://127.0.0.1:8080/v1/assets/mermaid-flow           # manifest (versione+digest)
curl http://127.0.0.1:8080/v1/assets/mermaid-flow/install   # install descriptor (hard install)
```

E la suite di test:

```powershell
$env:MCP_AUTH_DISABLED = "1"
pytest --cov=app --cov-report=term-missing
```

### 2.2 Opzione B — Docker in locale (ambiente riproducibile) ✅ consigliata

Lo scaffold ha già `Dockerfile` e `docker-compose.yml`. Girare in container in locale
**avvicina l'ambiente a quello di produzione** senza toccare Azure: stessa immagine
che poi userai in M4, ma eseguita sul tuo PC.

```powershell
cd mcp_blueprint/modelless-mcp/mcp-server-scaffold
docker compose up --build
# server su http://127.0.0.1:8080  (MCP_AUTH_DISABLED=1 è già impostato nel compose)
```

Perché Docker già ora conviene:

- **Parità d'ambiente**: la stessa immagine gira in locale e (in M4) su Azure Container
  Apps → meno sorprese "funziona sul mio PC".
- **Zero dipendenze cloud**: nessun modello, nessun provider, nessuna chiave. Il
  compose non richiede segreti perché il server non fa inferenza.
- **Onboarding rapido** per altri del team: `docker compose up` e via.

> Nota: in questa fase auth è disattivata (`MCP_AUTH_DISABLED=1`, **solo dev**).
> L'identità reale (Entra ID) è un problema di M4, non ora.

### 2.3 Connetti VS Code al catalogo locale (parità con il locale)

Il valore vero si vede quando **VS Code consuma il catalogo locale** e installa un
asset che diventa **selezionabile a mano** come uno scritto da te. Questo è il cuore
di M2 nel [piano](plan/implementation_plan.md):

1. Registra il server MCP locale nella configurazione MCP di VS Code (`settings.json`).
2. Fai **load effimero** di un asset (uso in sessione) → verifica il comportamento.
3. Fai **hard install** dello stesso asset (materializza il file in `.github/…`) →
   verifica che l'agente compaia nel **selettore** delle chat mode.
4. Modifica l'asset nel catalogo e verifica la **notifica/drift** ("update
   disponibile") sull'asset installato, poi il **re-install**.

### 2.4 Definizione di "MVP locale pronto"

Considera la Fase 1 completata quando, **senza alcun cloud**:

- [ ] Il server gira in locale (Python **o** Docker) e `pytest` è verde.
- [ ] Da VS Code fai **browse/search** del catalogo.
- [ ] Fai **load effimero** di almeno un asset e lo usi in sessione.
- [ ] Fai **hard install** di un agente e lo **selezioni a mano** nel picker.
- [ ] Dimostri la **notifica di aggiornamento + re-install** su un asset installato.
- [ ] Hai un **fallback offline** per gli asset critici.

A questo punto hai un prodotto **dimostrabile** end-to-end. Solo ora ha senso pensare
ad Azure.

## 3. FASE 2 — quando passare al repository dedicato

Passa a un nuovo repository/workspace dedicato **quando tutte queste condizioni sono
vere**:

1. La **Fase 1 (MVP locale)** è completa: la checklist §2.4 è tutta spuntata.
2. Hai letto e capito i documenti didattici in `docs/learn/`, incluse le **tre
   modalità** load / install / notify.
3. Hai deciso la topologia iniziale (consigliata: **Azure Container Apps**, stessa
   immagine Docker già provata in locale).
4. Hai un nome ufficiale per il repo (proposta: `mcp-catalog` o `qa-mcp-catalog`).

> L'ok dell'IT su Azure (§5) **non blocca** la Fase 1: puoi avviare la richiesta in
> parallelo, ma tutto l'MVP locale procede senza attese cloud.

### Come creare il nuovo repository (passi)

1. Crea il nuovo repo aziendale `mcp-catalog` (branch `main`, protezioni, CODEOWNERS).
2. Copia il contenuto di `mcp_blueprint/modelless-mcp/mcp-server-scaffold/`
   nella radice del nuovo repo.
3. Copia `specs/`, `docs/`, `plan/`, `infra/`,
   `examples/{terraform-skeleton,helm-skeleton}` nelle rispettive
   cartelle del nuovo repo (`manifests/` e `ci/` sono già dentro
   `mcp-server-scaffold/`, copiati al passo 2).
4. Sposta il workflow CI da `mcp-server-scaffold/ci/github-actions-deploy.yml` a
   `.github/workflows/` del nuovo repo e adegua i path (per ora **solo lint/test**,
   il deploy Azure si abilita in Fase 3).
5. Primo commit + push; verifica che CI (lint/test) sia verde.

## 4. FASE 3 — porting su Azure (solo dopo l'MVP locale)

Questa è l'**unica** fase cloud (milestone M4 del piano). Si prende l'immagine Docker
già provata in locale e la si porta su Azure aziendale: identità reale, persistenza
gestita, deploy e osservabilità. Guida completa in
[infra/azure/README.md](infra/azure/README.md).

Sequenza indicativa:

1. Landing zone Azure (subscription/RG/permessi) — vedi checklist IT §5.
2. App registration Entra ID + scope API; auth reale al posto dello stub.
3. Persistenza gestita: da file/SQLite locale a **PostgreSQL Flexible**.
4. Segreti in **Key Vault** + **Managed Identity**.
5. Deploy su **Azure Container Apps** (la stessa immagine del `docker compose` locale).
6. Telemetria: **Application Insights** + Log Analytics.
7. CI/CD via **OIDC federation** GitHub↔Azure (niente credenziali statiche).

## 5. COSA chiedere all'IT/Azure (solo per la Fase 3)

Porta all'IT questa lista **quando arrivi alla Fase 3** (puoi anticipare la richiesta
in parallelo alla Fase 1, ma non è un blocco). Sono richieste standard per un servizio
containerizzato. **Non serve accesso a modelli/Azure OpenAI**, perché il server non fa
inferenza.

- [ ] **Subscription Azure** e un **Resource Group** dedicati (es. `rg-mcp-mvp`).
- [ ] Regione consentita (es. `westeurope`) e vincoli di **data residency**.
- [ ] Permesso di creare: **Container Apps** (o AKS), **Container Registry (ACR)**,
      **Key Vault**, **PostgreSQL Flexible**, **Redis**, **Application Insights**.
- [ ] **App registration** su Entra ID (Azure AD) per il server + uno **scope API**.
- [ ] Possibilità di mappare **gruppi Entra ID** ai ruoli tenant (`user`, `admin`).
- [ ] **Managed Identity** per l'app (per leggere i segreti da Key Vault).
- [ ] **OIDC federation** tra GitHub e Azure (per CI/CD senza credenziali statiche).
- [ ] Eventuali requisiti di **rete privata** (private endpoint per DB/Redis).
- [ ] **Secret del repo GitHub** per il deploy OIDC: `AZURE_CLIENT_ID`,
      `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `ACR_NAME`, `RESOURCE_GROUP`.

### Come spiegarlo in una frase all'IT

> "Devo pubblicare un piccolo servizio HTTP in container su Azure, autenticato con
> Entra ID, che serve asset versionati e conserva stato in Postgres/Redis, con segreti
> in Key Vault. **Non usa alcun modello AI.** Mi servono la subscription, i permessi
> per creare queste risorse e una app registration."

## 6. Decisioni ancora aperte (da prendere durante la Fase 1/2)

| Decisione | Opzioni | Nota |
|---|---|---|
| Runtime locale | Python diretto vs **Docker** | Docker consigliato per parità con M4 |
| Topologia cloud (Fase 3) | Container Apps vs AKS | Consigliata ACA per l'MVP |
| Dipendenza `src/utility` | skill self-contained vs starter-kit pacchettizzato | Impatta le skill di generazione codice (interpretate dal modello locale) |
| Nome/scope API | `api://mcp-catalog/.default` | Concordare con IT (solo Fase 3) |
| Modello di inferenza | **Locale (seat Copilot)** | Nessun modello lato server, per scelta |
| Firma/provenienza asset | sigstore/cosign vs firma interna | Per integrità catalogo e verifica su install |
| Retention audit | 30 / 90 / 180 gg | Dipende da policy compliance |

## 7. Riferimenti rapidi

- Impara MCP: [docs/learn/MCP-overview.md](docs/learn/MCP-overview.md)
- Sicurezza/runtime: [docs/learn/security_and_runtime.md](docs/learn/security_and_runtime.md)
- Governance team: [docs/learn/governance_multi_team.md](docs/learn/governance_multi_team.md)
- Architettura: [specs/architecture.md](specs/architecture.md)
- API: [specs/openapi.yml](specs/openapi.yml)
- Piano: [plan/implementation_plan.md](plan/implementation_plan.md)
- Deploy Azure (Fase 3): [infra/azure/README.md](infra/azure/README.md)

---

**In sintesi**: **prima** fai girare e valida l'MVP **in locale** (Python o, meglio,
**Docker**) fino alla checklist §2.4 — browse, load effimero, hard install
selezionabile a mano, notifica/drift + re-install, tutto senza cloud. **Solo dopo**
crei il repo `mcp-catalog` e porti la **stessa immagine Docker** su Azure (Fase 3).
Non serve alcun provider di modelli. Quando l'MVP locale è pronto, dimmelo e riprendo
da lì.
