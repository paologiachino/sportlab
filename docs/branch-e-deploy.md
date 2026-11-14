# Branch, ambienti e deploy

## Ambienti

| Ambiente | Branch | Dove gira | Database | Dati |
| --- | --- | --- | --- | --- |
| Sviluppo | `feature/...` | Docker Compose sul PC | `sportlab_dev` | sintetici |
| Pre-produzione | `staging` | homelab | `sportlab_staging` | sintetici |
| Produzione | `main` | homelab, `sportlab.lacrete.casa` | `sportlab_prod` | reali |

I test automatici usano un database usa e getta creato a ogni esecuzione.

## Flusso dei branch

1. `main` e `staging` sono protetti: solo richieste di revisione approvate, con controlli automatici superati.
2. Ogni modifica nasce in `feature/...`, `fix/...` o `chore/...` e arriva su `staging` con una richiesta di revisione.
3. Il merge su `staging` avvia il deploy in pre-produzione.
4. Quando va bene, `staging` entra in `main` con una nuova richiesta di revisione e parte il deploy in produzione.

## Deploy

1. GitHub Actions esegue test, controlli di stile e scansione di sicurezza (dipendenze e segreti).
2. Con il merge su `staging` o `main` si costruiscono le immagini Docker e si salvano nel registro privato di GitHub (GHCR) con il tag del commit.
3. Un runner GitHub sull'homelab scarica le immagini e riavvia i container definiti in `sportlab-infra`.
4. Prima del backend gira il job di migrazione; in produzione è preceduto da un backup.
5. La produzione richiede l'approvazione manuale (Environments di GitHub).
6. Rollback: si rimette il tag precedente delle immagini; se una migrazione è incompatibile si ripristina il backup.

La configurazione degli ambienti e le procedure operative sono nel repository [sportlab-infra](https://github.com/paologiachino/sportlab-infra).

## Impostazioni GitHub da fare a mano

- Protezione dei branch `main` e `staging`: richiesta di revisione obbligatoria, controlli di stato obbligatori, divieto di push diretti.
- Environments `staging` e `production`, con approvazione manuale per `production`.
- Scansione dei segreti (secret scanning) e avvisi Dependabot attivi.
