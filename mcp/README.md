# MCP server

MCP server that exposes Sportlab data to Claude and other agents, on top of the same backend APIs.

Status: structure only; planned for phases 1–2.

## Principles

- Read-only at first.
- One personal token per user, with expiry and revocation; only the hash is stored in the database.
- Every request sees only the data of the user the token belongs to.
- A user pending approval cannot use it.

## Planned tools

- Activity list by period and sport, and the detail of one activity.
- Daily metrics (HRV, sleep, heart rate, readiness).
- Training load trend.
- Achievements, personal records and goals with progress.
