# Backend

API REST, modelli del database, sincronizzazione Garmin e migrazioni. Python con FastAPI, SQLAlchemy e Alembic.

Stato: solo struttura; il codice arriva nelle prossime fasi.

## Struttura prevista

```
app/
  api/        endpoint REST (sessioni, utenti, attività, metriche, obiettivi, amministrazione)
  core/       configurazione, sicurezza, cifratura delle chiavi, log
  db/         connessione, sessione, impostazione dell'utente per Row-Level Security
  models/     modelli SQLAlchemy (utente, attività, tracce, metriche, segmenti, obiettivi, traguardi)
  schemas/    schemi di ingresso e uscita delle API
  services/   logica applicativa, con filtro obbligatorio per utente
  sync/       worker di sincronizzazione con la Garmin Personal API
migrations/   migrazioni Alembic
tests/        test automatici
```

## Regole

- Ogni dato personale ha `user_id`; le query passano solo da `services/` con l'utente autenticato.
- Row-Level Security nel database come seconda barriera, con test che verificano che un utente non veda i dati di un altro.
- Due ruoli di database per ambiente: applicazione (solo dati) e migrazioni (struttura).
- Le migrazioni si rivedono a mano dopo la generazione automatica.
- Seeding ripetibile: dati di riferimento e utente amministratore da `ADMIN_EMAIL`; nessuna password.
