# PostGIS: verifica e installazione

PostGIS serve per tracce GPS e segmenti (mappe e segmenti, fase 3). L'immagine ufficiale di PostgreSQL non lo include.

Decisione: si usa il container PostgreSQL esistente sull'homelab, che è vuoto. Si sostituisce l'immagine con `postgis/postgis` (verificare i tag disponibili su Docker Hub).

## Verifica

I nomi tra parentesi angolari vanno sostituiti.

```bash
# container e immagine
docker ps --format "table {{.Names}}\t{{.Image}}"

# versione di PostgreSQL
docker exec -it <container> psql -U <utente> -d postgres -c "SHOW server_version;"

# estensione disponibile?
docker exec -it <container> psql -U <utente> -d postgres -c "SELECT name, default_version, installed_version FROM pg_available_extensions WHERE name LIKE 'postgis%';"
```

Nessuna riga: PostGIS non è installato. Con righe: si abilita in ogni database con `CREATE EXTENSION postgis;` e si controlla con `SELECT postgis_full_version();`.

## Procedura

1. Controllare con `\l` (in `psql`) che il PostgreSQL sia davvero vuoto e annotare la versione maggiore.
2. Backup per prudenza: `docker exec <container> pg_dumpall -U <utente> > backup.sql`, da conservare fuori dal container.
3. Cambiare l'immagine nel file Docker Compose dell'homelab con `postgis/postgis` della versione desiderata. Se la versione maggiore cambia, ricreare il volume dati (nessun dato da conservare).
4. Aggiornare e riavviare: `docker compose pull` e `docker compose up -d`.
5. Creare i database `sportlab_staging` e `sportlab_prod` con i ruoli applicazione e migrazioni, abilitare PostGIS in ciascuno e verificarlo.

L'installazione dei pacchetti con `apt` dentro il container non è consigliata: si perde alla prima ricreazione.
