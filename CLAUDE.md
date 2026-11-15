# CLAUDE.md — sportlab

Regole di lavoro per Claude Code in questo repository. Il proprietario è Paolo, che valida ogni modifica e usa il progetto anche per imparare: spiega le scelte non ovvie e procedi a piccoli passi.

## Progetto

Sito multiutente per attività sportive e dati di salute scaricati da Garmin (Personal API), con backend, frontend, server MCP e database PostgreSQL. Fase attuale: fase 0 (struttura). Descrizione completa in `README.md` e in `docs/`.

## Stack (confermato)

- Backend: Python, FastAPI, SQLAlchemy, Alembic.
- Database: PostgreSQL con PostGIS (da verificare sull'homelab, vedi `docs/postgis.md`).
- Frontend: Angular, TypeScript, Tailwind CSS.
- Mappe: MapLibre GL, curve di livello da DEM.
- MCP: server in sola lettura all'inizio, sopra le stesse API del backend.

## Modalità di lavoro

1. Lavora sempre su un branch (`feature/...`, `fix/...`, `chore/...`), mai direttamente su `main` o `staging`.
2. Passi piccoli: una funzione o un modulo alla volta, con test, poi una richiesta di revisione.
3. Spiega in breve ogni scelta non ovvia (struttura Angular, uso di SQLAlchemy, logica di sincronizzazione), così Paolo può validarla e imparare.
4. Non dichiarare un lavoro finito senza aver eseguito test e controlli di stile. Se non puoi eseguirli, dillo.
5. Una richiesta di revisione per volta, descritta in italiano, con cosa cambia e come provarla.

## Convenzioni (proposta, da confermare)

- Chat con Paolo in italiano. Codice, identificatori, workflow, commenti, messaggi di commit e descrizioni delle richieste di revisione in inglese.
- Messaggi di commit in inglese con prefisso: `feat:`, `fix:`, `chore:`, `docs:`, `test:`.
- La documentazione esistente (`README.md`, `docs/`) è ancora in italiano; la traduzione è da decidere.
- Python: formattazione e controllo con Ruff, tipi dove utile. TypeScript: ESLint e Prettier.

## Regole di sicurezza e dati

- Nessun segreto nel codice o nei repository: tutto da variabili d'ambiente (vedi `.env.example`).
- Ogni dato personale ha `user_id`; ogni query passa dallo strato che filtra per l'utente autenticato. Il database aggiunge Row-Level Security come seconda barriera.
- Gli utenti si registrano con Google e restano "in attesa" finché l'amministratore non li approva.
- L'amministratore è impersonale: nessun nome o email nel codice né nel seeding. Il ruolo `admin` va all'email in `ADMIN_EMAIL` al primo accesso; la registrazione libera non assegna mai ruoli.
- Le chiavi Garmin degli utenti si salvano cifrate; non si scrivono mai nei log.
- Le migrazioni si fanno con Alembic, scritte in modo compatibile con la versione precedente del codice.
- Dati di prova solo sintetici; mai dati reali di salute in sviluppo o pre-produzione.

## Comandi

Da completare quando esiste il codice (avvio, test, migrazioni, controlli di stile).

## Licenza

AGPL-3.0. Nuove dipendenze devono avere licenze compatibili.
