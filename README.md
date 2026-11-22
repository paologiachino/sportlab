# Sportlab

Multi-user web site that collects and analyses a person's sports activities. Data is downloaded from Garmin Connect (Personal API), stored in a local PostgreSQL database and shown in a web interface with dashboards, maps and goals. The data is also available to Claude (through an MCP server) for suggestions and training planning.

Intended use: personal and family, on a homelab, at `sportlab.lacrete.casa`. The project is designed so that it can become public in the future.

> Migration: Sportlab is becoming **Zonedose**, with the backend on Orchard Core in the [zonedose](https://github.com/paologiachino/zonedose) repository. The frontend here already uses that backend; the FastAPI backend in `backend/` is paused.

> Status: Google sign-in, sessions and user approval work end to end, from the browser (backend step 2, frontend step 1). Next: the staging deploy, then the Garmin sync; the MCP server is not started yet.

## Stack

| Layer | Technology |
| --- | --- |
| Backend and API | Python, FastAPI |
| ORM and migrations | SQLAlchemy, Alembic |
| Database | PostgreSQL with PostGIS |
| Frontend | Angular, TypeScript, Tailwind CSS |
| Maps | MapLibre GL, with contour lines from elevation data |
| Access for Claude | MCP server (read-only at first) |
| Containers and deploy | Docker, GitHub Actions, GHCR |

## Structure

```
backend/    API, models, Garmin sync, migrations
frontend/   Angular application
mcp/        MCP server for Claude and other agents
docs/       technical documentation and decisions
.github/    automated checks, Dependabot, pull request template
.vscode/    recommended extensions and settings
```

Environment configuration and deploys live in the [sportlab-infra](https://github.com/paologiachino/sportlab-infra) repository.

## Branches and environments

| Environment | Branch | Notes |
| --- | --- | --- |
| Development | `feature/...`, `fix/...`, `chore/...` | local, with Docker Compose |
| Staging | `staging` | synthetic data |
| Production | `main` | real data |

1. `main` and `staging` are protected: no direct pushes, only pull requests with passing checks.
2. Every change starts in a branch and reaches `staging` through a pull request.
3. After testing in staging, `staging` is merged into `main`.

Details in [docs/branch-and-deploy.md](docs/branch-and-deploy.md).

## Access and administrator

- Login is with Google only. People who register stay "pending" until an administrator approves them.
- The administrator is not a default user: the `admin` role is assigned at the first login with the email set in `ADMIN_EMAIL` (environment variable, see `.env.example`). A dedicated Google address, separate from your personal account, is recommended.
- No real name or address appears in the code or in the seeding. The first user to register does **not** become admin.
- An admin can promote or demote other users; the last admin cannot be removed.

## Development

Recommended editor: VS Code with the extensions listed in `.vscode/extensions.json`, and Claude Code in the integrated terminal. The project's working rules are in [CLAUDE.md](CLAUDE.md).

To start the backend and run its checks, see [backend/README.md](backend/README.md); for the frontend, [frontend/README.md](frontend/README.md). Google sign-in needs an OAuth client: [docs/google-oauth.md](docs/google-oauth.md).

## Security

Never put passwords, keys or tokens in the repository. The `.env.example` file lists the required variables; the real values stay outside the repository.

## Licence

GNU Affero General Public License v3.0. See [LICENSE](LICENSE).
