# QA Center of Competence — AllHands di Dipartimento (design)

## Contesto

Esiste già un deck HTML interattivo (`docs/presentazioni/PFM3_QA_Presentation.html`, 10 slide) che racconta in modo dettagliato l'assessment 2025, i gap, il framework QA e la roadmap del Centro di Competenza QA.

Serve un **nuovo deck**, molto più sintetico, per il prossimo AllHands di Dipartimento: la platea conosce già il perché e l'assessment iniziale (già coperti nell'AllHands precedente), quindi il focus è su **cosa è stato costruito finora** e sulle **novità**. Il deck ha due parti:

- **Corpo principale**: 15 minuti
- **Deep-dive**: 5 minuti extra dedicati al Test Automation Service (TAS), esposto in modo non tecnico per una platea eterogenea

## Output

Nuovo file: `docs/presentazioni/QA_AllHands_2026.html`

- Riusa il motore HTML/CSS/JS del deck PFM3 (slide system con transizioni, progress bar, nav dots, slide counter, toggle light/dark, font Playfair Display / DM Sans / Space Mono, palette teal/cyan/amber/pink su sfondo navy) per coerenza di brand e per velocità di realizzazione.
- Componenti riusabili dal deck esistente: `.card`, `.achievements-grid`/`.ach-item`, `.fw-grid`/`.fw-tile`, `.timeline`/`.tl-item`, `.pillar`, `.two-col`/`.three-col`, timeline orizzontale della roadmap.
- Non è richiesto il riuso dei componenti più elaborati e "tecnici" del vecchio deck (flow-diagram modal step-by-step, maturity gauge/bar, comparison table sinergia con tabelle dense) a meno che non servano in forma alleggerita.

## Struttura del deck

### Corpo principale (~9-10 slide, 15 minuti)

