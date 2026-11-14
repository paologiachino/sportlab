# Server MCP

Server MCP che espone i dati di Sportlab a Claude e ad altri agenti, sopra le stesse API del backend.

Stato: solo struttura; previsto nelle fasi 1–2.

## Principi

- Sola lettura all'inizio.
- Un token personale per utente, con scadenza e revoca; nel database si salva solo l'hash.
- Ogni richiesta vede solo i dati dell'utente a cui appartiene il token.
- Un utente in attesa di approvazione non può usarlo.

## Strumenti previsti

- Elenco attività per periodo e sport e dettaglio di una attività.
- Metriche giornaliere (HRV, sonno, battito, readiness).
- Andamento del carico di allenamento.
- Traguardi, record personali e obiettivi con avanzamento.
