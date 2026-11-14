# Sportlab

Sito web multiutente per raccogliere e analizzare le attività sportive di una persona. I dati vengono scaricati da Garmin Connect (Personal API), salvati in un database PostgreSQL locale e mostrati in un'interfaccia web con dashboard, mappe e obiettivi. I dati sono accessibili anche a Claude (tramite un server MCP) per suggerimenti e pianificazione degli allenamenti.

Uso previsto: personale e familiare, su homelab, all'indirizzo `sportlab.lacrete.casa`. Il progetto è pensato per poter diventare pubblico in futuro.

> Stato: fase 0, solo struttura del progetto. Il codice dell'applicazione non c'è ancora.

## Stack

| Livello | Tecnologia |
| --- | --- |
| Backend e API | Python, FastAPI |
| ORM e migrazioni | SQLAlchemy, Alembic |
| Database | PostgreSQL con PostGIS |
| Frontend | Angular, TypeScript, Tailwind CSS |
| Mappe | MapLibre GL, con curve di livello da dati di elevazione |
| Accesso per Claude | server MCP (in sola lettura all'inizio) |
| Contenitori e deploy | Docker, GitHub Actions, GHCR |

## Struttura

```
backend/    API, modelli, sincronizzazione Garmin, migrazioni
frontend/   applicazione Angular
mcp/        server MCP per Claude e altri agenti
docs/       documentazione tecnica e decisioni
.github/    controlli automatici, Dependabot, modelli per le richieste di revisione
.vscode/    estensioni e impostazioni consigliate
```

La configurazione degli ambienti e dei deploy sta nel repository [sportlab-infra](https://github.com/paologiachino/sportlab-infra).

## Branch e ambienti

| Ambiente | Branch | Note |
| --- | --- | --- |
| Sviluppo | `feature/...`, `fix/...`, `chore/...` | in locale con Docker Compose |
| Pre-produzione | `staging` | dati sintetici |
| Produzione | `main` | dati reali |

1. `main` e `staging` sono protetti: nessuna scrittura diretta, solo richieste di revisione approvate.
2. Ogni modifica nasce in un branch e arriva su `staging` con una richiesta di revisione.
3. Dopo la prova in pre-produzione, `staging` entra in `main`.

Dettagli in [docs/branch-e-deploy.md](docs/branch-e-deploy.md).

## Sviluppo

Editor consigliato: VS Code con le estensioni elencate in `.vscode/extensions.json`, e Claude Code dal terminale integrato. Le regole di lavoro del progetto sono in [CLAUDE.md](CLAUDE.md).

Le istruzioni per avviare backend e frontend verranno aggiunte con il primo codice.

## Sicurezza

Non inserire mai password, chiavi o token nel repository. Il file `.env.example` elenca le variabili necessarie; i valori reali restano fuori dal repository.

## Licenza

GNU Affero General Public License v3.0. Vedi [LICENSE](LICENSE).