1. **Cover** — "Centro di Competenza Quality Assurance", riuso layout, data/contesto aggiornati (AllHands di Dipartimento).
2. **Apertura / momentum** — messaggio: il Centro di Competenza QA è tra i progetti su cui il Dipartimento ha investito di più, in continuità con quanto detto nello scorso AllHands. Nessun richiamo ad assessment/gap 2025 (già noti alla platea).
3. **Due Pilastri** — differenziazione Testing vs Data Quality & Strategy, versione sintetica della slide "Due Pilastri" del deck PFM3 (idea dei due `pillar` box).
4. **Cosa abbiamo costruito** — achievement grid con numeri aggiornati rispetto al deck PFM3 (verificare/aggiornare i valori: pagine Confluence, principi manifesto, board Jira, ADR/GDR, ecc.), eventualmente con tile aggiuntive per segnalare le novità (TAS, Central Hub QA, stack AI) come "costruito quest'anno".
5. **Framework Testing** — versione alleggerita della slide "Il Framework QA in Dettaglio": poche tile (3-5), niente approfondimenti modali multi-step, solo gli elementi più rappresentativi (es. RACI, processo QA/SDLC, Jira, cadence).
6. **Framework Data Quality** — versione alleggerita della slide "Governance del Dato nel Data Lake", stesso principio di sintesi.
7. **Novità · Stack AI agentico** — 1 slide non tecnica. Messaggio: il team QA ha dotato il proprio workflow di un sistema di agenti AI governati (ruoli distinti tipo analyst/engineer/runner/closer, regole e guardrail, gestione del passaggio di consegne tra agenti) per velocizzare scrittura e manutenzione delle suite di test, riducendo errori e tempo di onboarding. Niente riferimenti a front matter YAML, nomi di file `.prompt.md`/`.agent.md`, dettagli implementativi: solo il valore per chi ascolta (velocità, meno variabilità, tracciabilità).
8. **Novità · Central Hub QA** — 1 slide. Messaggio: nuovo portale unico (FE Next.js + BE FastAPI) che consolida strumenti prima sparsi: generatore scenari BDD/Gherkin assistito da AI, dashboard suite E2E, KPI Jira (Testing/SANP/Data), Data Hub (catalogo PSP/servizi pagoPA, posizioni debitorie GPD), knowledge base documentale, gestione utenti/ruoli. Va presentato come evoluzione/superamento di Dashboard One e del vecchio Portale NRT.
9. **Sinergia dipartimenti** — Pagamenti ⇄ SEND & Interop, versione aggiornata/sintetizzata della slide esistente (mantenendo l'idea di scambio reciproco, senza necessariamente la tabella comparativa dettagliata).
10. **Cosa stiamo facendo ora** — aggiornata rispetto al deck PFM3:
    - *Automatismi CI/CD* → riformulata: il TAS è stato costruito, ora in fase di adozione da parte dei team prodotto, a partire dal progetto pilota **Checkout**.
    - *Data Quality Framework* → riformulata: framework completato, controlli di qualità su **GPD** pronti, in fase di passaggio in produzione su **SODA**.
    - *Adeguamento Portale NRT* → riformulata: inquadrata dentro il tema più ampio del **Central Hub QA**.
    - *Coordinamento & Evoluzione* → ridotta al solo **Sync con SL QA&OPS**; rimossi hiring e biblioteca standard documentali (conclusi/non più rilevanti da riportare).
    - Rimangono/aggiornare secondo necessità i progetti pilota in corso (verificare se Canone Unico Patrimoniale, FdR, Dismissione WISP sono ancora attuali o se lo stato è cambiato).
11. **Roadmap aggiornata** — timeline orizzontale "Da oggi a Giugno 2027" riusando il componente del deck PFM3, con milestone attualizzate alla luce dello stato corrente (es. "Siamo Qui" spostato in avanti, contenuti delle fasi successive coerenti con TAS/Central Hub/DQ in produzione).
12. **Chiusura** — claim finale (riuso "Build Quality Together!" o variante), transizione verso il deep-dive TAS.

### Deep-dive TAS (~4 slide, 5 minuti, non tecniche)

Fonti: i due PDF forniti (manuale sviluppatore TAS, design record TAS). Il pubblico è eterogeneo e non tecnico: niente YAML/script/nomi di opzioni (workflow_call, tas_orchestrator.py, ecc.) in slide — al massimo nei talking point/note dello speaker, se il formato lo consente.

A. **Cos'è il TAS** — il problema che risolve: suite di test di integrazione centralizzate, richiamabili da qualsiasi pipeline esterna (GitHub Actions, Azure DevOps, altro CI/CD) senza che il team chiamante debba gestire segreti o conoscere i dettagli dei test.

B. **Come si integra** — versione non tecnica dell'albero decisionale del manuale: messaggio "due percorsi pronti all'uso (template ufficiali per Azure DevOps e per GitHub Actions), pochissima configurazione, tutta la complessità è nascosta dal TAS".

C. **Cosa restituisce** — esito chiaro e strutturato (test passati/falliti/saltati, tempo di esecuzione, esito finale) usato per decidere se bloccare o meno un rilascio.

D. **Stato & adozione** — cosa è già operativo, target di adozione corrente (Checkout come primo team prodotto), prossimi passi di rollout.

## Cose da verificare con l'utente in fase di stesura contenuti (non bloccanti per il design)

- Valori numerici aggiornati per la slide "Cosa abbiamo costruito" (alcuni numeri del deck PFM3 potrebbero essere cambiati).
- Stato aggiornato dei progetti pilota (slide 10) oltre a quanto già indicato.
- Milestone esatte della roadmap aggiornata (slide 11), in particolare la posizione di "Siamo Qui".

## Fuori scope

- Non si tocca il deck PFM3 esistente.
- Non si introducono nuovi framework/librerie: puro HTML/CSS/JS statico come l'originale.
- Non è richiesta l'esportazione in altri formati (PDF/PPT): resta un deck HTML navigabile a schermo.
