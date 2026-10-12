# Centro di Competenza QA — Presentazione al nuovo Direttore (design)

## Contesto

Cambio di Direzione: il nuovo Direttore (Stefano) arriva da dentro PagoPA, ha un profilo business e conosce poco il Centro di Competenza QA. Incontro di **45 minuti** con il team QA interno: Cristiano (Manager), Andrea (Lead Tecnico), Annalisa (Business/Data Analyst). L'incontro è successivo al 12/10/2026.

Obiettivi:
- presentare **chi siamo, cosa facciamo, perché, dove vogliamo andare**;
- continuità del progetto;
- **messaggio implicito** (non una richiesta esplicita): serve una struttura riconosciuta in organigramma, come la struttura duale su SEND (SL QA&OPS), per avere autorevolezza verso i team di sviluppo.

Vincolo: pochissime slide, molto sintetiche, linguaggio business, nessun dettaglio operativo (Gherkin, branching model, flow-diagram modali).

## Output

Nuovo file: `docs/presentazioni/QA_Presentazione_Direttore_2026.html`, con foto in `docs/presentazioni/img/` (`cristiano-foto.jpeg`, `andrea-foto.png`, `annalisa-foto.jpeg`).

- Riusa il motore HTML/CSS/JS di `QA_AllHands_2026.html` (slide system, progress bar, nav dots, toggle light/dark, font, palette) per coerenza di brand.
- HTML/CSS/JS statico, nessuna nuova libreria. Nessun modal di approfondimento.
- Le foto sono referenziate con path relativo `img/...`.

## Struttura (cover + 6 slide)

0. **Cover** — "Centro di Competenza Quality Assurance · Dipartimento Pagamenti"; sottotitolo da incontro con la Direzione; nomi dei tre relatori; ottobre 2026.

1. **Chi siamo** — tre card con foto, ruolo nel team e 3 punti di background:
   - **Cristiano Sticca** — QA Manager. ~18 anni: GSE (IT Project Manager, referente qualità del software, 10+ anni), Enel (Solutions Architect), Treedom (Product Owner & QA Manager), Microsoft (Customer Success Account Manager). In PagoPA dal 2023.
   - **Andrea Ferracci** — Lead Tecnico. ~28 anni: 14 anni in BNL BNP Paribas (Enterprise Architect, TIBCO Competence Center, Technical Architect System Engineering & Automation: PaaS OpenShift, Jenkins/Ansible, Splunk). In PagoPA dal 2022 (Technical PM → Senior QA Engineer).
   - **Annalisa Sabatelli** — Business/Data Analyst. ~19 anni di qualità e validazione nell'industria: FCA (Body validation test project leader), Pininfarina, Alstom (Domain Leader, qualità e miglioramento continuo), Iveco, CIM4.0 Competence Center. In PagoPA dal 2025: Data Quality Framework, Data Contract, KPI.
   - Banda sotto: "~65 anni di esperienza complessiva" + team esteso esterno: **1 QA Analyst · 3 QA Engineer · 1 Data Engineer** (partner ALTEN, Quantyca).

2. **Perché esistiamo** — sinistra: punto di partenza, Assessment ALTEN 2025, maturità *Ad Hoc*, 5 gap in una riga ciascuno (strategia di test, test design, defect management, metriche, reporting). Destra: la risposta, cioè da pratiche ad hoc a qualità misurabile e replicabile con Quality Gate prima della produzione. Claim: *su una piattaforma di pagamenti nazionale un difetto in produzione costa in fiducia, non solo in ore.*

3. **Cosa facciamo** — due pilastri in linguaggio business:
   - **Testing**: test automatici richiamabili da qualsiasi pipeline (Test Automation Service), Quality Gate go/no-go, processo QA integrato nel ciclo di sviluppo.
   - **Data Quality**: controlli automatici sui dati del Data Lake, governati da Data Contract, osservabilità su SODA Cloud e alert.
   - Trasversali: **Central Hub QA** (link https://pagopa-u-itn-qa-qa-hub-wa.azurewebsites.net/), sinergia con SEND & Interop e IO-Wallet-Multicanalità (Quality Manifesto nato da noi e adottato da SL QA&OPS).

4. **Dove siamo oggi** — stato e numeri:
   - **TAS**: Checkout integrato (completato), eCommerce in integrazione. KPI: esecuzioni da pipeline (actor `pagopa-platform-github-bot`) dal 17/07/2026, con trend mensile (lug 29 · ago 10 · set 54 · ott 27 al 8/10; da riscaricare a ridosso dell'incontro). Mostrare **solo il volume** + nota: "la maggior parte dei fallimenti è debito tecnico che stiamo indirizzando con i team".
   - **Pilota**: Dismissione WISP up&running con test NRT; FdR in corso; POS (subentrato a CUP).
   - **Data Quality**: framework completato, **primo data check su GEC live dal 12/10**.
   - **Central Hub QA live**: drift check API SANP, KPI Jira del team, definizione controlli DQF, trend su entità (Commissioni PSP, GPD); in sviluppo le dashboard KPI dei test.
   - **Agentic AI**: in sperimentazione, in allineamento con le linee guida di Engineering.

5. **Dove vogliamo andare** — timeline: 2026 costruzione & pilota → **2027 anno dell'applicazione del framework a tutte le componenti** → target **Quality Gate sul 70% dei rilasci entro fine 2027**. Prossimi passi: Assessment TO-BE / QAdro (da pianificare), Agentic AI allineato a Engineering, sinergia a 3 dipartimenti.
   Riquadro **"Cosa serve per arrivarci"** (tre condizioni abilitanti, tono fattuale, non richiesta esplicita):
   1. adozione da parte dei team prodotto;
   2. continuità del team;
   3. un'identità organizzativa riconosciuta, sul modello della struttura duale già presente su SEND, per avere autorevolezza verso i team di sviluppo.

6. **Chiusura** — "Build Quality Together!" + una riga di sintesi.

## Fuori scope

- Non si modificano i deck esistenti.
- Nessuna esportazione PDF/PPT.
- Niente deep-dive tecnici o modali.
