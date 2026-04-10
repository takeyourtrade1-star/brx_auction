L'obiettivo è riscrivere il microservizio backend (da Node.js a Python) per il marketplace Ebartex. Il sistema deve essere progettato per una scalabilità orizzontale estrema (stile eBay/Amazon), altissima concorrenza, latenza minima e tolleranza ai guasti.
Non sono ammessi "colli di bottiglia" architetturali. Il codice deve seguire i principi della Clean Architecture / Domain-Driven Design (DDD).

🛠 2. Stack Tecnologico Imposto
Cursor AI DEVE utilizzare esclusivamente questo stack tecnologico:

Framework Core: FastAPI (per prestazioni estreme, supporto asincrono nativo e generazione automatica OpenAPI).

Server WSGI/ASGI: Gunicorn con worker Uvicorn (per gestire migliaia di richieste simultanee).

Validazione Dati: Pydantic V2 (tipizzazione rigorosa di input/output).

Database ORM/Query Builder: SQLAlchemy 2.0 (modalità esclusivamente ASYNC tramite asyncpg per PostgreSQL). Vietato usare driver sincroni nel flusso delle richieste web per evitare blocchi dell'Event Loop.

Gestione Cache e Rate Limiting: Redis (tramite redis.asyncio).

HTTP Client per altri microservizi: httpx (asincrono).

🏗 3. Struttura del Progetto (Clean Architecture)
Il codice generato da Cursor DEVE essere modulare. È severamente vietato creare file monolitici. La struttura deve essere:

Plaintext
app/
├── api/             # Router FastAPI, Endpoints (solo logica HTTP di smistamento)
├── core/            # Configurazione, Sicurezza (JWT, RS256), Dipendenze (Dependencies)
├── schemas/         # Modelli Pydantic (Input/Output, DTOs)
├── models/          # Modelli SQLAlchemy (Mappatura DB)
├── services/        # Logica di Business pura (qui risiede il cuore del marketplace)
├── infrastructure/  # Connessioni DB, Redis, client per Meilisearch/Auth
└── utils/           # Funzioni di supporto, eccezioni personalizzate
🔒 4. Sicurezza e Autenticazione (RS256 JWT)
La sicurezza deve essere "Zero Trust".

Autenticazione Asimmetrica (RS256): * I token JWT vengono generati dal Microservizio Auth separato. Questo microservizio Python NON deve generare token, ma solo validarli.

Prevenzione Collo di Bottiglia: Il microservizio deve avere la Public Key JWT in configurazione (env AUTH_JWT_PUBLIC_KEY, stessa chiave del servizio Auth) e validare i token localmente in memoria. Nessuna chiamata HTTP al servizio Auth per ogni richiesta (scalabilità). Se in futuro Auth espone un endpoint JWKS, si può prevedere il download della key all'avvio con TTL in cache.

Dependencies di FastAPI: Usare Depends() per estrarre l'utente dal token e bloccare la richiesta con un 401 Unauthorized prima ancora di toccare la logica di business.

Role-Based Access Control (RBAC): Implementare decoratori o dipendenze per verificare se l'utente ha privilegi Admin o User normale.

🛡 5. Prevenzione Vulnerabilità e Difesa Attiva
Cursor deve implementare meccanismi per prevenire attacchi automatici, bot e scraping abusivo:

Rate Limiting Distribuito: Ogni endpoint esposto pubblicamente deve avere un rate limiter basato su Redis (es. libreria fastapi-limiter).

Regola: Limiti differenziati (es. Endpoint di login/recupero password: 5 req/min. Ricerca: 100 req/min).

Validazione Rigida (Pydantic): Nessun dato esterno deve toccare il DB senza passare per Pydantic. Utilizzare regex, lunghezze massime (max_length) e tipi specifici (EmailStr, HttpUrl) per prevenire SQL Injection, XSS e Buffer Overflow.

Gestione CORS e Security Headers: Configurare CORS rigorosamente sui domini consentiti. Aggiungere middleware per header di sicurezza (HSTS, No-Sniff).

🚀 6. Scalabilità e Prevenzione Colli di Bottiglia (Performance)
Per reggere il traffico di un marketplace enorme, Cursor deve applicare queste best practice:

Tutto Asincrono (100% Async): Ogni chiamata a DB, Redis, o API esterne (es. Meilisearch) DEVE avere await. Se una singola funzione blocca l'Event Loop, l'intero server si congela per tutti gli utenti.

Connection Pooling (Critico): Il DB MySQL (oltre 500MB di dati e tabelle relazionali complesse) non reggerà se si apre e chiude una connessione per ogni query. Usare l'AsyncEngine di SQLAlchemy con un pool_size generoso (es. 20-50) e max_overflow.

Strategia di Caching: Dati che cambiano raramente (Categorie, liste dei Set, configurazioni di gioco) DEVONO essere servite da Redis o RAM Cache, non da PostgreSQL.

Paginazione Obbligatoria: Qualsiasi endpoint che restituisca una lista (carte, transazioni, ordini) DEVE implementare Limit/Offset o Keyset Pagination (Cursor Pagination preferita per prestazioni su tabelle grandi). Mai fare SELECT * senza limiti.

🔗 7. Ecosistema e Interazioni tra Microservizi
Cursor deve sapere che questo microservizio non vive da solo:

Interazione con Meilisearch (Motore di Ricerca): * La ricerca globale (Autocomplete, full-text) viene fatta dal frontend direttamente su Meilisearch.

Il Backend Python deve intervenire solo in fase di scrittura/aggiornamento. Quando una carta viene venduta, aggiunta o modificata nel database, il backend deve mettere in coda una richiesta di reindex (Redis list/stream). Un worker separato consuma la coda e chiama BRX_Search (POST /api/admin/reindex con X-Admin-API-Key) per mantenere l'indice aggiornato, senza rallentare la risposta HTTP all'utente. BRX_Search espone solo il reindex completo (non push di singoli documenti).

Interazione con Database Locale: PostgreSQL con tabelle marketplace (auctions, bids, products) e sync (user_sync_settings, user_inventory_items, sync_operations). Le card sono referenziate per id (es. blueprint_id); i dettagli si recuperano da servizi esterni o da Meilisearch. Fai riferimento allo schema SQL esistente per i modelli SQLAlchemy.

🤖 8. Regole di Comportamento per l'Agente AI (Cursor)
Pensa prima di scrivere: Prima di implementare un endpoint, scrivi nei commenti (o spiegami) il flusso logico, le query SQL generate e i potenziali rischi di concorrenza.

Type Hinting Assoluto: Tutto il codice Python deve avere type hints (def get_user(id: int) -> UserSchema:). Nessun tipo Any a meno che non sia strettamente necessario.

Gestione Errori Globali: Centralizza le eccezioni. Mai restituire lo stack trace o errori SQL all'utente finale (Information Disclosure). Ritorna sempre formati JSON standard (es. {"detail": "User not found", "code": "USER_NOT_FOUND"}).

Log Strutturati: Usa la libreria logging (o loguru) stampando in formato JSON, includendo request_id per poter tracciare gli errori tra microservizi in AWS CloudWatch.